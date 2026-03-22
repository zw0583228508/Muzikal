import { Router, type IRouter } from "express";
import { eq } from "drizzle-orm";
import { db, jobsTable } from "@workspace/db";
import { broadcastJobUpdate } from "../lib/websocket.js";

const router: IRouter = Router();

function serializeJobFull(job: typeof jobsTable.$inferSelect) {
  return {
    jobId: job.jobId,
    projectId: job.projectId,
    type: job.type,
    status: job.status,
    progress: job.progress,
    currentStep: job.currentStep,
    isMock: job.isMock ?? false,
    errorMessage: job.errorMessage ?? null,
    errorCode: job.errorCode ?? null,
    inputPayload: job.inputPayload ?? null,
    resultData: job.resultData ?? null,
    warnings: job.warnings ?? null,
    processingMetadata: job.processingMetadata ?? null,
    startedAt: job.startedAt ?? null,
    finishedAt: job.finishedAt ?? null,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
  };
}

// GET /api/jobs/:jobId
router.get("/:jobId", async (req, res) => {
  const { jobId } = req.params;
  if (!jobId || typeof jobId !== "string") {
    res.status(400).json({ error: "Missing jobId" });
    return;
  }

  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  if (!job) {
    res.status(404).json({ error: "Job not found" });
    return;
  }

  res.json(serializeJobFull(job));
});

// POST /api/jobs/:jobId/cancel
router.post("/:jobId/cancel", async (req, res) => {
  const { jobId } = req.params;
  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  if (!job) {
    res.status(404).json({ error: "Job not found" });
    return;
  }
  if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
    res.status(409).json({ error: `Cannot cancel job in status '${job.status}'` });
    return;
  }

  await db.update(jobsTable)
    .set({
      status: "cancelled",
      currentStep: "Cancelled by user",
      finishedAt: new Date(),
      updatedAt: new Date(),
    } as Parameters<typeof db.update>[0]["set"])
    .where(eq(jobsTable.jobId, jobId));

  broadcastJobUpdate(jobId, job.projectId, {
    status: "cancelled",
    currentStep: "Cancelled by user",
    progress: job.progress,
  });

  const [updated] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJobFull(updated));
});

// POST /api/jobs/:jobId/retry
// Re-queues a failed/cancelled job for re-execution.
// NOTE: In MOCK_MODE this only resets status — a real Celery integration
// would re-dispatch the Celery task. This is the placeholder that wires
// up the schema + API contract.
router.post("/:jobId/retry", async (req, res) => {
  const { jobId } = req.params;
  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  if (!job) {
    res.status(404).json({ error: "Job not found" });
    return;
  }
  if (job.status !== "failed" && job.status !== "cancelled") {
    res.status(409).json({ error: `Can only retry failed or cancelled jobs, got '${job.status}'` });
    return;
  }

  await db.update(jobsTable)
    .set({
      status: "queued",
      progress: 0,
      currentStep: "Re-queued for retry",
      errorMessage: null,
      errorCode: null,
      startedAt: null,
      finishedAt: null,
      updatedAt: new Date(),
    } as Parameters<typeof db.update>[0]["set"])
    .where(eq(jobsTable.jobId, jobId));

  broadcastJobUpdate(jobId, job.projectId, {
    status: "queued",
    progress: 0,
    currentStep: "Re-queued for retry",
  });

  const [updated] = await db.select().from(jobsTable).where(eq(jobsTable.jobId, jobId));
  res.json(serializeJobFull(updated));
});

export default router;
