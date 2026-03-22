import { Router, type IRouter } from "express";
import { eq } from "drizzle-orm";
import { db, jobsTable } from "@workspace/db";

const router: IRouter = Router();

// GET /api/jobs/:jobId
router.get("/:jobId", async (req, res) => {
  const { jobId } = req.params;
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
    errorMessage: job.errorMessage,
    createdAt: job.createdAt,
  });
});

export default router;
