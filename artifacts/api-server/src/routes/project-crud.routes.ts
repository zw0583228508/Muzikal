/**
 * Basic project CRUD + upload + mock-mode banner.
 * Routes: GET /, POST /, GET /:id, DELETE /:id, POST /:id/upload, GET /mock-mode
 */

import { Router } from "express";
import { eq, desc, count, or, isNull } from "drizzle-orm";
import { db, projectsTable, jobsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "../lib/websocket";
import { parseProjectId } from "../lib/validate";
import {
  MOCK_MODE,
  PIPELINE_VERSION,
  MODEL_VERSIONS,
  upload,
  serializeProject,
  serializeJob,
} from "../lib/project-helpers";

const router = Router();

// GET /api/projects/mock-mode
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

// GET /api/projects  — supports ?page=1&limit=20
router.get("/", async (req, res) => {
  const page  = Math.max(1, parseInt(req.query.page  as string) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit as string) || 20));
  const offset = (page - 1) * limit;

  const userId: string | null = (req as any).user?.id ?? (req as any).userId ?? null;
  const userFilter = userId
    ? or(eq(projectsTable.userId, userId), isNull(projectsTable.userId))
    : undefined;

  const [projects, [{ total }]] = await Promise.all([
    db.select().from(projectsTable)
      .where(userFilter)
      .orderBy(desc(projectsTable.createdAt))
      .limit(limit)
      .offset(offset),
    db.select({ total: count() }).from(projectsTable).where(userFilter),
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
  const userId: string | null = (req as any).user?.id ?? (req as any).userId ?? null;
  const [project] = await db
    .insert(projectsTable)
    .values({ name: name.trim(), description, userId })
    .returning();
  res.status(201).json(serializeProject(project));
});

// GET /api/projects/:id
router.get("/:id", async (req, res) => {
  const id = parseProjectId(req, res);
  if (id === null) return;
  const [project] = await db
    .select()
    .from(projectsTable)
    .where(eq(projectsTable.id, id));
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
    jobId, projectId, type: "upload", status: "completed",
    progress: 100, currentStep: "Upload complete",
  });

  await db.update(projectsTable)
    .set({ status: "created", updatedAt: new Date() })
    .where(eq(projectsTable.id, projectId));

  broadcastJobUpdate(jobId, projectId, { status: "completed", progress: 100, currentStep: "Upload complete" });

  res.json({
    jobId, projectId, type: "upload", status: "completed",
    progress: 100, currentStep: "Upload complete", createdAt: new Date(),
  });
});

export default router;
