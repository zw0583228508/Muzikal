/**
 * Shared helpers, config, middleware, and serializers for all project routes.
 * Imported by every sub-router under src/routes/project-*.routes.ts
 */

import path from "path";
import fs from "fs";
import { createHmac, randomBytes } from "crypto";
import { type Request, type Response, type NextFunction } from "express";
import multer from "multer";
import { eq } from "drizzle-orm";
import { db, projectsTable, jobsTable } from "@workspace/db";
import { v4 as uuidv4 } from "uuid";
import { broadcastJobUpdate } from "./websocket";
import { parseProjectId } from "./validate";
import { logger } from "./logger";

// ─── Config ──────────────────────────────────────────────────────────────────

export const UPLOADS_DIR = process.env.UPLOADS_DIR || "/tmp/music-ai-uploads";
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

export const PYTHON_BACKEND = process.env.PYTHON_BACKEND_URL || "http://localhost:8001";

/**
 * MOCK_MODE controls behaviour when the Python backend is unavailable.
 * MOCK_MODE=false (default) — any Python backend failure marks the job as FAILED.
 * MOCK_MODE=true  — enables simulation mode for UI testing WITHOUT a working ML backend.
 *                   Must be explicitly set in env; never enabled in production.
 */
export const MOCK_MODE = (process.env.MOCK_MODE ?? "false").toLowerCase() === "true";
if (MOCK_MODE) {
  console.warn(
    "[WARN] MOCK_MODE is ENABLED — analysis results are simulated. " +
    "Set MOCK_MODE=false for real production analysis."
  );
}

export const PIPELINE_VERSION = "2.0.0";

export const MODEL_VERSIONS: Record<string, string> = {
  demucs:         "htdemucs-4.0.1",
  madmom:         "0.16.1",
  essentia:       "2.1b6",
  torchcrepe:     "0.0.24",
  "basic-pitch":  "0.4.0",
  librosa:        "0.11.0",
};

export const MODEL_BY_TYPE: Record<string, string> = {
  rhythm:     `madmom-${MODEL_VERSIONS.madmom}`,
  key:        `essentia-${MODEL_VERSIONS.essentia}`,
  chords:     `chord-cnn-${MODEL_VERSIONS["chord-cnn"]}`,
  melody:     `pyin-${MODEL_VERSIONS.pyin}`,
  structure:  `msaf-${MODEL_VERSIONS.msaf}`,
  separation: `demucs-${MODEL_VERSIONS.demucs}`,
  vocals:     `crepe-${MODEL_VERSIONS.crepe}`,
};

// ─── Multer ──────────────────────────────────────────────────────────────────

const diskStorage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOADS_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, `${uuidv4()}${ext}`);
  },
});

export const upload = multer({
  storage: diskStorage,
  limits: { fileSize: 200 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const allowed = [".wav", ".mp3", ".flac", ".aiff", ".m4a", ".ogg"];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error(`Unsupported file type: ${ext}`));
  },
});

// ─── Download tokens ─────────────────────────────────────────────────────────

/** Signing secret for local presigned download tokens. */
const STORAGE_SECRET = process.env.STORAGE_SECRET || randomBytes(32).toString("hex");

/** Sign a download token (HMAC-SHA256) encoding projectId + fileName + expiry. */
export function signDownloadToken(
  projectId: number,
  fileName: string,
  expiresInSeconds = 3600,
): string {
  const payload = JSON.stringify({
    projectId,
    fileName,
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds,
  });
  const b64 = Buffer.from(payload).toString("base64url");
  const sig = createHmac("sha256", STORAGE_SECRET).update(b64).digest("base64url");
  return `${b64}.${sig}`;
}

/** Verify a download token; returns parsed payload or null if invalid/expired. */
export function verifyDownloadToken(
  token: string,
): { projectId: number; fileName: string; exp: number } | null {
  try {
    const [b64, sig] = token.split(".");
    const expected = createHmac("sha256", STORAGE_SECRET).update(b64).digest("base64url");
    if (sig !== expected) return null;
    const payload = JSON.parse(Buffer.from(b64, "base64url").toString("utf-8"));
    if (payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

// ─── Python backend proxy ─────────────────────────────────────────────────────

export async function callPythonBackend(
  endpoint: string,
  body: object,
  projectId?: number,
) {
  let res: globalThis.Response;
  try {
    res = await fetch(`${PYTHON_BACKEND}/python-api${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (networkErr) {
    logger.error({ projectId, endpoint, err: String(networkErr) }, "Python backend unreachable");
    throw new Error(`Python backend unreachable: ${networkErr}`);
  }
  if (!res.ok) {
    const errBody = await res.text().catch(() => "(unreadable)");
    logger.error({ projectId, endpoint, status: res.status, errBody }, "Python backend returned error");
    throw new Error(`Python backend error (${res.status}): ${errBody}`);
  }
  return res.json();
}

// ─── Job helpers ─────────────────────────────────────────────────────────────

/** Update job in DB and broadcast over WebSocket. */
export async function updateJob(
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
  await db
    .update(jobsTable)
    .set({ ...update, updatedAt: new Date() } as Parameters<typeof db.update>[0]["set"])
    .where(eq(jobsTable.jobId, jobId));
  broadcastJobUpdate(jobId, projectId, update);
}

/** Mark job as started (sets startedAt + running status). */
export async function startJob(jobId: string, projectId: number, firstStep: string) {
  await updateJob(jobId, projectId, {
    status: "running",
    progress: 1,
    currentStep: firstStep,
    startedAt: new Date(),
  });
}

/** Mark job as failed with errorCode and finishedAt. */
export async function failJobNoPython(
  jobId: string,
  projectId: number,
  err: unknown,
) {
  const msg = err instanceof Error ? err.message : String(err);
  logger.error({ jobId, projectId, error: msg }, "Python backend failed — marking job FAILED");
  await updateJob(jobId, projectId, {
    status: "failed",
    progress: 0,
    currentStep: "Python backend unavailable",
    errorMessage: msg,
    errorCode: "PYTHON_UNAVAILABLE",
    finishedAt: new Date(),
  });
}

// ─── Ownership middleware ─────────────────────────────────────────────────────

/**
 * Ownership middleware — verifies the authenticated user owns the project.
 * Attaches project record to res.locals.project.
 */
export async function requireProjectOwner(
  req: Request,
  res: Response,
  next: NextFunction,
) {
  const projectId = parseProjectId(req, res);
  if (projectId === null) return;
  const [project] = await db
    .select()
    .from(projectsTable)
    .where(eq(projectsTable.id, projectId));
  if (!project) {
    res.status(404).json({ error: "Project not found" });
    return;
  }
  const userId = (req as any).user?.id ?? (req as any).userId ?? null;
  if (
    userId !== null &&
    project.userId !== null &&
    String(project.userId) !== String(userId)
  ) {
    logger.warn({ projectId, userId }, "Forbidden: user does not own project");
    res.status(403).json({ error: "Forbidden" });
    return;
  }
  (res as any).locals.project = project;
  next();
}

// ─── Serializers ─────────────────────────────────────────────────────────────

export function serializeProject(p: typeof projectsTable.$inferSelect) {
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

export function serializeJob(j: typeof jobsTable.$inferSelect) {
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
