import { z } from "zod";
import { VersioningSchema } from "./versioning.js";

export const JobStatusSchema = z.enum([
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
]);

export const JobTypeSchema = z.enum([
  "analysis",
  "arrangement",
  "export",
  "render",
  "separation",
]);

export const JobStepSchema = z.object({
  name: z.string(),
  status: z.enum(["pending", "running", "completed", "failed", "skipped"]),
  startedAt: z.string().datetime().optional(),
  completedAt: z.string().datetime().optional(),
  durationMs: z.number().optional(),
  error: z.string().optional(),
});

export const JobSchema = z.object({
  jobId: z.string(),
  projectId: z.number().int().positive(),
  type: JobTypeSchema,
  status: JobStatusSchema,
  progress: z.number().min(0).max(100),
  currentStep: z.string().optional(),
  steps: z.array(JobStepSchema).optional(),
  isMock: z.boolean().default(false),
  errorMessage: z.string().nullable().optional(),
  resultData: z.record(z.unknown()).nullable().optional(),
  warnings: z.array(z.string()).nullable().optional(),
  processingMetadata: z.record(z.unknown()).nullable().optional(),
  pipelineVersion: z.string().optional(),
  modelVersions: z.record(z.string()).optional(),
  createdAt: z.string().or(z.date()).optional(),
  updatedAt: z.string().or(z.date()).optional(),
});

export type Job = z.infer<typeof JobSchema>;
export type JobStatus = z.infer<typeof JobStatusSchema>;
export type JobType = z.infer<typeof JobTypeSchema>;
export type JobStep = z.infer<typeof JobStepSchema>;

export const ANALYSIS_STEPS: JobStep[] = [
  { name: "preprocessing", status: "pending" },
  { name: "separation", status: "pending" },
  { name: "rhythm", status: "pending" },
  { name: "key", status: "pending" },
  { name: "chords", status: "pending" },
  { name: "melody", status: "pending" },
  { name: "vocals", status: "pending" },
  { name: "structure", status: "pending" },
];

export const ARRANGEMENT_STEPS: JobStep[] = [
  { name: "section_map", status: "pending" },
  { name: "harmonic_plan", status: "pending" },
  { name: "instrumentation", status: "pending" },
  { name: "orchestration", status: "pending" },
  { name: "transitions", status: "pending" },
];

export const EXPORT_STEPS: JobStep[] = [
  { name: "quantization", status: "pending" },
  { name: "midi_export", status: "pending" },
  { name: "musicxml_export", status: "pending" },
  { name: "audio_render", status: "pending" },
];
