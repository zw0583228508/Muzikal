import { pgTable, text, serial, integer, real, jsonb, timestamp, pgEnum, bigint, boolean, index } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const projectStatusEnum = pgEnum("project_status", [
  "created", "uploading", "analyzing", "analyzed", "arranging", "arranged", "exporting", "done", "error"
]);

export const jobTypeEnum = pgEnum("job_type", [
  "upload", "analysis", "arrangement", "export", "render"
]);

export const jobStatusEnum = pgEnum("job_status", [
  "queued", "running", "completed", "failed", "cancelled"
]);

// ─── Projects ─────────────────────────────────────────────────────────────────

export const projectsTable = pgTable("projects", {
  id: serial("id").primaryKey(),
  userId: text("user_id"),
  name: text("name").notNull(),
  description: text("description"),
  status: projectStatusEnum("status").notNull().default("created"),
  audioFileName: text("audio_file_name"),
  audioFilePath: text("audio_file_path"),
  audioDurationSeconds: real("audio_duration_seconds"),
  audioSampleRate: integer("audio_sample_rate"),
  audioChannels: integer("audio_channels"),
  audioFileHash: text("audio_file_hash"),
  audioCodec: text("audio_codec"),
  audioBitrate: integer("audio_bitrate"),
  userCorrections: jsonb("user_corrections"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export const jobsTable = pgTable("jobs", {
  id: serial("id").primaryKey(),
  jobId: text("job_id").notNull().unique(),
  projectId: integer("project_id").notNull().references(() => projectsTable.id, { onDelete: "cascade" }),
  type: jobTypeEnum("type").notNull(),
  status: jobStatusEnum("status").notNull().default("queued"),
  progress: real("progress").notNull().default(0),
  currentStep: text("current_step"),
  isMock: boolean("is_mock").notNull().default(false),
  errorMessage: text("error_message"),
  errorCode: text("error_code"),
  inputPayload: jsonb("input_payload"),
  resultData: jsonb("result_data"),
  warnings: jsonb("warnings"),
  processingMetadata: jsonb("processing_metadata"),
  startedAt: timestamp("started_at"),
  finishedAt: timestamp("finished_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

// ─── Analysis Results ─────────────────────────────────────────────────────────

export const analysisResultsTable = pgTable("analysis_results", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id").notNull().unique().references(() => projectsTable.id, { onDelete: "cascade" }),
  rhythmData: jsonb("rhythm_data"),
  keyData: jsonb("key_data"),
  chordsData: jsonb("chords_data"),
  melodyData: jsonb("melody_data"),
  structureData: jsonb("structure_data"),
  waveformData: jsonb("waveform_data"),
  vocalsData: jsonb("vocals_data"),
  sourceSeparationData: jsonb("source_separation_data"),
  tonalTimelineData: jsonb("tonal_timeline_data"),
  confidenceData: jsonb("confidence_data"),
  pipelineVersion: text("pipeline_version"),
  modelVersions: jsonb("model_versions"),
  processingMetadata: jsonb("processing_metadata"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

// ─── Arrangements ─────────────────────────────────────────────────────────────

export const arrangementsTable = pgTable("arrangements", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id").notNull().references(() => projectsTable.id, { onDelete: "cascade" }),
  versionNumber: integer("version_number").notNull().default(1),
  isCurrent: boolean("is_current").notNull().default(true),
  styleId: text("style_id").notNull(),
  tracksData: jsonb("tracks_data"),
  arrangementPlan: jsonb("arrangement_plan"),
  totalDurationSeconds: real("total_duration_seconds"),
  generationMetadata: jsonb("generation_metadata"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

// ─── Project Files ────────────────────────────────────────────────────────────

export const projectFilesTable = pgTable("project_files", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id").notNull().references(() => projectsTable.id, { onDelete: "cascade" }),
  jobId: text("job_id").notNull(),
  fileName: text("file_name").notNull(),
  filePath: text("file_path").notNull(),
  fileType: text("file_type").notNull(),
  fileSizeBytes: bigint("file_size_bytes", { mode: "number" }),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

// ─── Zod Schemas & Types ──────────────────────────────────────────────────────

export const insertProjectSchema = createInsertSchema(projectsTable).omit({ id: true, createdAt: true, updatedAt: true });
export const insertJobSchema = createInsertSchema(jobsTable).omit({ id: true, createdAt: true, updatedAt: true });

export const projectsByUserIdx = index("projects_user_id_idx").on(projectsTable.userId);

export type Project = typeof projectsTable.$inferSelect;
export type InsertProject = z.infer<typeof insertProjectSchema>;
export type Job = typeof jobsTable.$inferSelect;
export type InsertJob = z.infer<typeof insertJobSchema>;
export type AnalysisResult = typeof analysisResultsTable.$inferSelect;
export type Arrangement = typeof arrangementsTable.$inferSelect;
export type ProjectFile = typeof projectFilesTable.$inferSelect;
