import { Router, type IRouter } from "express";
import { eq } from "drizzle-orm";
import { db, jobsTable } from "@workspace/db";

const router: IRouter = Router();

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

  res.json({
    jobId: job.jobId,
    projectId: job.projectId,
    type: job.type,
    status: job.status,
    progress: job.progress,
    currentStep: job.currentStep,
    isMock: job.isMock ?? false,
    errorMessage: job.errorMessage ?? null,
    resultData: job.resultData ?? null,
    warnings: job.warnings ?? null,
    processingMetadata: job.processingMetadata ?? null,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
  });
});

export default router;
