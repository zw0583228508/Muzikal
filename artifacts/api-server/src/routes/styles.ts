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

export default router;

// ─── Fallback — used if YAML file is unavailable ──────────────────────────────
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
