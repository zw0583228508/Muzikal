import { Router, type IRouter } from "express";
import path from "path";
import fs from "fs";
import yaml from "js-yaml";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const router: IRouter = Router();

/**
 * Single source of truth for style definitions.
 * Loaded from configs/styles/genres.yaml at the workspace root.
 * Both Node.js (here) and Python (audio/style_loader.py) load from the same file.
 */

// __dirname = artifacts/api-server/src/routes → 4 levels up = workspace root
const WORKSPACE_ROOT = process.env.WORKSPACE_ROOT ??
  path.resolve(path.join(__dirname, "..", "..", "..", ".."));
const STYLES_YAML_PATH = path.join(WORKSPACE_ROOT, "configs", "styles", "genres.yaml");

interface StyleConfig {
  id: string;
  name: string;
  nameHe?: string;
  genre: string;
  genreHe?: string;
  description?: string;
  density_default?: number;
  instrumentation?: string[];
  tempo_feel?: string;
  harmonic_tendency?: string;
  notes?: string;
}

interface StylesFile {
  styles: StyleConfig[];
}

let _cachedStyles: StyleConfig[] | null = null;

function loadStylesFromYaml(): StyleConfig[] {
  if (_cachedStyles) return _cachedStyles;

  try {
    const raw = fs.readFileSync(STYLES_YAML_PATH, "utf-8");
    const parsed = yaml.load(raw) as StylesFile;
    _cachedStyles = parsed?.styles ?? [];
    console.log(`[styles] Loaded ${_cachedStyles.length} styles from YAML`);
    return _cachedStyles;
  } catch (err) {
    console.warn(`[styles] Could not load YAML (${err}); using hardcoded fallback`);
    return FALLBACK_STYLES;
  }
}

// GET /api/styles
router.get("/", (_req, res) => {
  const styles = loadStylesFromYaml();
  res.json(
    styles.map((s) => ({
      id: s.id,
      name: s.name,
      nameHe: s.nameHe ?? s.name,
      genre: s.genre,
      genreHe: s.genreHe ?? s.genre,
      description: s.description ?? "",
      defaultDensity: s.density_default ?? 0.7,
      defaultInstruments: s.instrumentation ?? [],
      tempoFeel: s.tempo_feel ?? "straight",
      harmonicTendency: s.harmonic_tendency ?? "diatonic",
    })),
  );
});

// GET /api/styles/personas
// Returns all arranger persona definitions loaded from arranger_personas.yaml
const PERSONAS_YAML_PATH = path.join(
  WORKSPACE_ROOT, "artifacts", "music-ai-backend", "orchestration", "arranger_personas.yaml"
);

let _cachedPersonas: PersonaConfig[] | null = null;

interface PersonaConfig {
  id: string;
  name: string;
  name_en: string;
  description: string;
  preferred_styles: string[];
  instrumentation_weights: Record<string, number>;
  density_curve: Record<string, number>;
  humanization: number;
  swing: number;
  fills_density: number;
  articulation_bias: string;
  dynamics_shape: string;
  transition_vocabulary: string[];
  tags: string[];
}

function loadPersonasFromYaml(): PersonaConfig[] {
  if (_cachedPersonas) return _cachedPersonas;
  try {
    const raw = fs.readFileSync(PERSONAS_YAML_PATH, "utf-8");
    const parsed = yaml.load(raw) as { personas: PersonaConfig[] };
    _cachedPersonas = parsed?.personas ?? [];
    console.log(`[styles] Loaded ${_cachedPersonas.length} personas from YAML`);
    return _cachedPersonas;
  } catch (err) {
    console.warn(`[styles] Could not load personas YAML (${err})`);
    return FALLBACK_PERSONAS;
  }
}

router.get("/personas", (_req, res) => {
  const personas = loadPersonasFromYaml();
  res.json(personas.map(p => ({
    id: p.id,
    name: p.name,
    nameEn: p.name_en,
    description: p.description,
    preferredStyles: p.preferred_styles ?? [],
    humanization: p.humanization ?? 0.5,
    swing: p.swing ?? 0.0,
    transitionVocabulary: p.transition_vocabulary ?? [],
    articulationBias: p.articulation_bias ?? "natural",
    dynamicsShape: p.dynamics_shape ?? "linear",
    tags: p.tags ?? [],
  })));
});

// ─── Genre routes (Universal Style Engine) ───────────────────────────────────
const PYTHON_BACKEND = `http://localhost:${process.env.PYTHON_BACKEND_PORT ?? 8001}`;

async function pythonGet(path: string): Promise<{ status: number; data: unknown }> {
  try {
    const res = await fetch(`${PYTHON_BACKEND}${path}`);
    const data = await res.json().catch(() => ({}));
    return { status: res.status, data };
  } catch {
    return { status: 502, data: { error: "Python backend unavailable" } };
  }
}

// GET /api/styles/genres — list all YAML genre files
router.get("/genres", async (_req, res) => {
  const { status, data } = await pythonGet("/agent/genres");
  return res.status(status).json(data);
});

// GET /api/styles/:id/profile — get one genre YAML
router.get("/:id/profile", async (req, res) => {
  const { id } = req.params;
  if (id === "personas") return; // skip — handled by /personas route above
  const { status, data } = await pythonGet(`/agent/styles/${id}/profile`);
  return res.status(status).json(data);
});

export default router;

// ─── Fallbacks — used if YAML files are unavailable ──────────────────────────
const FALLBACK_PERSONAS: PersonaConfig[] = [
  { id: "modern-pop", name: "פופ מודרני", name_en: "Modern Pop Producer", description: "Tight, polished pop production", preferred_styles: ["pop"], instrumentation_weights: { drums: 1.2, bass: 1.1 }, density_curve: { intro: 0.4, verse: 0.55, chorus: 0.95, outro: 0.3 }, humanization: 0.4, swing: 0.0, fills_density: 0.65, articulation_bias: "rhythmic-punchy", dynamics_shape: "drop-at-chorus", transition_vocabulary: ["build", "drop"], tags: ["polished", "commercial"] },
  { id: "hasidic-wedding", name: "חתונה חסידית", name_en: "Hasidic Wedding", description: "High-energy celebratory", preferred_styles: ["hasidic"], instrumentation_weights: { violin: 1.4, accordion: 1.3, brass: 1.1 }, density_curve: { intro: 0.5, verse: 0.75, chorus: 1.0, outro: 0.4 }, humanization: 0.85, swing: 0.0, fills_density: 0.9, articulation_bias: "staccato-accented", dynamics_shape: "crescendo-to-chorus", transition_vocabulary: ["build", "punch"], tags: ["energetic", "ethnic"] },
  { id: "cinematic", name: "קולנועי", name_en: "Cinematic", description: "Epic orchestral energy", preferred_styles: ["cinematic"], instrumentation_weights: { strings: 1.5, brass: 1.4, piano: 1.2 }, density_curve: { intro: 0.3, verse: 0.55, chorus: 1.0, outro: 0.35 }, humanization: 0.6, swing: 0.0, fills_density: 0.5, articulation_bias: "legato-flowing", dynamics_shape: "arch-climax", transition_vocabulary: ["swell", "riser"], tags: ["dramatic", "epic"] },
];

const FALLBACK_STYLES: StyleConfig[] = [
  { id: "pop", name: "Pop", genre: "Pop" },
  { id: "jazz", name: "Jazz", genre: "Jazz" },
  { id: "rnb", name: "R&B / Soul", genre: "R&B" },
  { id: "classical", name: "Classical", genre: "Classical" },
  { id: "electronic", name: "Electronic", genre: "Electronic" },
  { id: "rock", name: "Rock", genre: "Rock" },
  { id: "bossa_nova", name: "Bossa Nova", genre: "Bossa Nova" },
  { id: "ambient", name: "Ambient", genre: "Ambient" },
  { id: "hasidic", name: "חסידי / Hasidic", nameHe: "חסידי", genre: "Hasidic" },
  { id: "middle_eastern", name: "מזרחי / Middle Eastern", nameHe: "מזרחי", genre: "Middle Eastern" },
  { id: "hiphop", name: "Hip-Hop / Trap", genre: "Hip-Hop" },
  { id: "ballad", name: "Ballad", genre: "Ballad" },
  { id: "cinematic", name: "Cinematic", genre: "Cinematic" },
  { id: "wedding", name: "Wedding Band", genre: "Wedding" },
  { id: "acoustic", name: "Acoustic / Folk", genre: "Acoustic" },
];
