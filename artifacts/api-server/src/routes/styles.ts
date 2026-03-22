import { Router, type IRouter } from "express";

const router: IRouter = Router();

/**
 * Single source of truth for style definitions in the Node.js layer.
 * Keep this in sync with artifacts/music-ai-backend/orchestration/arranger.py → STYLES.
 */
export const STYLES = [
  {
    id: "pop",
    name: "Pop",
    genre: "Pop",
    description: "Radio-friendly pop with clean production and melodic hooks",
    tags: ["modern", "melodic", "commercial"],
    defaultInstruments: ["drums", "bass", "piano", "guitar", "strings", "pad"],
    defaultDensity: 0.75,
  },
  {
    id: "jazz",
    name: "Jazz",
    genre: "Jazz",
    description: "Swing jazz with complex harmony and improvised feel",
    tags: ["swing", "complex", "improvised"],
    defaultInstruments: ["drums", "bass", "piano", "guitar", "brass"],
    defaultDensity: 0.65,
  },
  {
    id: "rnb",
    name: "R&B / Soul",
    genre: "R&B",
    description: "Soulful R&B with groove bass and lush chords",
    tags: ["soulful", "groove", "lush"],
    defaultInstruments: ["drums", "bass", "piano", "guitar", "strings", "pad"],
    defaultDensity: 0.80,
  },
  {
    id: "classical",
    name: "Orchestral",
    genre: "Classical",
    description: "Full orchestral arrangement with strings, brass, and woodwinds",
    tags: ["orchestral", "dramatic", "classical"],
    defaultInstruments: ["strings", "brass", "piano"],
    defaultDensity: 0.85,
  },
  {
    id: "electronic",
    name: "Electronic",
    genre: "Electronic",
    description: "Synth-driven electronic production with driving beats",
    tags: ["electronic", "synth", "driving"],
    defaultInstruments: ["drums", "bass", "pad", "lead_synth"],
    defaultDensity: 0.90,
  },
  {
    id: "rock",
    name: "Rock",
    genre: "Rock",
    description: "Energetic rock with electric guitars and powerful drums",
    tags: ["energetic", "powerful", "guitar"],
    defaultInstruments: ["drums", "bass", "guitar", "piano"],
    defaultDensity: 0.85,
  },
  {
    id: "bossa_nova",
    name: "Bossa Nova",
    genre: "Brazilian",
    description: "Relaxed bossa nova with gentle guitar and subtle percussion",
    tags: ["relaxed", "brazilian", "elegant"],
    defaultInstruments: ["drums", "bass", "guitar", "piano"],
    defaultDensity: 0.55,
  },
  {
    id: "ambient",
    name: "Ambient",
    genre: "Ambient",
    description: "Atmospheric ambient textures with evolving pads and minimal rhythm",
    tags: ["atmospheric", "textural", "minimal"],
    defaultInstruments: ["pad", "strings", "piano"],
    defaultDensity: 0.30,
  },
  {
    id: "hasidic",
    name: "חסידי / Hasidic",
    genre: "Hasidic",
    description: "Traditional Hasidic/Klezmer with freylekhs dance rhythms and ornamental melody",
    tags: ["jewish", "klezmer", "traditional", "dance"],
    defaultInstruments: ["drums", "bass", "piano", "strings", "brass"],
    defaultDensity: 0.80,
  },
  {
    id: "middle_eastern",
    name: "מזרחי / Middle Eastern",
    genre: "Middle Eastern",
    description: "Mizrahi/Arabic style with maqam scales, oud-like guitar, and darbuka percussion",
    tags: ["mizrahi", "arabic", "maqam", "oud"],
    defaultInstruments: ["drums", "bass", "guitar", "strings", "pad"],
    defaultDensity: 0.72,
  },
  {
    id: "hiphop",
    name: "Hip-Hop / Trap",
    genre: "Hip-Hop",
    description: "Modern hip-hop beat with heavy 808 bass, trap hi-hats, and vocal chops",
    tags: ["trap", "808", "urban", "beats"],
    defaultInstruments: ["drums", "bass", "pad", "lead_synth"],
    defaultDensity: 0.88,
  },
  {
    id: "ballad",
    name: "Ballad",
    genre: "Ballad",
    description: "Slow emotional ballad with piano, strings, and intimate dynamics",
    tags: ["slow", "emotional", "intimate", "piano"],
    defaultInstruments: ["piano", "strings", "pad", "bass"],
    defaultDensity: 0.45,
  },
  {
    id: "cinematic",
    name: "Cinematic",
    genre: "Cinematic",
    description: "Epic film score with full orchestra, dramatic swells, and emotional arcs",
    tags: ["film", "epic", "dramatic", "orchestral"],
    defaultInstruments: ["strings", "brass", "piano", "pad", "drums"],
    defaultDensity: 0.90,
  },
  {
    id: "wedding",
    name: "Wedding Band",
    genre: "Wedding",
    description: "Festive wedding band with full horns, rhythm section, and crowd-pleasing arrangements",
    tags: ["festive", "horns", "celebration", "live"],
    defaultInstruments: ["drums", "bass", "piano", "brass", "strings", "guitar"],
    defaultDensity: 0.85,
  },
  {
    id: "acoustic",
    name: "Acoustic / Folk",
    genre: "Acoustic",
    description: "Intimate acoustic folk with fingerpicked guitar, light percussion, and natural warmth",
    tags: ["folk", "acoustic", "guitar", "intimate"],
    defaultInstruments: ["guitar", "bass", "piano"],
    defaultDensity: 0.40,
  },
];

// GET /api/styles
router.get("/", (_req, res) => {
  res.json(STYLES);
});

export default router;
