import { pgTable, text, serial, integer, real, jsonb, timestamp, pgEnum } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const projectStatusEnum = pgEnum("project_status", [
  "created", "uploading", "analyzing", "analyzed", "arranging", "arranged", "exporting", "done", "error"
]);

export const jobTypeEnum = pgEnum("job_type", [
  "upload", "analysis", "arrangement", "export", "render"
]);

export const jobStatusEnum = pgEnum("job_status", [
  "queued", "running", "completed", "failed"
]);

export const projectsTable = pgTable("projects", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  description: text("description"),
  status: projectStatusEnum("status").notNull().default("created"),
  audioFileName: text("audio_file_name"),
  audioFilePath: text("audio_file_path"),
  audioDurationSeconds: real("audio_duration_seconds"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

export const jobsTable = pgTable("jobs", {
  id: serial("id").primaryKey(),
  jobId: text("job_id").notNull().unique(),
  projectId: integer("project_id").notNull().references(() => projectsTable.id, { onDelete: "cascade" }),
  type: jobTypeEnum("type").notNull(),
  status: jobStatusEnum("status").notNull().default("queued"),
  progress: real("progress").notNull().default(0),
  currentStep: text("current_step"),
  errorMessage: text("error_message"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

export const analysisResultsTable = pgTable("analysis_results", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id").notNull().unique().references(() => projectsTable.id, { onDelete: "cascade" }),
  rhythmData: jsonb("rhythm_data"),
  keyData: jsonb("key_data"),
  chordsData: jsonb("chords_data"),
  melodyData: jsonb("melody_data"),
  structureData: jsonb("structure_data"),
  waveformData: jsonb("waveform_data"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const arrangementsTable = pgTable("arrangements", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id").notNull().references(() => projectsTable.id, { onDelete: "cascade" }),
  styleId: text("style_id").notNull(),
  tracksData: jsonb("tracks_data"),
  totalDurationSeconds: real("total_duration_seconds"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const insertProjectSchema = createInsertSchema(projectsTable).omit({ id: true, createdAt: true, updatedAt: true });
export const insertJobSchema = createInsertSchema(jobsTable).omit({ id: true, createdAt: true, updatedAt: true });

export type Project = typeof projectsTable.$inferSelect;
export type InsertProject = z.infer<typeof insertProjectSchema>;
export type Job = typeof jobsTable.$inferSelect;
export type InsertJob = z.infer<typeof insertJobSchema>;
export type AnalysisResult = typeof analysisResultsTable.$inferSelect;
export type Arrangement = typeof arrangementsTable.$inferSelect;
