import { z } from "zod";

export const VersioningSchema = z.object({
  pipelineVersion: z.string(),
  modelVersions: z.record(z.string()).optional(),
  createdFromAudioHash: z.string().optional(),
});

export type Versioning = z.infer<typeof VersioningSchema>;

export const PIPELINE_VERSION = "1.0.0";

export const MODEL_VERSIONS = {
  rhythm: "librosa-0.10",
  key: "krumhansl-schmuckler",
  chords: "template-matching-v2",
  melody: "pyin",
  vocals: "pyin-vocal",
  structure: "ssm-novelty",
  separation: "demucs-htdemucs",
  export: "pretty-midi-1.0",
} as const;
