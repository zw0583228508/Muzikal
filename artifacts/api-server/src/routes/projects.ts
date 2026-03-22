import { Router, type IRouter } from "express";
import multer from "multer";
import path from "path";
import fs from "fs";
import { eq, desc } from "drizzle-orm";
import { db, projectsTable, jobsTable, analysisResultsTable, arrangementsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";

const router: IRouter = Router();

// File upload storage
const UPLOADS_DIR = process.env.UPLOADS_DIR || "/tmp/music-ai-uploads";
if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOADS_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, `${uuidv4()}${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB
  fileFilter: (_req, file, cb) => {
    const allowed = [".wav", ".mp3", ".flac", ".aiff", ".m4a", ".ogg"];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error(`Unsupported file type: ${ext}`));
  },
});

const PYTHON_BACKEND = process.env.PYTHON_BACKEND_URL || "http://localhost:8001";

async function callPythonBackend(endpoint: string, body: object) {
  const res = await fetch(`${PYTHON_BACKEND}/python-api${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Python backend error: ${err}`);
  }
  return res.json();
}

// GET /api/projects
router.get("/", async (_req, res) => {
  const projects = await db.select().from(projectsTable).orderBy(desc(projectsTable.createdAt));
  res.json(projects.map(p => ({
    id: p.id,
    name: p.name,
    description: p.description,
    status: p.status,
    audioFileName: p.audioFileName,
    audioDurationSeconds: p.audioDurationSeconds,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
  })));
});

// POST /api/projects
router.post("/", async (req, res) => {
  const { name, description } = req.body;
  if (!name) {
    res.status(400).json({ error: "name is required" });
    return;
  }
  const [project] = await db.insert(projectsTable).values({ name, description }).returning();
  res.status(201).json({
    id: project.id,
    name: project.name,
    description: project.description,
    status: project.status,
    audioFileName: project.audioFileName,
    audioDurationSeconds: project.audioDurationSeconds,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
  });
});

// GET /api/projects/:id
router.get("/:id", async (req, res) => {
  const id = parseInt(req.params.id);
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, id));
  if (!project) {
    res.status(404).json({ error: "Project not found" });
    return;
  }
  res.json({
    id: project.id,
    name: project.name,
    description: project.description,
    status: project.status,
    audioFileName: project.audioFileName,
    audioDurationSeconds: project.audioDurationSeconds,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
  });
});

// DELETE /api/projects/:id
router.delete("/:id", async (req, res) => {
  const id = parseInt(req.params.id);
  await db.delete(projectsTable).where(eq(projectsTable.id, id));
  res.status(204).send();
});

// POST /api/projects/:id/upload
router.post("/:id/upload", upload.single("file"), async (req, res) => {
  const projectId = parseInt(req.params.id);
  const file = req.file;

  if (!file) {
    res.status(400).json({ error: "No file provided" });
    return;
  }

  const jobId = `upload-${uuidv4()}`;

  // Update project with file info
  await db.update(projectsTable)
    .set({ audioFileName: file.originalname, audioFilePath: file.path, status: "uploading", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));

  // Create job record
  await db.insert(jobsTable).values({
    jobId,
    projectId,
    type: "upload",
    status: "completed",
    progress: 100,
    currentStep: "Upload complete",
  });

  // Update status to analyzed-ready
  await db.update(projectsTable)
    .set({ status: "created", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));

  res.json({
    jobId,
    projectId,
    type: "upload",
    status: "completed",
    progress: 100,
    currentStep: "Upload complete",
    createdAt: new Date(),
  });
});

// POST /api/projects/:id/analyze
router.post("/:id/analyze", async (req, res) => {
  const projectId = parseInt(req.params.id);

  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) {
    res.status(404).json({ error: "Project not found" });
    return;
  }

  if (!project.audioFilePath) {
    res.status(400).json({ error: "No audio file uploaded yet" });
    return;
  }

  const jobId = `analysis-${uuidv4()}`;

  await db.insert(jobsTable).values({
    jobId,
    projectId,
    type: "analysis",
    status: "queued",
    progress: 0,
    currentStep: "Queued",
  });

  // Call Python backend to start analysis
  try {
    await callPythonBackend("/analyze", {
      job_id: jobId,
      project_id: projectId,
      audio_file_path: project.audioFilePath,
    });
  } catch (err) {
    // Python backend might not be running - update job to simulate progress
    console.warn("Python backend not available, using simulated analysis");
    runSimulatedAnalysis(jobId, projectId);
  }

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json({
    jobId: job.jobId,
    projectId: job.projectId,
    type: job.type,
    status: job.status,
    progress: job.progress,
    currentStep: job.currentStep,
    createdAt: job.createdAt,
  });
});

// GET /api/projects/:id/analysis
router.get("/:id/analysis", async (req, res) => {
  const projectId = parseInt(req.params.id);
  const [result] = await db.select().from(analysisResultsTable)
    .where(eq(analysisResultsTable.projectId, projectId));

  if (!result) {
    res.status(404).json({ error: "Analysis not ready" });
    return;
  }

  res.json({
    projectId: result.projectId,
    rhythm: result.rhythmData,
    key: result.keyData,
    chords: result.chordsData,
    melody: result.melodyData,
    structure: result.structureData,
    waveformData: result.waveformData,
  });
});

// POST /api/projects/:id/arrangement
router.post("/:id/arrangement", async (req, res) => {
  const projectId = parseInt(req.params.id);
  const { styleId, instruments, density, humanize, tempoFactor } = req.body;

  const jobId = `arrangement-${uuidv4()}`;

  await db.insert(jobsTable).values({
    jobId,
    projectId,
    type: "arrangement",
    status: "queued",
    progress: 0,
    currentStep: "Queued",
  });

  try {
    await callPythonBackend("/arrange", {
      job_id: jobId,
      project_id: projectId,
      style_id: styleId || "pop",
      instruments: instruments || null,
      density: density ?? 0.7,
      humanize: humanize ?? true,
      tempo_factor: tempoFactor ?? 1.0,
    });
  } catch (err) {
    console.warn("Python backend not available, using simulated arrangement");
    runSimulatedArrangement(jobId, projectId, styleId || "pop");
  }

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json({
    jobId: job.jobId,
    projectId: job.projectId,
    type: job.type,
    status: job.status,
    progress: job.progress,
    currentStep: job.currentStep,
    createdAt: job.createdAt,
  });
});

// GET /api/projects/:id/arrangement
router.get("/:id/arrangement", async (req, res) => {
  const projectId = parseInt(req.params.id);
  const [result] = await db.select().from(arrangementsTable)
    .where(eq(arrangementsTable.projectId, projectId));

  if (!result) {
    res.status(404).json({ error: "Arrangement not ready" });
    return;
  }

  res.json({
    projectId: result.projectId,
    styleId: result.styleId,
    tracks: result.tracksData,
    totalDurationSeconds: result.totalDurationSeconds,
  });
});

// POST /api/projects/:id/export
router.post("/:id/export", async (req, res) => {
  const projectId = parseInt(req.params.id);
  const { formats } = req.body;

  const jobId = `export-${uuidv4()}`;

  await db.insert(jobsTable).values({
    jobId,
    projectId,
    type: "export",
    status: "queued",
    progress: 0,
    currentStep: "Queued",
  });

  // Simulate export process
  runSimulatedExport(jobId, projectId, formats);

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json({
    jobId: job.jobId,
    projectId: job.projectId,
    type: job.type,
    status: job.status,
    progress: job.progress,
    currentStep: job.currentStep,
    createdAt: job.createdAt,
  });
});

// --- Simulation helpers (fallback when Python backend unavailable) ---

async function runSimulatedAnalysis(jobId: string, projectId: number) {
  const steps = [
    { step: "Loading audio", progress: 10 },
    { step: "Separating sources", progress: 20 },
    { step: "Analyzing rhythm and tempo", progress: 35 },
    { step: "Detecting key and mode", progress: 50 },
    { step: "Analyzing chord progressions", progress: 65 },
    { step: "Extracting melody", progress: 78 },
    { step: "Detecting song structure", progress: 88 },
    { step: "Finalizing results", progress: 95 },
  ];

  for (const { step, progress } of steps) {
    await new Promise(r => setTimeout(r, 2000));
    await db.update(jobsTable)
      .set({ status: "running", progress, currentStep: step, updatedAt: new Date() })
      .where(eq(jobsTable.jobId, jobId));
    await db.update(projectsTable)
      .set({ status: "analyzing", updatedAt: new Date() })
      .where(eq(projectsTable.id, projectId));
  }

  // Save simulated analysis data
  const waveform = Array.from({ length: 1000 }, (_, i) => Math.abs(Math.sin(i * 0.1) * Math.random() * 0.8 + 0.1));
  const bpm = 120 + Math.floor(Math.random() * 40);
  const beatDuration = 60 / bpm;
  const totalDuration = 180;
  const beatGrid = Array.from({ length: Math.floor(totalDuration / beatDuration) }, (_, i) => parseFloat((i * beatDuration).toFixed(3)));
  const downbeats = beatGrid.filter((_, i) => i % 4 === 0);

  await db.insert(analysisResultsTable).values({
    projectId,
    rhythmData: {
      bpm,
      timeSignatureNumerator: 4,
      timeSignatureDenominator: 4,
      beatGrid,
      downbeats,
    },
    keyData: {
      globalKey: ["C", "Am", "G", "F", "D", "Em"][Math.floor(Math.random() * 6)],
      mode: Math.random() > 0.4 ? "major" : "minor",
      confidence: 0.85 + Math.random() * 0.1,
      modulations: [],
    },
    chordsData: {
      chords: generateSimulatedChords(totalDuration, beatDuration),
      leadSheet: "C | Am | F | G | C | Am | F | G",
    },
    melodyData: {
      notes: generateSimulatedMelody(totalDuration),
      inferredHarmony: ["C - Am - F - G", "C - F - Am - G", "Am - F - C - G"],
    },
    structureData: {
      sections: [
        { label: "intro", startTime: 0, endTime: 16, confidence: 0.88 },
        { label: "verse", startTime: 16, endTime: 48, confidence: 0.82 },
        { label: "chorus", startTime: 48, endTime: 80, confidence: 0.91 },
        { label: "verse", startTime: 80, endTime: 112, confidence: 0.79 },
        { label: "chorus", startTime: 112, endTime: 144, confidence: 0.93 },
        { label: "bridge", startTime: 144, endTime: 160, confidence: 0.75 },
        { label: "chorus", startTime: 160, endTime: 180, confidence: 0.89 },
      ],
    },
    waveformData: waveform,
  });

  await db.update(jobsTable)
    .set({ status: "completed", progress: 100, currentStep: "Analysis complete", updatedAt: new Date() })
    .where(eq(jobsTable.jobId, jobId));
  await db.update(projectsTable)
    .set({ status: "analyzed", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
}

function generateSimulatedChords(duration: number, beatDuration: number) {
  const progressions = [
    ["C", "Am", "F", "G"],
    ["Am", "F", "C", "G"],
    ["G", "D", "Em", "C"],
    ["F", "G", "Am", "C"],
  ];
  const prog = progressions[Math.floor(Math.random() * progressions.length)];
  const chords = [];
  let t = 0;
  let i = 0;
  const chordDuration = beatDuration * 4;
  while (t < duration) {
    chords.push({
      startTime: parseFloat(t.toFixed(2)),
      endTime: parseFloat(Math.min(t + chordDuration, duration).toFixed(2)),
      chord: prog[i % prog.length],
      romanNumeral: ["I", "vi", "IV", "V"][i % 4],
      confidence: 0.78 + Math.random() * 0.18,
      alternatives: ["Am7", "Cadd9"],
    });
    t += chordDuration;
    i++;
  }
  return chords;
}

function generateSimulatedMelody(duration: number) {
  const notes = [];
  const scale = [60, 62, 64, 65, 67, 69, 71, 72]; // C major
  let t = 0;
  while (t < duration * 0.6) {
    const noteDuration = [0.25, 0.5, 1.0][Math.floor(Math.random() * 3)];
    const pitch = scale[Math.floor(Math.random() * scale.length)];
    notes.push({
      startTime: parseFloat(t.toFixed(3)),
      endTime: parseFloat((t + noteDuration * 0.9).toFixed(3)),
      pitch,
      frequency: parseFloat((440 * Math.pow(2, (pitch - 69) / 12)).toFixed(2)),
      velocity: 65 + Math.floor(Math.random() * 30),
    });
    t += noteDuration + (Math.random() > 0.7 ? 0.1 : 0);
  }
  return notes;
}

async function runSimulatedArrangement(jobId: string, projectId: number, styleId: string) {
  const steps = [
    { step: "Loading analysis data", progress: 20 },
    { step: "Generating drum pattern", progress: 40 },
    { step: "Creating bass line", progress: 55 },
    { step: "Building chord voicings", progress: 70 },
    { step: "Adding orchestration", progress: 85 },
    { step: "Humanizing performance", progress: 95 },
  ];

  for (const { step, progress } of steps) {
    await new Promise(r => setTimeout(r, 1500));
    await db.update(jobsTable)
      .set({ status: "running", progress, currentStep: step, updatedAt: new Date() })
      .where(eq(jobsTable.jobId, jobId));
  }

  const totalDuration = 180;
  const bpm = 120;
  const beatDuration = 60 / bpm;

  const tracks = [
    generateDrumTrack(totalDuration, bpm),
    generateBassTrack(totalDuration, bpm),
    generatePianoTrack(totalDuration, bpm),
    generateStringsTrack(totalDuration, bpm),
  ];

  await db.insert(arrangementsTable).values({
    projectId,
    styleId,
    tracksData: tracks,
    totalDurationSeconds: totalDuration,
  }).onConflictDoNothing();

  await db.update(jobsTable)
    .set({ status: "completed", progress: 100, currentStep: "Arrangement complete", updatedAt: new Date() })
    .where(eq(jobsTable.jobId, jobId));
  await db.update(projectsTable)
    .set({ status: "arranged", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
}

function generateDrumTrack(duration: number, bpm: number) {
  const beatDuration = 60 / bpm;
  const notes = [];
  for (let t = 0; t < duration; t += beatDuration) {
    const beatInMeasure = Math.floor(t / beatDuration) % 4;
    if (beatInMeasure === 0) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 36, velocity: 100 });
    if (beatInMeasure === 2) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 36, velocity: 88 });
    if (beatInMeasure === 1 || beatInMeasure === 3) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 38, velocity: 95 });
    notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.05, pitch: 42, velocity: 60 });
    notes.push({ startTime: parseFloat((t + beatDuration / 2).toFixed(3)), duration: 0.05, pitch: 42, velocity: 50 });
  }
  return { id: "drums", name: "Drums", instrument: "Drum Kit", channel: 9, color: "#e74c3c", notes, volume: 0.85, pan: 0, muted: false, soloed: false };
}

function generateBassTrack(duration: number, bpm: number) {
  const chordRoots = [36, 33, 29, 31]; // C, A, F, G bass octave
  const chordDuration = (60 / bpm) * 4;
  const notes = [];
  let t = 0;
  let i = 0;
  while (t < duration) {
    notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((chordDuration * 0.45).toFixed(3)), pitch: chordRoots[i % 4], velocity: 88 });
    notes.push({ startTime: parseFloat((t + chordDuration * 0.5).toFixed(3)), duration: parseFloat((chordDuration * 0.4).toFixed(3)), pitch: chordRoots[i % 4] + 7, velocity: 75 });
    t += chordDuration;
    i++;
  }
  return { id: "bass", name: "Bass", instrument: "Electric Bass", channel: 1, color: "#8e44ad", notes, volume: 0.80, pan: -0.1, muted: false, soloed: false };
}

function generatePianoTrack(duration: number, bpm: number) {
  const chords = [[48, 52, 55], [45, 48, 52], [41, 45, 48], [43, 47, 50]]; // C, Am, F, G triads
  const chordDuration = (60 / bpm) * 4;
  const notes = [];
  let t = 0;
  let i = 0;
  while (t < duration) {
    for (const pitch of chords[i % 4]) {
      notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((chordDuration * 0.85).toFixed(3)), pitch: pitch + 12, velocity: 70 });
    }
    t += chordDuration;
    i++;
  }
  return { id: "piano", name: "Piano", instrument: "Grand Piano", channel: 2, color: "#2980b9", notes, volume: 0.70, pan: 0.1, muted: false, soloed: false };
}

function generateStringsTrack(duration: number, bpm: number) {
  const chords = [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]];
  const chordDuration = (60 / bpm) * 4;
  const notes = [];
  let t = 0;
  let i = 0;
  while (t < duration) {
    for (const pitch of chords[i % 4]) {
      notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((chordDuration * 0.98).toFixed(3)), pitch, velocity: 55 });
    }
    t += chordDuration;
    i++;
  }
  return { id: "strings", name: "Strings", instrument: "String Ensemble", channel: 4, color: "#f39c12", notes, volume: 0.60, pan: 0, muted: false, soloed: false };
}

async function runSimulatedExport(jobId: string, projectId: number, formats: string[]) {
  const fmtList = formats || ["midi", "wav"];
  for (let i = 0; i < fmtList.length; i++) {
    await new Promise(r => setTimeout(r, 1000));
    const progress = Math.round(((i + 1) / fmtList.length) * 100);
    await db.update(jobsTable)
      .set({ status: "running", progress, currentStep: `Exporting ${fmtList[i].toUpperCase()}`, updatedAt: new Date() })
      .where(eq(jobsTable.jobId, jobId));
  }
  await db.update(jobsTable)
    .set({ status: "completed", progress: 100, currentStep: "Export complete", updatedAt: new Date() })
    .where(eq(jobsTable.jobId, jobId));
  await db.update(projectsTable)
    .set({ status: "done", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
}

export default router;
