import { z } from "zod";
import { VersioningSchema } from "./versioning.js";

export const NoteSchema = z.object({
  pitch: z.number().int(),
  startTime: z.number(),
  duration: z.number(),
  velocity: z.number().int().min(0).max(127),
  frequency: z.number().optional(),
});

export const ChordEventSchema = z.object({
  startTime: z.number(),
  endTime: z.number(),
  chord: z.string(),
  romanNumeral: z.string().optional(),
  confidence: z.number().min(0).max(1),
  alternatives: z.array(z.string()).optional(),
  locked: z.boolean().optional(),
});

export const SectionSchema = z.object({
  label: z.string(),
  startTime: z.number(),
  endTime: z.number(),
  confidence: z.number().min(0).max(1),
  locked: z.boolean().optional(),
  regenerate: z.boolean().optional(),
});

export const ModulationSchema = z.object({
  timeSeconds: z.number(),
  fromKey: z.string(),
  toKey: z.string(),
});

export const RhythmDataSchema = z.object({
  bpm: z.number(),
  timeSignatureNumerator: z.number().int(),
  timeSignatureDenominator: z.number().int(),
  beatGrid: z.array(z.number()),
  downbeats: z.array(z.number()),
  confidence: z.number().min(0).max(1).optional(),
  warnings: z.array(z.string()).optional(),
  isMock: z.boolean().optional(),
});

export const KeyDataSchema = z.object({
  globalKey: z.string(),
  mode: z.string(),
  confidence: z.number().min(0).max(1),
  modulations: z.array(ModulationSchema).optional(),
  alternatives: z.array(z.object({ key: z.string(), mode: z.string(), confidence: z.number() })).optional(),
  warnings: z.array(z.string()).optional(),
  isMock: z.boolean().optional(),
});

export const ChordsDataSchema = z.object({
  chords: z.array(ChordEventSchema),
  leadSheet: z.string().optional(),
  warnings: z.array(z.string()).optional(),
  isMock: z.boolean().optional(),
});

export const MelodyDataSchema = z.object({
  notes: z.array(NoteSchema),
  inferredHarmony: z.array(z.string()).optional(),
  confidence: z.number().min(0).max(1).optional(),
  warnings: z.array(z.string()).optional(),
  isMock: z.boolean().optional(),
});

export const VocalsDataSchema = z.object({
  notes: z.array(NoteSchema).optional(),
  phrases: z.array(z.object({
    startTime: z.number(),
    endTime: z.number(),
    pitchMean: z.number(),
  })).optional(),
  vibratoDetected: z.boolean().optional(),
  confidence: z.number().min(0).max(1).optional(),
  warnings: z.array(z.string()).optional(),
}).optional();

export const StructureDataSchema = z.object({
  sections: z.array(SectionSchema),
  warnings: z.array(z.string()).optional(),
  isMock: z.boolean().optional(),
});

export const ConfidenceDataSchema = z.object({
  overall: z.number().min(0).max(1),
  rhythm: z.number().min(0).max(1).optional(),
  key: z.number().min(0).max(1).optional(),
  chords: z.number().min(0).max(1).optional(),
  melody: z.number().min(0).max(1).optional(),
  structure: z.number().min(0).max(1).optional(),
  vocals: z.number().min(0).max(1).optional(),
});

export const AnalysisResultSchema = z.object({
  projectId: z.number().int().positive(),
  rhythm: RhythmDataSchema.optional(),
  key: KeyDataSchema.optional(),
  chords: ChordsDataSchema.optional(),
  melody: MelodyDataSchema.optional(),
  vocals: VocalsDataSchema.optional(),
  structure: StructureDataSchema.optional(),
  sourceSeparation: z.object({
    method: z.string(),
    stems: z.array(z.string()),
    qualityScores: z.record(z.number()).optional(),
    warnings: z.array(z.string()).optional(),
  }).optional(),
  waveformData: z.array(z.number()).optional(),
  tonalTimeline: z.array(z.object({
    timeSeconds: z.number(),
    key: z.string(),
    mode: z.string(),
    confidence: z.number(),
  })).optional(),
  confidenceData: ConfidenceDataSchema.optional(),
  pipelineVersion: z.string().optional(),
  modelVersions: z.record(z.string()).optional(),
  createdFromAudioHash: z.string().optional(),
  createdAt: z.string().or(z.date()).optional(),
  updatedAt: z.string().or(z.date()).optional(),
}).merge(VersioningSchema.partial());

export type AnalysisResult = z.infer<typeof AnalysisResultSchema>;
export type RhythmData = z.infer<typeof RhythmDataSchema>;
export type KeyData = z.infer<typeof KeyDataSchema>;
export type ChordsData = z.infer<typeof ChordsDataSchema>;
export type MelodyData = z.infer<typeof MelodyDataSchema>;
export type StructureData = z.infer<typeof StructureDataSchema>;
export type Section = z.infer<typeof SectionSchema>;
export type ChordEvent = z.infer<typeof ChordEventSchema>;
export type Note = z.infer<typeof NoteSchema>;
export type ConfidenceData = z.infer<typeof ConfidenceDataSchema>;
