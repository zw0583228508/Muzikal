/**
 * Analysis, corrections, and lock routes.
 * Routes: POST /:id/analyze, GET /:id/analysis, POST /:id/corrections,
 *         GET|PUT|PATCH /:id/locks, POST /:id/regenerate-section
 */

import { Router } from "express";
import { eq } from "drizzle-orm";
import { db, projectsTable, jobsTable, analysisResultsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "../lib/websocket";
import { parseProjectId } from "../lib/validate";
import {
  MOCK_MODE,
  PIPELINE_VERSION,
  MODEL_VERSIONS,
  callPythonBackend,
  failJobNoPython,
  serializeJob,
} from "../lib/project-helpers";
import { runSimulatedAnalysis } from "../lib/project-simulation";

const router = Router();

// POST /api/projects/:id/analyze
router.post("/:id/analyze", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }
  if (!project.audioFilePath && !MOCK_MODE) {
    res.status(400).json({ error: "No audio file uploaded yet" });
    return;
  }

  const jobId = `analysis-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "analysis", status: "queued",
    progress: 0, currentStep: "Queued", isMock: MOCK_MODE,
  });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

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
        }, projectId);
      }
    } catch (err) {
      console.error("[analyze] pipeline error:", err);
      try {
        await failJobNoPython(jobId, projectId, err);
      } catch (failErr) {
        console.error("[analyze] failed to mark job as failed:", failErr);
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
  const [result] = await db
    .select()
    .from(analysisResultsTable)
    .where(eq(analysisResultsTable.projectId, projectId));
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

// POST /api/projects/:id/corrections  — store user overrides for analysis data
router.post("/:id/corrections", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }

  const { bpm, timeSignature, globalKey, mode, chords } = req.body as Record<string, unknown>;
  const corrections: Record<string, unknown> = {};
  if (bpm !== undefined) corrections.bpm = Number(bpm);
  if (timeSignature !== undefined) corrections.timeSignature = timeSignature;
  if (globalKey !== undefined) corrections.globalKey = String(globalKey);
  if (mode !== undefined) corrections.mode = String(mode);
  if (chords !== undefined) corrections.chords = chords;
  corrections.correctedAt = new Date().toISOString();

  const [analysis] = await db
    .select()
    .from(analysisResultsTable)
    .where(eq(analysisResultsTable.projectId, projectId));
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

  await db.execute(
    `UPDATE projects SET updated_at = NOW() WHERE id = ${projectId}`
  );

  res.json({ ok: true, corrections, appliedToAnalysis: !!analysis });
});

// ─── Lock System ─────────────────────────────────────────────────────────────

const LOCK_COMPONENTS = new Set(["harmony", "structure", "melody", "tracks", "key", "chords", "bpm"]);

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

  const body = req.body as Record<string, boolean>;
  const locks: Record<string, boolean> = {};
  for (const [k, v] of Object.entries(body)) {
    if (LOCK_COMPONENTS.has(k) && typeof v === "boolean") locks[k] = v;
  }

  await db.update(projectsTable)
    .set({ userCorrections: { ...(project.userCorrections as object ?? {}), locks }, updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
  res.json({ locks });
});

// PATCH /api/projects/:id/locks/:component — toggle a single lock
router.patch("/:id/locks/:component", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { component } = req.params;
  if (!LOCK_COMPONENTS.has(component)) {
    res.status(400).json({ error: `Unknown lock component: ${component}` });
    return;
  }

  const [project] = await db.select().from(projectsTable).where(eq(projectsTable.id, projectId));
  if (!project) { res.status(404).json({ error: "Project not found" }); return; }

  const { locked } = req.body as { locked: boolean };
  if (typeof locked !== "boolean") {
    res.status(400).json({ error: "locked must be boolean" });
    return;
  }

  const currentCorrections = (project.userCorrections as Record<string, unknown>) ?? {};
  const currentLocks = (currentCorrections.locks as Record<string, boolean>) ?? {};
  const newLocks = { ...currentLocks, [component]: locked };

  await db.update(projectsTable)
    .set({ userCorrections: { ...currentCorrections, locks: newLocks }, updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));
  res.json({ component, locked, locks: newLocks });
});

// POST /api/projects/:id/regenerate-section
router.post("/:id/regenerate-section", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { sectionLabel, sectionIndex } = req.body as { sectionLabel?: string; sectionIndex?: number };
  if (!sectionLabel && sectionIndex === undefined) {
    res.status(400).json({ error: "sectionLabel or sectionIndex required" });
    return;
  }

  const [analysis] = await db
    .select()
    .from(analysisResultsTable)
    .where(eq(analysisResultsTable.projectId, projectId));
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

export default router;
