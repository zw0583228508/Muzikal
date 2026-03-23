/**
 * Export and render pipeline routes.
 * Routes: POST /:id/export, POST /:id/export/bundle, POST /:id/render
 */

import { Router } from "express";
import { eq } from "drizzle-orm";
import { db, jobsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "../lib/websocket";
import { parseProjectId } from "../lib/validate";
import { logger } from "../lib/logger";
import {
  MOCK_MODE,
  PYTHON_BACKEND,
  callPythonBackend,
  failJobNoPython,
  updateJob,
  requireProjectOwner,
  serializeJob,
} from "../lib/project-helpers";
import { runSimulatedExport } from "../lib/project-simulation";

const router = Router();

// POST /api/projects/:id/export
router.post("/:id/export", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { formats = ["midi"] } = req.body;

  const jobId = `export-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "export", status: "queued",
    progress: 0, currentStep: "Queued", isMock: MOCK_MODE,
  });
  broadcastJobUpdate(jobId, projectId, { status: "queued", progress: 0, currentStep: "Queued", isMock: MOCK_MODE });

  (async () => {
    try {
      if (MOCK_MODE) {
        await runSimulatedExport(jobId, projectId, formats);
        return;
      }
      await callPythonBackend("/export", { job_id: jobId, project_id: projectId, formats }, projectId);
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

// POST /api/projects/:id/export/bundle — ZIP of all exported files (proxied from Python)
router.post("/:id/export/bundle", requireProjectOwner, async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { formats = ["midi", "musicxml", "wav"] } = req.body;

  const pythonRes = await fetch(
    `${PYTHON_BACKEND}/python-api/projects/${projectId}/export/bundle`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formats }),
    }
  ).catch((err) => {
    logger.error({ projectId, err: String(err) }, "Export bundle fetch failed");
    return null;
  });

  if (!pythonRes || !pythonRes.ok) {
    const status = pythonRes?.status ?? 502;
    const body = pythonRes ? await pythonRes.text().catch(() => "") : "Python unreachable";
    logger.error({ projectId, status, body }, "Export bundle Python error");
    res.status(status === 404 ? 404 : 502).json({ error: "Bundle generation failed", detail: body });
    return;
  }

  res.setHeader("Content-Type", "application/zip");
  res.setHeader("Content-Disposition", `attachment; filename="project_${projectId}_bundle.zip"`);
  const buf = await pythonRes.arrayBuffer();
  res.send(Buffer.from(buf));
});

// POST /api/projects/:id/render
router.post("/:id/render", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { formats = ["wav"] } = req.body;

  const jobId = `render-${uuidv4()}`;
  await db.insert(jobsTable).values({
    jobId, projectId, type: "render", status: "queued",
    progress: 0, currentStep: "Queued", isMock: MOCK_MODE,
  });
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
      await updateJob(jobId, projectId, {
        status: "completed", progress: 100,
        currentStep: "[MOCK] Render complete", isMock: true,
      });
      return;
    }
    try {
      await callPythonBackend("/render", { job_id: jobId, project_id: projectId, formats }, projectId);
    } catch (err) {
      await failJobNoPython(jobId, projectId, err);
    }
  })();

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJob(job));
});

export default router;
