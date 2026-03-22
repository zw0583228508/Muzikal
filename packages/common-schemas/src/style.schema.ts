import { z } from "zod";

export const StyleSchema = z.object({
  id: z.string(),
  name: z.string(),
  nameHe: z.string().optional(),
  genre: z.string(),
  genreHe: z.string().optional(),
  description: z.string().optional(),
  defaultDensity: z.number().min(0).max(1).default(0.7),
  defaultInstruments: z.array(z.string()).default([]),
  tempoFeel: z.enum(["straight", "swing", "shuffle", "rubato", "half-time", "double-time"]).default("straight"),
  harmonicTendency: z.enum([
    "diatonic",
    "extended_chords",
    "modal",
    "chromatic",
    "pentatonic",
    "maqam",
    "klezmer",
    "blues",
  ]).default("diatonic"),
  notes: z.string().optional(),
});

export type Style = z.infer<typeof StyleSchema>;

export const ArrangerProfileSchema = z.object({
  styleId: z.string(),
  intro: z.object({
    bars: z.number().int(),
    density: z.number().min(0).max(1),
    instruments: z.array(z.string()),
  }),
  verse: z.object({
    density: z.number().min(0).max(1),
    instruments: z.array(z.string()),
    rhythmicFeel: z.string(),
  }),
  chorus: z.object({
    density: z.number().min(0).max(1),
    instruments: z.array(z.string()),
    dynamicBoost: z.number(),
  }),
  bridge: z.object({
    density: z.number().min(0).max(1),
    instruments: z.array(z.string()),
    contrastWithChorus: z.boolean(),
  }).optional(),
  outro: z.object({
    bars: z.number().int(),
    fadeOut: z.boolean(),
  }),
});

export type ArrangerProfile = z.infer<typeof ArrangerProfileSchema>;
