/**
 * Arrangement generation and regeneration routes.
 * Routes: POST /:id/arrangement, GET /:id/arrangement, GET /:id/arrangement/history,
 *         POST /:id/arrangement/section/:label/regenerate,
 *         POST /:id/arrangement/track/:trackId/regenerate
 */

import { Router } from "express";
import { eq, desc, and } from "drizzle-orm";
import { db, jobsTable, arrangementsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "../lib/websocket";
import { parseProjectId } from "../lib/validate";
import {
  MOCK_MODE,
  PIPELINE_VERSION,
  callPythonBackend,
  failJobNoPython,
  startJob,
  updateJob,
  serializeJob,
} from "../lib/project-helpers";
import { runSimulatedArrangement } from "../lib/project-simulation";

const router = Router();

// POST /api/projects/:id/arrangement
router.post("/:id/arrangement", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { styleId, instruments, density, humanize, tempoFactor, personaId, styleProfile } = req.body;

  const jobId = `arrangement-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "arrangement", status: "queued", progress: 0,
    currentStep: "Queued", isMock: MOCK_MODE,
    inputPayload: { styleId, personaId: personaId ?? null, density, humanize, tempoFactor, hasStyleProfile: !!styleProfile },
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
        style_profile: styleProfile ?? null,
        pipeline_version: PIPELINE_VERSION,
      }, projectId);
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
  const [result] = await db
    .select()
    .from(arrangementsTable)
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
  const versions = await db
    .select()
    .from(arrangementsTable)
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

// POST /api/projects/:id/arrangement/restore/:versionId  — set a past version as current
router.post("/:id/arrangement/restore/:versionId", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const versionId = parseInt(req.params.versionId, 10);
  if (isNaN(versionId)) { res.status(400).json({ error: "Invalid versionId" }); return; }

  // Check this version belongs to this project
  const [target] = await db
    .select()
    .from(arrangementsTable)
    .where(and(eq(arrangementsTable.id, versionId), eq(arrangementsTable.projectId, projectId)));
  if (!target) { res.status(404).json({ error: "Version not found for this project" }); return; }

  // Clear current flag on all versions, then set it on the target
  await db.update(arrangementsTable)
    .set({ isCurrent: false })
    .where(eq(arrangementsTable.projectId, projectId));
  await db.update(arrangementsTable)
    .set({ isCurrent: true })
    .where(eq(arrangementsTable.id, versionId));

  res.json({ ok: true, restoredVersionNumber: target.versionNumber, styleId: target.styleId });
});

// POST /api/projects/:id/arrangement/section/:label/regenerate
router.post("/:id/arrangement/section/:label/regenerate", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { label } = req.params;
  const { styleId, personaId } = req.body;

  const [arr] = await db
    .select()
    .from(arrangementsTable)
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
      }, projectId);
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// POST /api/projects/:id/arrangement/track/:trackId/regenerate
router.post("/:id/arrangement/track/:trackId/regenerate", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { trackId } = req.params;
  const { styleId, personaId } = req.body;

  const [arr] = await db
    .select()
    .from(arrangementsTable)
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
      }, projectId);
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

export default router;
