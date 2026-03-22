import { z } from "zod";

export const ProjectStatusSchema = z.enum([
  "created",
  "uploading",
  "uploaded",
  "analyzing",
  "analyzed",
  "arranging",
  "arranged",
  "exporting",
  "error",
]);

export const ProjectSchema = z.object({
  id: z.number().int().positive(),
  name: z.string().min(1).max(255),
  description: z.string().optional(),
  audioFileName: z.string().optional(),
  audioFilePath: z.string().optional(),
  audioDurationSeconds: z.number().optional(),
  audioSampleRate: z.number().int().optional(),
  audioChannels: z.number().int().optional(),
  audioCodec: z.string().optional(),
  audioFileHash: z.string().optional(),
  status: ProjectStatusSchema,
  userCorrections: z.record(z.unknown()).nullable().optional(),
  locks: z.record(z.boolean()).nullable().optional(),
  createdAt: z.string().or(z.date()).optional(),
  updatedAt: z.string().or(z.date()).optional(),
});

export type Project = z.infer<typeof ProjectSchema>;
export type ProjectStatus = z.infer<typeof ProjectStatusSchema>;
