import { z } from "zod";

export const TrackSchema = z.object({
  id: z.string(),
  name: z.string(),
  instrument: z.string(),
  midiProgram: z.number().int().min(0).max(127),
  channel: z.number().int().min(0).max(15),
  color: z.string().optional(),
  volume: z.number().min(0).max(1).default(0.8),
  pan: z.number().min(-1).max(1).default(0),
  muted: z.boolean().default(false),
  soloed: z.boolean().default(false),
  locked: z.boolean().default(false),
  notes: z.array(z.object({
    pitch: z.number().int(),
    startTime: z.number(),
    duration: z.number(),
    velocity: z.number().int().min(0).max(127),
  })),
  role: z.string().optional(),
  section: z.string().optional(),
});

export const SectionPlanSchema = z.object({
  label: z.string(),
  startTime: z.number(),
  endTime: z.number(),
  chordProgression: z.string().optional(),
  key: z.string().optional(),
  intensity: z.number().min(0).max(1).optional(),
  regenerate: z.boolean().optional(),
});

export const HarmonicPlanSchema = z.object({
  globalKey: z.string(),
  mode: z.string(),
  sections: z.array(z.object({
    sectionLabel: z.string(),
    progression: z.array(z.string()),
    extensions: z.array(z.string()).optional(),
  })),
});

export const InstrumentationPlanSchema = z.object({
  styleId: z.string(),
  tracks: z.array(z.object({
    instrument: z.string(),
    role: z.string(),
    density: z.number().min(0).max(1),
    sections: z.array(z.string()),
  })),
});

export const ArrangementSchema = z.object({
  projectId: z.number().int().positive(),
  versionNumber: z.number().int().min(1),
  styleId: z.string(),
  tracks: z.array(TrackSchema),
  totalDurationSeconds: z.number(),
  sectionPlan: z.array(SectionPlanSchema).optional(),
  harmonicPlan: HarmonicPlanSchema.optional(),
  instrumentationPlan: InstrumentationPlanSchema.optional(),
  generationMetadata: z.record(z.unknown()).optional(),
  pipelineVersion: z.string().optional(),
  createdAt: z.string().or(z.date()).optional(),
});

export type Arrangement = z.infer<typeof ArrangementSchema>;
export type Track = z.infer<typeof TrackSchema>;
export type SectionPlan = z.infer<typeof SectionPlanSchema>;
export type HarmonicPlan = z.infer<typeof HarmonicPlanSchema>;
export type InstrumentationPlan = z.infer<typeof InstrumentationPlanSchema>;
