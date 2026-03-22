import { z } from "zod";

export const VersioningSchema = z.object({
  pipelineVersion: z.string(),
  modelVersions: z.record(z.string()).optional(),
  createdFromAudioHash: z.string().optional(),
});

export type Versioning = z.infer<typeof VersioningSchema>;

export const PIPELINE_VERSION = "1.1.0";

export const MODEL_VERSIONS: Record<string, string> = {
  "madmom":    "madmom-0.16.1",
  "essentia":  "essentia-2.1b6",
  "chord-cnn": "chord-cnn-0.4.0",
  "pyin":      "pyin-0.1.1",
  "msaf":      "msaf-0.1.8",
  "demucs":    "demucs-4.0.1",
  "crepe":     "crepe-0.0.13",
} as const;

export const MODEL_BY_TYPE: Record<string, string> = {
  rhythm:    MODEL_VERSIONS["madmom"],
  key:       MODEL_VERSIONS["essentia"],
  chords:    MODEL_VERSIONS["chord-cnn"],
  melody:    MODEL_VERSIONS["pyin"],
  vocals:    MODEL_VERSIONS["pyin"],
  structure: MODEL_VERSIONS["msaf"],
  stems:     MODEL_VERSIONS["demucs"],
  f0:        MODEL_VERSIONS["crepe"],
} as const;
