/**
 * Mock simulation helpers — run only when MOCK_MODE=true (development default).
 * All step labels are prefixed with [MOCK] so it is crystal-clear in the UI.
 * NEVER remove the [MOCK] prefix — it is a product integrity requirement.
 */

import { eq, desc } from "drizzle-orm";
import {
  db,
  projectsTable,
  jobsTable,
  analysisResultsTable,
  arrangementsTable,
} from "@workspace/db";
import { updateJob, startJob, MODEL_BY_TYPE, PIPELINE_VERSION } from "./project-helpers";

// ─── Analysis Simulation ─────────────────────────────────────────────────────

export async function runSimulatedAnalysis(jobId: string, projectId: number) {
  await startJob(jobId, projectId, "[MOCK] Loading audio");
  const steps = [
    { step: "[MOCK] Loading audio",                    progress: 10 },
    { step: "[MOCK] Separating sources (Demucs)",      progress: 20 },
    { step: "[MOCK] Analyzing rhythm & tempo",         progress: 35 },
    { step: "[MOCK] Detecting key & mode",             progress: 50 },
    { step: "[MOCK] Analyzing chord progressions",     progress: 65 },
    { step: "[MOCK] Extracting melody (pyin)",         progress: 78 },
    { step: "[MOCK] Detecting song structure",         progress: 88 },
    { step: "[MOCK] Finalizing results",               progress: 95 },
  ];

  for (const { step, progress } of steps) {
    await new Promise(r => setTimeout(r, 2000));
    await updateJob(jobId, projectId, { status: "running", progress, currentStep: step, isMock: true });
    await db.update(projectsTable)
      .set({ status: "analyzing", updatedAt: new Date() })
      .where(eq(projectsTable.id, projectId));
  }

  const waveform = Array.from({ length: 1000 }, (_, i) =>
    Math.abs(Math.sin(i * 0.1) * Math.random() * 0.8 + 0.1),
  );
  const bpm = 120 + Math.floor(Math.random() * 40);
  const beatDuration = 60 / bpm;
  const totalDuration = 180;
  const beatGrid = Array.from(
    { length: Math.floor(totalDuration / beatDuration) },
    (_, i) => parseFloat((i * beatDuration).toFixed(3)),
  );
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
      leadSheet: simChords.slice(0, 8).map((c: { chord: string }) => c.chord).join(" | "),
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

  await updateJob(jobId, projectId, {
    status: "completed", progress: 100,
    currentStep: "[MOCK] Analysis complete",
    isMock: true, finishedAt: new Date(),
  });
  await db.update(projectsTable)
    .set({ status: "analyzed", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
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
      pitch,
      frequency: parseFloat((440 * Math.pow(2, (pitch - 69) / 12)).toFixed(2)),
      velocity: 65 + Math.floor(Math.random() * 30),
    });
    t += noteDuration + (Math.random() > 0.7 ? 0.1 : 0);
  }
  return notes;
}

// ─── Arrangement Simulation ───────────────────────────────────────────────────

export async function runSimulatedArrangement(
  jobId: string,
  projectId: number,
  styleId: string,
) {
  await startJob(jobId, projectId, "[MOCK] Loading analysis data");
  const steps = [
    { step: "[MOCK] Loading analysis data",   progress: 20 },
    { step: "[MOCK] Generating drum pattern", progress: 40 },
    { step: "[MOCK] Creating bass line",       progress: 55 },
    { step: "[MOCK] Building chord voicings", progress: 70 },
    { step: "[MOCK] Adding orchestration",    progress: 85 },
    { step: "[MOCK] Humanizing performance",  progress: 95 },
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

  await db.update(arrangementsTable)
    .set({ isCurrent: false })
    .where(eq(arrangementsTable.projectId, projectId));

  const existing = await db
    .select()
    .from(arrangementsTable)
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

  await updateJob(jobId, projectId, {
    status: "completed", progress: 100,
    currentStep: "[MOCK] Arrangement complete",
    isMock: true, finishedAt: new Date(),
  });
  await db.update(projectsTable)
    .set({ status: "arranged", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
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

// ─── Export Simulation ────────────────────────────────────────────────────────

export async function runSimulatedExport(
  jobId: string,
  projectId: number,
  formats: string[],
) {
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
  await updateJob(jobId, projectId, {
    status: "completed", progress: 100,
    currentStep: "[MOCK] Export complete",
    isMock: true, finishedAt: new Date(),
  });
  await db.update(projectsTable)
    .set({ status: "done", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
}
