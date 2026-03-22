import { Router, type IRouter } from "express";

const router: IRouter = Router();

const STYLES = [
  { id: "pop", name: "Pop", genre: "Pop", description: "Radio-friendly pop with clean production and melodic hooks", tags: ["modern", "melodic", "commercial"] },
  { id: "jazz", name: "Jazz", genre: "Jazz", description: "Swing jazz with complex harmony and improvised feel", tags: ["swing", "complex", "improvised"] },
  { id: "rnb", name: "R&B / Soul", genre: "R&B", description: "Soulful R&B with groove bass and lush chords", tags: ["soulful", "groove", "lush"] },
  { id: "classical", name: "Orchestral", genre: "Classical", description: "Full orchestral arrangement with strings, brass, and woodwinds", tags: ["orchestral", "dramatic", "cinematic"] },
  { id: "electronic", name: "Electronic", genre: "Electronic", description: "Synth-driven electronic production with driving beats", tags: ["electronic", "synth", "driving"] },
  { id: "rock", name: "Rock", genre: "Rock", description: "Energetic rock with electric guitars and powerful drums", tags: ["energetic", "powerful", "guitar"] },
  { id: "bossa_nova", name: "Bossa Nova", genre: "Brazilian", description: "Relaxed bossa nova with gentle guitar and subtle percussion", tags: ["relaxed", "brazilian", "elegant"] },
  { id: "ambient", name: "Ambient", genre: "Ambient", description: "Atmospheric ambient textures with evolving pads and minimal rhythm", tags: ["atmospheric", "textural", "minimal"] },
];

// GET /api/styles
router.get("/", (_req, res) => {
  res.json(STYLES);
});

export default router;
