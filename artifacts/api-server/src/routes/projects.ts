import { Router, type IRouter } from "express";
import multer from "multer";
import path from "path";
import fs from "fs";
import { eq, desc, and, count } from "drizzle-orm";
import { db, projectsTable, jobsTable, analysisResultsTable, arrangementsTable, projectFilesTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "../lib/websocket";
import { parseProjectId } from "../lib/validate";

const router: IRouter = Router();

// ─── Config ──────────────────────────────────────────────────────────────────
const UPLOADS_DIR = process.env.UPLOADS_DIR || "/tmp/music-ai-uploads";
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const PYTHON_BACKEND = process.env.PYTHON_BACKEND_URL || "http://localhost:8001";

/**
 * MOCK_MODE controls behaviour when the Python backend is unavailable.
 * When MOCK_MODE=true (default in dev), the Node layer runs a clearly-labelled
 * simulation so the UI remains exercisable without a working ML backend.
 * When MOCK_MODE=false, any Python backend failure marks the job as FAILED
 * — no silent fake success. Set this to "false" in production.
 */
const MOCK_MODE = (process.env.MOCK_MODE ?? "true").toLowerCase() === "true";
const PIPELINE_VERSION = "1.1.0";

const MODEL_VERSIONS: Record<string, string> = {
  madmom:       "0.16.1",
  essentia:     "2.1b6",
  "chord-cnn":  "0.4.0",
  pyin:         "0.1.1",
  msaf:         "0.5.0",
  demucs:       "htdemucs-4.0",
  crepe:        "0.0.13",
};

const MODEL_BY_TYPE: Record<string, string> = {
  rhythm:     `madmom-${MODEL_VERSIONS.madmom}`,
  key:        `essentia-${MODEL_VERSIONS.essentia}`,
  chords:     `chord-cnn-${MODEL_VERSIONS["chord-cnn"]}`,
  melody:     `pyin-${MODEL_VERSIONS.pyin}`,
  structure:  `msaf-${MODEL_VERSIONS.msaf}`,
  separation: `demucs-${MODEL_VERSIONS.demucs}`,
  vocals:     `crepe-${MODEL_VERSIONS.crepe}`,
};

// ─── Multer ───────────────────────────────────────────────────────────────────
const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOADS_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, `${uuidv4()}${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 200 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const allowed = [".wav", ".mp3", ".flac", ".aiff", ".m4a", ".ogg"];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error(`Unsupported file type: ${ext}`));
  },
});

// ─── Helpers ─────────────────────────────────────────────────────────────────
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

/** Update job in DB and broadcast over WebSocket. */
async function updateJob(
  jobId: string,
  projectId: number,
  update: {
    status?: string;
    progress?: number;
    currentStep?: string;
    isMock?: boolean;
    errorMessage?: string;
    errorCode?: string;
    startedAt?: Date;
    finishedAt?: Date;
  },
) {
  await db.update(jobsTable)
    .set({ ...update, updatedAt: new Date() } as Parameters<typeof db.update>[0]["set"])
    .where(eq(jobsTable.jobId, jobId));
  broadcastJobUpdate(jobId, projectId, update);
}

/** Mark job as started (sets startedAt + running status). */
async function startJob(jobId: string, projectId: number, firstStep: string) {
  await updateJob(jobId, projectId, {
    status: "running",
    progress: 1,
    currentStep: firstStep,
    startedAt: new Date(),
  });
}

/** Mark job as failed with errorCode and finishedAt. */
async function failJobNoPython(jobId: string, projectId: number, err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  await updateJob(jobId, projectId, {
    status: "failed",
    progress: 0,
    currentStep: "Python backend unavailable",
    errorMessage: msg,
    errorCode: "PYTHON_UNAVAILABLE",
    finishedAt: new Date(),
  });
}

function serializeProject(p: typeof projectsTable.$inferSelect) {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    status: p.status,
    audioFileName: p.audioFileName,
    audioFilePath: p.audioFilePath,
    audioDurationSeconds: p.audioDurationSeconds,
    audioSampleRate: p.audioSampleRate,
    audioChannels: p.audioChannels,
    audioCodec: p.audioCodec,
    userCorrections: p.userCorrections ?? null,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
  };
}

function serializeJob(j: typeof jobsTable.$inferSelect) {
  return {
    jobId: j.jobId,
    projectId: j.projectId,
    type: j.type,
    status: j.status,
    progress: j.progress,
    currentStep: j.currentStep,
    isMock: j.isMock ?? false,
    errorMessage: j.errorMessage ?? null,
    errorCode: j.errorCode ?? null,
    inputPayload: j.inputPayload ?? null,
    resultData: j.resultData ?? null,
    warnings: j.warnings ?? null,
    startedAt: j.startedAt ?? null,
    finishedAt: j.finishedAt ?? null,
    createdAt: j.createdAt,
    updatedAt: j.updatedAt,
  };
}

// ─── Mock Mode Endpoint ───────────────────────────────────────────────────────

// GET /api/projects/mock-mode
// Returns the current MOCK_MODE flag so the frontend can display a banner on load.
router.get("/mock-mode", (_req, res) => {
  res.json({
    isMock: MOCK_MODE,
    mockMode: MOCK_MODE,
    pipelineVersion: PIPELINE_VERSION,
    modelVersions: MODEL_VERSIONS,
    message: MOCK_MODE
      ? "Running in MOCK MODE — results are simulated (dev only)"
      : "Running against live Python backend",
  });
});

// ─── Projects CRUD ────────────────────────────────────────────────────────────

// GET /api/projects  — supports ?page=1&limit=20
router.get("/", async (req, res) => {
  const page  = Math.max(1, parseInt(req.query.page  as string) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit as string) || 20));
  const offset = (page - 1) * limit;

  const [projects, [{ total }]] = await Promise.all([
    db.select().from(projectsTable)
      .orderBy(desc(projectsTable.createdAt))
      .limit(limit)
      .offset(offset),
    db.select({ total: count() }).from(projectsTable),
  ]);

  const pages = Math.ceil(Number(total) / limit);
  res.json({
    projects: projects.map(serializeProject),
    pagination: { page, limit, total: Number(total), pages },
  });
});

// POST /api/projects
router.post("/", async (req, res) => {
  const { name, description } = req.body;
  if (!name?.trim()) {
    res.status(400).json({ error: "name is required" });
    return;
  }
  const [project] = await db.insert(projectsTable).values({ name: name.trim(), description }).returning();
  res.status(201).json(serializeProject(project));
});

// GET /api/projects/:id
router.get("/:id", async (req, res) => {
  const id = parseProjectId(req, res);
  if (id === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, id));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }
  res.json(serializeProject(project));
});

// DELETE /api/projects/:id
router.delete("/:id", async (req, res) => {
  const id = parseProjectId(req, res);
  if (id === null) return;
  await db.delete(projectsTable).where(eq(projectsTable.id, id));
  res.status(204).send();
});

// ─── Upload ───────────────────────────────────────────────────────────────────

// POST /api/projects/:id/upload
router.post("/:id/upload", upload.single("file"), async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const file = req.file;
  if (!file) { res.status(400).json({ error: "No file provided" }); return; }

  const jobId = `upload-${uuidv4()}`;

  await db.update(projectsTable)
    .set({ audioFileName: file.originalname, audioFilePath: file.path, status: "uploading", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));

  await db.insert(jobsTable).values({
    jobId, projectId, type: "upload", status: "completed", progress: 100, currentStep: "Upload complete",
  });

  await db.update(projectsTable)
    .set({ status: "created", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));

  broadcastJobUpdate(jobId, projectId, { status: "completed", progress: 100, currentStep: "Upload complete" });

  res.json({ jobId, projectId, type: "upload", status: "completed", progress: 100, currentStep: "Upload complete", createdAt: new Date() });
});

// ─── Analysis ─────────────────────────────────────────────────────────────────

// POST /api/projects/:id/analyze
router.post("/:id/analyze", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }
  if (!project.audioFilePath && !MOCK_MODE) { res.status(400).json({ error: "No audio file uploaded yet" }); return; }

  const jobId = `analysis-${uuidv4()}`;
  await db.insert(jobsTable).values({ jobId, projectId, type: "analysis", status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

  // Fire-and-forget: call Python or simulate
  (async () => {
    try {
      if (MOCK_MODE) {
        await runSimulatedAnalysis(jobId, projectId);
      } else {
        await callPythonBackend("/analyze", {
          job_id: jobId,
          project_id: projectId,
          audio_file_path: project.audioFilePath,
          pipeline_version: PIPELINE_VERSION,
        });
      }
    } catch (err) {
      console.error("[analyze] pipeline error:", err);
      try {
        await failJobNoPython(jobId, projectId, err);
      } catch (failErr) {
        console.error("[analyze] failed to mark job as failed (project may have been deleted):", failErr);
      }
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// GET /api/projects/:id/analysis
router.get("/:id/analysis", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [result] = await db.select().from(analysisResultsTable).where(eq(analysisResultsTable.projectId, projectId));
  if (!result) { res.status(404).json({ error: "Analysis not ready" }); return; }
  const rhythmData = result.rhythmData as Record<string, unknown> | null;
  const analysisIsMock = !!(rhythmData?.isMock);
  res.json({
    projectId: result.projectId,
    rhythm: result.rhythmData,
    key: result.keyData,
    chords: result.chordsData,
    melody: result.melodyData,
    structure: result.structureData,
    waveformData: result.waveformData,
    vocals: result.vocalsData,
    sourceSeparation: result.sourceSeparationData,
    tonalTimeline: result.tonalTimelineData,
    confidenceData: result.confidenceData,
    pipelineVersion: result.pipelineVersion ?? PIPELINE_VERSION,
    modelVersions: analysisIsMock ? null : MODEL_VERSIONS,
    isMock: analysisIsMock,
    createdAt: result.createdAt,
    updatedAt: result.updatedAt,
  });
});

// ─── Manual Corrections ───────────────────────────────────────────────────────

// POST /api/projects/:id/corrections  — store user overrides for analysis data
router.post("/:id/corrections", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }

  // Allowed correction fields
  const { bpm, timeSignature, globalKey, mode, chords } = req.body as Record<string, unknown>;
  const corrections: Record<string, unknown> = {};
  if (bpm !== undefined) corrections.bpm = Number(bpm);
  if (timeSignature !== undefined) corrections.timeSignature = timeSignature;
  if (globalKey !== undefined) corrections.globalKey = String(globalKey);
  if (mode !== undefined) corrections.mode = String(mode);
  if (chords !== undefined) corrections.chords = chords;
  corrections.correctedAt = new Date().toISOString();

  // Merge into analysis_results if it exists
  const [analysis] = await db.select().from(analysisResultsTable).where(eq(analysisResultsTable.projectId, projectId));
  if (analysis) {
    const updatedRhythm = { ...(analysis.rhythmData as Record<string, unknown> || {}) };
    const updatedKey = { ...(analysis.keyData as Record<string, unknown> || {}) };
    if (corrections.bpm) updatedRhythm.bpm = corrections.bpm;
    if (corrections.timeSignature) updatedRhythm.timeSignature = corrections.timeSignature;
    if (corrections.globalKey) updatedKey.globalKey = corrections.globalKey;
    if (corrections.mode) updatedKey.mode = corrections.mode;
    await db.update(analysisResultsTable)
      .set({ rhythmData: updatedRhythm, keyData: updatedKey, updatedAt: new Date() })
      .where(eq(analysisResultsTable.projectId, projectId));
  }

  // Also store on the project row for quick access
  await db.execute(
    `UPDATE projects SET updated_at = NOW() WHERE id = ${projectId}`
  );

  res.json({ ok: true, corrections, appliedToAnalysis: !!analysis });
});

// ─── Lock System ─────────────────────────────────────────────────────────────
// STEP 15: Lock individual components to prevent regeneration.
// Lock keys: harmony, structure, melody, tracks, key, chords, bpm

// GET /api/projects/:id/locks
router.get("/:id/locks", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }
  res.json({ locks: (project as any).locks ?? {} });
});

// PUT /api/projects/:id/locks  — replace the full lock state
router.put("/:id/locks", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }

  const allowed = new Set(["harmony", "structure", "melody", "tracks", "key", "chords", "bpm"]);
  const body = req.body as Record<string, boolean>;
  const locks: Record<string, boolean> = {};
  for (const [k, v] of Object.entries(body)) {
    if (allowed.has(k) && typeof v === "boolean") locks[k] = v;
  }

  await db.update(projectsTable).set({ userCorrections: { ...(project.userCorrections as object ?? {}), locks }, updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
  res.json({ locks });
});

// PATCH /api/projects/:id/locks/:component — toggle a single lock
router.patch("/:id/locks/:component", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { component } = req.params;
  const allowed = new Set(["harmony", "structure", "melody", "tracks", "key", "chords", "bpm"]);
  if (!allowed.has(component)) { res.status(400).json({ error: `Unknown lock component: ${component}` }); return; }

  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }

  const { locked } = req.body as { locked: boolean };
  if (typeof locked !== "boolean") { res.status(400).json({ error: "locked must be boolean" }); return; }

  const currentCorrections = (project.userCorrections as Record<string, unknown>) ?? {};
  const currentLocks = (currentCorrections.locks as Record<string, boolean>) ?? {};
  const newLocks = { ...currentLocks, [component]: locked };

  await db.update(projectsTable).set({ userCorrections: { ...currentCorrections, locks: newLocks }, updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
  res.json({ component, locked, locks: newLocks });
});

// POST /api/projects/:id/regenerate-section — mark section for regeneration
router.post("/:id/regenerate-section", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { sectionLabel, sectionIndex } = req.body as { sectionLabel?: string; sectionIndex?: number };
  if (!sectionLabel && sectionIndex === undefined) {
    res.status(400).json({ error: "sectionLabel or sectionIndex required" });
    return;
  }

  const [analysis] = await db.select().from(analysisResultsTable).where(eq(analysisResultsTable.projectId, projectId));
  if (!analysis) { res.status(404).json({ error: "Analysis not ready" }); return; }

  const structureData = analysis.structureData as Record<string, unknown> | null;
  const sections: unknown[] = (structureData?.sections as unknown[]) ?? [];
  const updated = sections.map((s: any, i: number) => {
    const match = sectionIndex !== undefined ? i === sectionIndex : s.label === sectionLabel;
    return match ? { ...s, regenerate: true } : s;
  });

  await db.update(analysisResultsTable)
    .set({ structureData: { ...structureData, sections: updated }, updatedAt: new Date() })
    .where(eq(analysisResultsTable.projectId, projectId));

  res.json({ ok: true, markedSections: updated.filter((s: any) => s.regenerate).length });
});

// ─── Arrangement ──────────────────────────────────────────────────────────────

// POST /api/projects/:id/arrangement
router.post("/:id/arrangement", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { styleId, instruments, density, humanize, tempoFactor, personaId } = req.body;

  const jobId = `arrangement-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "arrangement", status: "queued", progress: 0,
    currentStep: "Queued", isMock: MOCK_MODE,
    inputPayload: { styleId, personaId: personaId ?? null, density, humanize, tempoFactor },
  });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

  (async () => {
    try {
      if (MOCK_MODE) {
        await runSimulatedArrangement(jobId, projectId, styleId || "pop");
        return;
      }
      await callPythonBackend("/arrange", {
        job_id: jobId,
        project_id: projectId,
        style_id: styleId || "pop",
        instruments: instruments || null,
        density: density ?? 0.7,
        humanize: humanize ?? true,
        tempo_factor: tempoFactor ?? 1.0,
        persona_id: personaId ?? null,
        pipeline_version: PIPELINE_VERSION,
      });
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// POST /api/projects/:id/arrangement/section/:label/regenerate
// Regenerates only the tracks for a specific section label (mock: replaces track notes for that section)
router.post("/:id/arrangement/section/:label/regenerate", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { label } = req.params;
  const { styleId, personaId } = req.body;

  const [arr] = await db.select().from(arrangementsTable)
    .where(and(eq(arrangementsTable.projectId, projectId), eq(arrangementsTable.isCurrent, true)))
    .limit(1);
  if (!arr) { res.status(404).json({ error: "No current arrangement" }); return; }

  const jobId = `regen-section-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "arrangement", status: "queued", progress: 0,
    currentStep: `Regenerating section: ${label}`, isMock: MOCK_MODE,
    inputPayload: { sectionLabel: label, styleId: styleId ?? arr.styleId, personaId: personaId ?? null },
  });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: `Queued section regen: ${label}`, isMock: MOCK_MODE });

  (async () => {
    try {
      if (MOCK_MODE) {
        await startJob(jobId, projectId, `[MOCK] Regenerating section: ${label}`);
        await new Promise(r => setTimeout(r, 800));
        await updateJob(jobId, projectId, { status: "running", progress: 50, currentStep: `[MOCK] Writing notes for ${label}`, isMock: true });
        await new Promise(r => setTimeout(r, 800));
        await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: `[MOCK] Section ${label} regenerated`, isMock: true, finishedAt: new Date() });
        return;
      }
      await callPythonBackend("/arrange/section", {
        job_id: jobId, project_id: projectId,
        section_label: label,
        style_id: styleId ?? arr.styleId,
        persona_id: personaId ?? null,
      });
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// POST /api/projects/:id/arrangement/track/:trackId/regenerate
// Regenerates only a specific instrument track in the current arrangement
router.post("/:id/arrangement/track/:trackId/regenerate", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { trackId } = req.params;
  const { styleId, personaId } = req.body;

  const [arr] = await db.select().from(arrangementsTable)
    .where(and(eq(arrangementsTable.projectId, projectId), eq(arrangementsTable.isCurrent, true)))
    .limit(1);
  if (!arr) { res.status(404).json({ error: "No current arrangement" }); return; }

  const jobId = `regen-track-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "arrangement", status: "queued", progress: 0,
    currentStep: `Regenerating track: ${trackId}`, isMock: MOCK_MODE,
    inputPayload: { trackId, styleId: styleId ?? arr.styleId, personaId: personaId ?? null },
  });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: `Queued track regen: ${trackId}`, isMock: MOCK_MODE });

  (async () => {
    try {
      if (MOCK_MODE) {
        await startJob(jobId, projectId, `[MOCK] Regenerating track: ${trackId}`);
        await new Promise(r => setTimeout(r, 600));
        await updateJob(jobId, projectId, { status: "running", progress: 60, currentStep: `[MOCK] Generating new ${trackId} pattern`, isMock: true });
        await new Promise(r => setTimeout(r, 600));
        await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: `[MOCK] Track ${trackId} regenerated`, isMock: true, finishedAt: new Date() });
        return;
      }
      await callPythonBackend("/arrange/track", {
        job_id: jobId, project_id: projectId,
        track_id: trackId,
        style_id: styleId ?? arr.styleId,
        persona_id: personaId ?? null,
      });
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// GET /api/projects/:id/arrangement  — returns the current (latest) arrangement version
router.get("/:id/arrangement", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [result] = await db.select().from(arrangementsTable)
    .where(and(eq(arrangementsTable.projectId, projectId), eq(arrangementsTable.isCurrent, true)))
    .orderBy(desc(arrangementsTable.versionNumber))
    .limit(1);
  if (!result) { res.status(404).json({ error: "Arrangement not ready" }); return; }
  const arrMeta = result.generationMetadata as Record<string, unknown> | null;
  const arrIsMock = !!(arrMeta?.isMock);
  res.json({
    projectId: result.projectId,
    versionNumber: result.versionNumber,
    styleId: result.styleId,
    tracks: result.tracksData,
    totalDurationSeconds: result.totalDurationSeconds,
    arrangementPlan: result.arrangementPlan,
    generationMetadata: result.generationMetadata,
    isMock: arrIsMock,
    pipelineVersion: PIPELINE_VERSION,
    createdFromAudioHash: (arrMeta?.createdFromAudioHash as string | undefined) ?? null,
    createdAt: result.createdAt,
  });
});

// GET /api/projects/:id/arrangement/history  — all arrangement versions
router.get("/:id/arrangement/history", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const versions = await db.select().from(arrangementsTable)
    .where(eq(arrangementsTable.projectId, projectId))
    .orderBy(desc(arrangementsTable.versionNumber));
  res.json(versions.map(v => ({
    id: v.id,
    versionNumber: v.versionNumber,
    isCurrent: v.isCurrent,
    styleId: v.styleId,
    totalDurationSeconds: v.totalDurationSeconds,
    createdAt: v.createdAt,
  })));
});

// ─── Audio stream ─────────────────────────────────────────────────────────────

// GET /api/projects/:id/audio  (HTTP range-request streaming)
router.get("/:id/audio", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) return res.status(404).json({ error: "Project not found" });
  if (!project.audioFilePath || !fs.existsSync(project.audioFilePath)) {
    return res.status(404).json({ error: "No audio file" });
  }
  const stat = fs.statSync(project.audioFilePath);
  const ext = path.extname(project.audioFilePath).toLowerCase().slice(1);
  const mimeMap: Record<string, string> = {
    wav: "audio/wav", mp3: "audio/mpeg", flac: "audio/flac",
    aiff: "audio/aiff", m4a: "audio/mp4", ogg: "audio/ogg",
  };
  const mime = mimeMap[ext] || "audio/octet-stream";
  const range = req.headers.range;
  if (range) {
    const [startStr, endStr] = range.replace(/bytes=/, "").split("-");
    const start = parseInt(startStr, 10);
    const end = endStr ? parseInt(endStr, 10) : stat.size - 1;
    res.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${stat.size}`,
      "Accept-Ranges": "bytes",
      "Content-Length": end - start + 1,
      "Content-Type": mime,
    });
    fs.createReadStream(project.audioFilePath, { start, end }).pipe(res);
  } else {
    res.writeHead(200, {
      "Content-Length": stat.size,
      "Content-Type": mime,
      "Accept-Ranges": "bytes",
    });
    fs.createReadStream(project.audioFilePath).pipe(res);
  }
});

// ─── Generated files ──────────────────────────────────────────────────────────

// GET /api/projects/:id/files
router.get("/:id/files", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const files = await db.select().from(projectFilesTable)
    .where(eq(projectFilesTable.projectId, projectId))
    .orderBy(desc(projectFilesTable.createdAt));
  res.json(files.map(f => ({
    id: f.id, fileName: f.fileName, fileType: f.fileType,
    fileSizeBytes: f.fileSizeBytes, createdAt: f.createdAt,
  })));
});

// GET /api/projects/:id/files/:filename/download
router.get("/:id/files/:filename/download", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { filename } = req.params;
  const [file] = await db.select().from(projectFilesTable).where(
    and(eq(projectFilesTable.projectId, projectId), eq(projectFilesTable.fileName, filename))
  );
  if (!file) return res.status(404).json({ error: "File not found" });
  if (!fs.existsSync(file.filePath)) return res.status(410).json({ error: "File no longer on disk" });

  const mimeMap: Record<string, string> = {
    mid: "audio/midi", midi: "audio/midi",
    musicxml: "application/vnd.recordare.musicxml+xml",
    wav: "audio/wav", flac: "audio/flac", mp3: "audio/mpeg",
    txt: "text/plain", pdf: "application/pdf",
  };
  const mime = mimeMap[file.fileType] || "application/octet-stream";
  res.setHeader("Content-Disposition", `attachment; filename="${file.fileName}"`);
  res.setHeader("Content-Type", mime);
  if (file.fileSizeBytes) res.setHeader("Content-Length", file.fileSizeBytes);
  fs.createReadStream(file.filePath).pipe(res);
});

// ─── Render ───────────────────────────────────────────────────────────────────

// POST /api/projects/:id/render
router.post("/:id/render", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { formats = ["wav"] } = req.body;

  const jobId = `render-${uuidv4()}`;
  await db.insert(jobsTable).values({ jobId, projectId, type: "render", status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

  (async () => {
    if (MOCK_MODE) {
      const steps = [
        "[MOCK] Synthesizing instruments",
        "[MOCK] Mixing tracks",
        "[MOCK] Mastering (-14 LUFS)",
        "[MOCK] Writing audio files",
      ];
      for (let i = 0; i < steps.length; i++) {
        await new Promise(r => setTimeout(r, 2000));
        await updateJob(jobId, projectId, {
          status: "running",
          progress: Math.round((i + 1) / steps.length * 95),
          currentStep: steps[i],
          isMock: true,
        });
      }
      await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: "[MOCK] Render complete", isMock: true });
      return;
    }
    try {
      await callPythonBackend("/render", { job_id: jobId, project_id: projectId, formats });
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// ─── Export ───────────────────────────────────────────────────────────────────

// POST /api/projects/:id/export
router.post("/:id/export", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { formats = ["midi"] } = req.body;

  const jobId = `export-${uuidv4()}`;
  await db.insert(jobsTable).values({ jobId, projectId, type: "export", status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

  (async () => {
    try {
      if (MOCK_MODE) {
        await runSimulatedExport(jobId, projectId, formats);
        return;
      }
      await callPythonBackend("/export", { job_id: jobId, project_id: projectId, formats });
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// ═════════════════════════════════════════════════════════════════════════════
// MOCK SIMULATION HELPERS
// These run only when MOCK_MODE=true (development default).
// All steps are prefixed with [MOCK] so it is crystal-clear in the UI.
// Never remove this label — it is a product integrity requirement.
// ═════════════════════════════════════════════════════════════════════════════

async function runSimulatedAnalysis(jobId: string, projectId: number) {
  await startJob(jobId, projectId, "[MOCK] Loading audio");
  const steps = [
    { step: "[MOCK] Loading audio", progress: 10 },
    { step: "[MOCK] Separating sources (Demucs)", progress: 20 },
    { step: "[MOCK] Analyzing rhythm & tempo", progress: 35 },
    { step: "[MOCK] Detecting key & mode", progress: 50 },
    { step: "[MOCK] Analyzing chord progressions", progress: 65 },
    { step: "[MOCK] Extracting melody (pyin)", progress: 78 },
    { step: "[MOCK] Detecting song structure", progress: 88 },
    { step: "[MOCK] Finalizing results", progress: 95 },
  ];

  for (const { step, progress } of steps) {
    await new Promise(r => setTimeout(r, 2000));
    await updateJob(jobId, projectId, { status: "running", progress, currentStep: step, isMock: true });
    await db.update(projectsTable).set({ status: "analyzing", updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
  }

  const waveform = Array.from({ length: 1000 }, (_, i) => Math.abs(Math.sin(i * 0.1) * Math.random() * 0.8 + 0.1));
  const bpm = 120 + Math.floor(Math.random() * 40);
  const beatDuration = 60 / bpm;
  const totalDuration = 180;
  const beatGrid = Array.from({ length: Math.floor(totalDuration / beatDuration) }, (_, i) => parseFloat((i * beatDuration).toFixed(3)));
  const downbeats = beatGrid.filter((_, i) => i % 4 === 0);

  const globalKey = ["C", "Am", "G", "F", "D", "Em"][Math.floor(Math.random() * 6)];
  const keyMode = Math.random() > 0.4 ? "major" : "minor";
  const simChords = generateSimulatedChords(totalDuration, beatDuration);

  await db.delete(analysisResultsTable).where(eq(analysisResultsTable.projectId, projectId));
  await db.insert(analysisResultsTable).values({
    projectId,
    pipelineVersion: PIPELINE_VERSION,
    rhythmData: {
      bpm, timeSignatureNumerator: 4, timeSignatureDenominator: 4,
      beatGrid, downbeats,
      confidence: 0.88, isMock: true,
      model: MODEL_BY_TYPE.rhythm,
    },
    keyData: {
      globalKey, mode: keyMode,
      confidence: 0.85 + Math.random() * 0.1,
      alternatives: [{ key: globalKey === "C" ? "Am" : "C", mode: keyMode === "major" ? "minor" : "major", confidence: 0.62 }],
      modulations: [],
      isMock: true,
      model: MODEL_BY_TYPE.key,
    },
    chordsData: {
      chords: simChords,
      leadSheet: simChords.slice(0, 8).map((c: {chord: string}) => c.chord).join(" | "),
      isMock: true,
      model: MODEL_BY_TYPE.chords,
    },
    melodyData: {
      notes: generateSimulatedMelody(totalDuration),
      inferredHarmony: ["C - Am - F - G", "C - F - Am - G"],
      isMock: true,
      model: MODEL_BY_TYPE.melody,
    },
    structureData: {
      sections: [
        { label: "intro",  startTime: 0,   endTime: 16,  confidence: 0.88, isMock: true },
        { label: "verse",  startTime: 16,  endTime: 48,  confidence: 0.82, isMock: true },
        { label: "chorus", startTime: 48,  endTime: 80,  confidence: 0.91, isMock: true },
        { label: "verse",  startTime: 80,  endTime: 112, confidence: 0.79, isMock: true },
        { label: "chorus", startTime: 112, endTime: 144, confidence: 0.93, isMock: true },
        { label: "bridge", startTime: 144, endTime: 160, confidence: 0.75, isMock: true },
        { label: "chorus", startTime: 160, endTime: 180, confidence: 0.89, isMock: true },
      ],
      isMock: true,
      model: MODEL_BY_TYPE.structure,
    },
    waveformData: waveform,
  });

  await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: "[MOCK] Analysis complete", isMock: true, finishedAt: new Date() });
  await db.update(projectsTable).set({ status: "analyzed", updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
}

function generateSimulatedChords(duration: number, beatDuration: number) {
  const progressions = [
    ["C", "Am", "F", "G"], ["Am", "F", "C", "G"],
    ["G", "D", "Em", "C"], ["F", "G", "Am", "C"],
  ];
  const prog = progressions[Math.floor(Math.random() * progressions.length)];
  const chords = [];
  let t = 0; let i = 0;
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
    t += chordDuration; i++;
  }
  return chords;
}

function generateSimulatedMelody(duration: number) {
  const notes = [];
  const scale = [60, 62, 64, 65, 67, 69, 71, 72];
  let t = 0;
  while (t < duration * 0.6) {
    const noteDuration = [0.25, 0.5, 1.0][Math.floor(Math.random() * 3)];
    const pitch = scale[Math.floor(Math.random() * scale.length)];
    notes.push({
      startTime: parseFloat(t.toFixed(3)),
      endTime: parseFloat((t + noteDuration * 0.9).toFixed(3)),
      pitch, frequency: parseFloat((440 * Math.pow(2, (pitch - 69) / 12)).toFixed(2)),
      velocity: 65 + Math.floor(Math.random() * 30),
    });
    t += noteDuration + (Math.random() > 0.7 ? 0.1 : 0);
  }
  return notes;
}

async function runSimulatedArrangement(jobId: string, projectId: number, styleId: string) {
  await startJob(jobId, projectId, "[MOCK] Loading analysis data");
  const steps = [
    { step: "[MOCK] Loading analysis data", progress: 20 },
    { step: "[MOCK] Generating drum pattern", progress: 40 },
    { step: "[MOCK] Creating bass line", progress: 55 },
    { step: "[MOCK] Building chord voicings", progress: 70 },
    { step: "[MOCK] Adding orchestration", progress: 85 },
    { step: "[MOCK] Humanizing performance", progress: 95 },
  ];

  for (const { step, progress } of steps) {
    await new Promise(r => setTimeout(r, 1500));
    await updateJob(jobId, projectId, { status: "running", progress, currentStep: step, isMock: true });
  }

  const totalDuration = 180;
  const bpm = 120;
  const tracks = [
    generateDrumTrack(totalDuration, bpm),
    generateBassTrack(totalDuration, bpm),
    generatePianoTrack(totalDuration, bpm),
    generateStringsTrack(totalDuration, bpm),
  ];

  // Versioning: mark previous versions as not current
  await db.update(arrangementsTable)
    .set({ isCurrent: false })
    .where(eq(arrangementsTable.projectId, projectId));

  // Get next version number
  const existing = await db.select().from(arrangementsTable)
    .where(eq(arrangementsTable.projectId, projectId))
    .orderBy(desc(arrangementsTable.versionNumber))
    .limit(1);
  const nextVersion = (existing[0]?.versionNumber ?? 0) + 1;

  await db.insert(arrangementsTable).values({
    projectId,
    styleId,
    tracksData: tracks,
    totalDurationSeconds: totalDuration,
    isCurrent: true,
    versionNumber: nextVersion,
    generationMetadata: { isMock: true, bpm, style: styleId },
  });

  await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: "[MOCK] Arrangement complete", isMock: true, finishedAt: new Date() });
  await db.update(projectsTable).set({ status: "arranged", updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
}

function generateDrumTrack(duration: number, bpm: number) {
  const bd = 60 / bpm;
  const notes = [];
  for (let t = 0; t < duration; t += bd) {
    const b = Math.floor(t / bd) % 4;
    if (b === 0) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 36, velocity: 100 });
    if (b === 2) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 36, velocity: 88 });
    if (b === 1 || b === 3) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.1, pitch: 38, velocity: 95 });
    notes.push({ startTime: parseFloat(t.toFixed(3)), duration: 0.05, pitch: 42, velocity: 60 });
    notes.push({ startTime: parseFloat((t + bd / 2).toFixed(3)), duration: 0.05, pitch: 42, velocity: 50 });
  }
  return { id: "drums", name: "Drums", instrument: "Drum Kit", channel: 9, color: "#e74c3c", notes, volume: 0.85, pan: 0, muted: false, soloed: false };
}

function generateBassTrack(duration: number, bpm: number) {
  const roots = [36, 33, 29, 31];
  const cd = (60 / bpm) * 4;
  const notes = [];
  let t = 0; let i = 0;
  while (t < duration) {
    notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((cd * 0.45).toFixed(3)), pitch: roots[i % 4], velocity: 88 });
    notes.push({ startTime: parseFloat((t + cd * 0.5).toFixed(3)), duration: parseFloat((cd * 0.4).toFixed(3)), pitch: roots[i % 4] + 7, velocity: 75 });
    t += cd; i++;
  }
  return { id: "bass", name: "Bass", instrument: "Electric Bass", channel: 1, color: "#8e44ad", notes, volume: 0.80, pan: -0.1, muted: false, soloed: false };
}

function generatePianoTrack(duration: number, bpm: number) {
  const chords = [[48, 52, 55], [45, 48, 52], [41, 45, 48], [43, 47, 50]];
  const cd = (60 / bpm) * 4;
  const notes = [];
  let t = 0; let i = 0;
  while (t < duration) {
    for (const p of chords[i % 4]) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((cd * 0.85).toFixed(3)), pitch: p + 12, velocity: 70 });
    t += cd; i++;
  }
  return { id: "piano", name: "Piano", instrument: "Grand Piano", channel: 2, color: "#2980b9", notes, volume: 0.70, pan: 0.1, muted: false, soloed: false };
}

function generateStringsTrack(duration: number, bpm: number) {
  const chords = [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]];
  const cd = (60 / bpm) * 4;
  const notes = [];
  let t = 0; let i = 0;
  while (t < duration) {
    for (const p of chords[i % 4]) notes.push({ startTime: parseFloat(t.toFixed(3)), duration: parseFloat((cd * 0.98).toFixed(3)), pitch: p, velocity: 55 });
    t += cd; i++;
  }
  return { id: "strings", name: "Strings", instrument: "String Ensemble", channel: 4, color: "#f39c12", notes, volume: 0.60, pan: 0, muted: false, soloed: false };
}

async function runSimulatedExport(jobId: string, projectId: number, formats: string[]) {
  const fmtList = Array.isArray(formats) ? formats : ["midi"];
  await startJob(jobId, projectId, `[MOCK] Exporting ${fmtList[0]?.toUpperCase() ?? "MIDI"}`);
  for (let i = 0; i < fmtList.length; i++) {
    await new Promise(r => setTimeout(r, 1000));
    const progress = Math.round(((i + 1) / fmtList.length) * 100);
    await updateJob(jobId, projectId, {
      status: "running", progress,
      currentStep: `[MOCK] Exporting ${fmtList[i].toUpperCase()}`,
      isMock: true,
    });
  }
  await updateJob(jobId, projectId, { status: "completed", progress: 100, currentStep: "[MOCK] Export complete", isMock: true, finishedAt: new Date() });
  await db.update(projectsTable).set({ status: "done", updatedAt: new Date() }).where(eq(projectsTable.id, projectId));
}

export default router;
