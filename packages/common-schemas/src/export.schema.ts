import { z } from "zod";

export const ExportFormatSchema = z.enum([
  "midi",
  "musicxml",
  "wav",
  "flac",
  "mp3",
  "lead_sheet",
  "full_score",
]);

export const ExportQualitySchema = z.enum(["preview", "high"]);

export const ExportOptionsSchema = z.object({
  format: ExportFormatSchema,
  quality: ExportQualitySchema.default("high"),
  includeChordSymbols: z.boolean().default(true),
  includeLyrics: z.boolean().default(false),
  quantizeToGrid: z.boolean().default(true),
  quantizeResolution: z.number().int().default(16),
  tempoOverride: z.number().optional(),
  normalizeLoudness: z.boolean().default(true),
  targetLufs: z.number().default(-14),
  sampleRate: z.number().int().default(44100),
  bitDepth: z.number().int().default(24),
});

export const ExportResultSchema = z.object({
  format: ExportFormatSchema,
  quality: ExportQualitySchema,
  filePath: z.string(),
  fileName: z.string(),
  fileSizeBytes: z.number(),
  durationSeconds: z.number().optional(),
  warnings: z.array(z.string()).optional(),
  pipelineVersion: z.string().optional(),
});

export type ExportFormat = z.infer<typeof ExportFormatSchema>;
export type ExportQuality = z.infer<typeof ExportQualitySchema>;
export type ExportOptions = z.infer<typeof ExportOptionsSchema>;
export type ExportResult = z.infer<typeof ExportResultSchema>;
