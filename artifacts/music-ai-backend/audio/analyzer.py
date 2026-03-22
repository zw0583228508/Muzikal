"""
Main audio analysis orchestrator — STEP 8.
Full MIR pipeline: ingestion → separation → rhythm → key → chords → melody → vocals → structure.
Each module returns {result, confidence, warnings, alternatives}.
"""

import os
import sys
import logging
import numpy as np

from audio.rhythm import analyze_rhythm
from audio.key_mode import analyze_key
from audio.chords import analyze_chords
from audio.melody import analyze_melody
from audio.structure import analyze_structure

logger = logging.getLogger(__name__)

# Directory for separated stems
STEMS_BASE_DIR = os.environ.get("STEMS_DIR", "/tmp/musicai_stems")

# Try to import the shared ingestion module
try:
    _pkg_root = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "packages")
    if _pkg_root not in sys.path:
        sys.path.insert(0, os.path.normpath(_pkg_root))
    from audio_core.ingestion import ingest_audio
    USE_INGESTION_MODULE = True
    logger.info("Using shared audio_core ingestion module")
except ImportError as _ie:
    USE_INGESTION_MODULE = False
    logger.warning(f"audio_core ingestion module not found ({_ie}); using inline fallback")


def _load_audio_fallback(file_path: str, target_sr: int = 22050):
    """Fallback audio loader when ingestion module is unavailable."""
    import librosa
    y, sr = librosa.load(file_path, sr=target_sr, mono=True)
    y = y / (np.max(np.abs(y)) + 1e-8)
    return y, sr


def _generate_waveform_fallback(y: np.ndarray, num_points: int = 1000) -> list:
    chunk_size = max(1, len(y) // num_points)
    waveform = []
    for i in range(num_points):
        start = i * chunk_size
        end = min(start + chunk_size, len(y))
        if start < len(y):
            chunk = y[start:end]
            waveform.append(float(np.max(np.abs(chunk))))
        else:
            waveform.append(0.0)
    return waveform


def run_full_analysis(audio_file_path: str, project_id: int, progress_callback=None) -> dict:
    """
    Run the full audio analysis pipeline.
    Steps:
      1. Ingest (validate, probe, normalize, waveform, checksum)
      2. Source separation (Demucs or HPSS)
      3. Rhythm analysis
      4. Key/mode analysis
      5. Chord analysis
      6. Melody extraction
      7. Vocal analysis
      8. Structure detection
      9. Confidence aggregation
    """
    logger.info(f"Starting full analysis for project {project_id}: {audio_file_path}")
    all_warnings = []

    def report(step: str, pct: float):
        logger.info(f"[{pct:.0f}%] {step}")
        if progress_callback:
            progress_callback(step, pct)

    # ── Step 1: Ingest ──────────────────────────────────────────────────────
    report("Validating and preprocessing audio", 5)
    file_hash = None
    if USE_INGESTION_MODULE:
        ingestion = ingest_audio(audio_file_path, generate_spectrogram=False)
        y = ingestion["audio"]
        sr = ingestion["sampleRate"]
        duration = ingestion["duration"]
        waveform_data = ingestion["waveform"]
        file_hash = ingestion["fileHash"]
        all_warnings.extend(ingestion.get("warnings", []))
        logger.info(f"Ingested: {duration:.1f}s @ {sr}Hz, hash={file_hash[:8]}")
    else:
        y, sr = _load_audio_fallback(audio_file_path)
        duration = len(y) / sr
        waveform_data = _generate_waveform_fallback(y)
        logger.info(f"Loaded (fallback): {duration:.1f}s @ {sr}Hz")

    # ── Step 2: Waveform ────────────────────────────────────────────────────
    report("Generating waveform visualization", 8)
    # Already generated above during ingestion

    # ── Step 3: Source Separation ───────────────────────────────────────────
    report("Separating audio sources (stems)", 12)
    separation_result = {}
    vocal_stem_path = None
    try:
        from audio.separator import run_source_separation
        separation_result = run_source_separation(audio_file_path, project_id, STEMS_BASE_DIR)
        vocal_stem_path = separation_result.get("stems", {}).get("vocals")
        logger.info(f"Source separation: method={separation_result.get('method')}, stems={list(separation_result.get('stems', {}).keys())}")
    except Exception as e:
        logger.warning(f"Source separation skipped: {e}")

    # ── Step 4: Rhythm ──────────────────────────────────────────────────────
    report("Analyzing rhythm and tempo", 25)
    rhythm = analyze_rhythm(y, sr)

    # ── Step 5: Key/Mode ────────────────────────────────────────────────────
    report("Detecting key and mode", 40)
    key = analyze_key(y, sr)

    # ── Step 6: Chords ──────────────────────────────────────────────────────
    report("Analyzing chord progressions", 55)
    chords = analyze_chords(y, sr, rhythm, key)

    # ── Step 7: Melody ──────────────────────────────────────────────────────
    report("Extracting melody", 68)
    melody = analyze_melody(y, sr, rhythm)

    # ── Step 8: Vocal Analysis ──────────────────────────────────────────────
    report("Analyzing vocals (pitch, vibrato, phrasing)", 78)
    vocal_analysis = {}
    try:
        from audio.vocal_analysis import analyze_vocals
        vocal_analysis = analyze_vocals(vocal_stem_path, y, sr)
        logger.info(f"Vocal analysis: {len(vocal_analysis.get('notes', []))} notes, {len(vocal_analysis.get('phrases', []))} phrases")
    except Exception as e:
        logger.warning(f"Vocal analysis skipped: {e}")

    # ── Step 9: Structure ───────────────────────────────────────────────────
    report("Detecting song structure", 88)
    structure = analyze_structure(y, sr, rhythm)

    # ── Step 9: Confidence aggregation ─────────────────────────────────────
    report("Aggregating confidence scores", 95)
    all_warnings.extend(rhythm.get("warnings", []))
    all_warnings.extend(structure.get("warnings", []))
    if not vocal_stem_path:
        all_warnings.append("Vocal analysis used full mix (no stem separation available) — quality may be lower")

    confidence_data = {
        "overall": round(float(np.mean([
            rhythm.get("confidence", 0.7),
            key.get("confidence", 0.7),
            float(np.mean([c.get("confidence", 0.7) for c in chords.get("chords", [{"confidence": 0.7}])[:20]])),
        ])), 3),
        "rhythm": rhythm.get("confidence", 0.7),
        "key": key.get("confidence", 0.7),
        "chords": float(np.mean([c.get("confidence", 0.7) for c in chords.get("chords", [{"confidence": 0.7}])[:20]])) if chords.get("chords") else 0.7,
        "melody": melody.get("confidence", 0.7),
        "structure": float(np.mean([s.get("confidence", 0.6) for s in structure.get("sections", [{"confidence": 0.6}])])),
        "vocals": vocal_analysis.get("confidence", 0.0) if vocal_analysis else 0.0,
    }

    report("Analysis complete", 100)

    return {
        "project_id": project_id,
        "duration": round(duration, 2),
        "sampleRate": sr,
        "fileHash": file_hash,
        "rhythm": rhythm,
        "key": key,
        "chords": chords,
        "melody": melody,
        "vocals": vocal_analysis,
        "structure": structure,
        "waveformData": waveform_data,
        "confidenceData": confidence_data,
        "sourceSeparation": {
            "method": separation_result.get("method", "none"),
            "stems": list(separation_result.get("stems", {}).keys()),
            "qualityScores": separation_result.get("quality_scores", {}),
            "warnings": separation_result.get("warnings", []),
        },
        "warnings": all_warnings,
    }
