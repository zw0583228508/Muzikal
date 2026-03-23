/**
 * Audio streaming and generated file download routes.
 * Routes: GET /:id/audio, GET /:id/files, GET /:id/files/:filename/download,
 *         GET /:id/files/:filename/serve
 */

import fs from "fs";
import path from "path";
import { Router } from "express";
import { eq, desc, and } from "drizzle-orm";
import { db, projectsTable, projectFilesTable } from "@workspace/db";
import { parseProjectId } from "../lib/validate";
import { logger } from "../lib/logger";
import {
  requireProjectOwner,
  signDownloadToken,
  verifyDownloadToken,
} from "../lib/project-helpers";

const router = Router();

const MIME_AUDIO: Record<string, string> = {
  wav: "audio/wav", mp3: "audio/mpeg", flac: "audio/flac",
  aiff: "audio/aiff", m4a: "audio/mp4", ogg: "audio/ogg",
};

const MIME_EXPORT: Record<string, string> = {
  mid: "audio/midi", midi: "audio/midi",
  musicxml: "application/vnd.recordare.musicxml+xml",
  wav: "audio/wav", flac: "audio/flac", mp3: "audio/mpeg",
  txt: "text/plain", pdf: "application/pdf",
};

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
  const mime = MIME_AUDIO[ext] || "audio/octet-stream";
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

// GET /api/projects/:id/files  — list project files (ownership-protected)
router.get("/:id/files", requireProjectOwner, async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const files = await db
    .select()
    .from(projectFilesTable)
    .where(eq(projectFilesTable.projectId, projectId))
    .orderBy(desc(projectFilesTable.createdAt));
  res.json(files.map(f => ({
    id: f.id,
    fileName: f.fileName,
    fileType: f.fileType,
    fileSizeBytes: f.fileSizeBytes,
    createdAt: f.createdAt,
    downloadUrl: `/api/projects/${projectId}/files/${encodeURIComponent(f.fileName)}/download`,
  })));
});

// GET /api/projects/:id/files/:filename/download
// Issues a short-lived signed redirect URL.
router.get("/:id/files/:filename/download", requireProjectOwner, async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { filename } = req.params;
  const [file] = await db
    .select()
    .from(projectFilesTable)
    .where(and(eq(projectFilesTable.projectId, projectId), eq(projectFilesTable.fileName, filename)));
  if (!file) return res.status(404).json({ error: "File not found" });
  if (!fs.existsSync(file.filePath)) return res.status(410).json({ error: "File no longer on disk" });

  const token = signDownloadToken(projectId, filename, 3600);
  res.redirect(302, `/api/projects/${projectId}/files/${encodeURIComponent(filename)}/serve?token=${token}`);
});

// GET /api/projects/:id/files/:filename/serve?token=<signed>
// Validates signed token and streams the file.
router.get("/:id/files/:filename/serve", async (req, res) => {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const { filename } = req.params;
  const { token } = req.query as { token?: string };
  if (!token) return res.status(401).json({ error: "Missing token" });

  const payload = verifyDownloadToken(token);
  if (!payload || payload.projectId !== projectId || payload.fileName !== filename) {
    return res.status(403).json({ error: "Invalid or expired download token" });
  }

  const [file] = await db
    .select()
    .from(projectFilesTable)
    .where(and(eq(projectFilesTable.projectId, projectId), eq(projectFilesTable.fileName, filename)));
  if (!file) return res.status(404).json({ error: "File not found" });
  if (!fs.existsSync(file.filePath)) return res.status(410).json({ error: "File no longer on disk" });

  const mime = MIME_EXPORT[file.fileType] || "application/octet-stream";
  res.setHeader("Content-Disposition", `attachment; filename="${file.fileName}"`);
  res.setHeader("Content-Type", mime);
  if (file.fileSizeBytes) res.setHeader("Content-Length", file.fileSizeBytes);
  logger.info({ projectId, fileName: filename }, "Serving file via signed token");
  fs.createReadStream(file.filePath).pipe(res);
});

export default router;
