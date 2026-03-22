"""
Main audio analysis orchestrator.
Full MIR pipeline: source separation, rhythm, key, chords, melody, vocal analysis, structure.
"""

import os
import logging
import numpy as np
import soundfile as sf
import librosa

from audio.rhythm import analyze_rhythm
from audio.key_mode import analyze_key
from audio.chords import analyze_chords
from audio.melody import analyze_melody
from audio.structure import analyze_structure

logger = logging.getLogger(__name__)

# Directory for separated stems
STEMS_BASE_DIR = os.environ.get("STEMS_DIR", "/tmp/musicai_stems")


def load_audio(file_path: str, target_sr: int = 22050):
    """Load and normalize audio file."""
    logger.info(f"Loading audio: {file_path}")
    y, sr = librosa.load(file_path, sr=target_sr, mono=True)
    y = librosa.util.normalize(y)
    return y, sr


def generate_waveform_data(y: np.ndarray, num_points: int = 1000) -> list:
    """Generate downsampled waveform for display."""
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
      1. Load audio
      2. Waveform generation
      3. Source separation (Demucs or HPSS)
      4. Rhythm analysis
      5. Key/mode analysis
      6. Chord analysis
      7. Melody extraction
      8. Vocal analysis
      9. Structure detection
    """
    logger.info(f"Starting full analysis for project {project_id}: {audio_file_path}")

    def report(step: str, pct: float):
        logger.info(f"[{pct:.0f}%] {step}")
        if progress_callback:
            progress_callback(step, pct)

    # ── Step 1: Load audio ──────────────────────────────────────────────────
    report("Loading and preprocessing audio", 5)
    y, sr = load_audio(audio_file_path)
    duration = len(y) / sr
    logger.info(f"Loaded: {duration:.1f}s @ {sr}Hz")

    # ── Step 2: Waveform ────────────────────────────────────────────────────
    report("Generating waveform visualization", 8)
    waveform_data = generate_waveform_data(y)

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

    report("Analysis complete", 100)

    return {
        "project_id": project_id,
        "duration": round(duration, 2),
        "sampleRate": sr,
        "rhythm": rhythm,
        "key": key,
        "chords": chords,
        "melody": melody,
        "vocals": vocal_analysis,
        "structure": structure,
        "waveformData": waveform_data,
        "sourceSeparation": {
            "method": separation_result.get("method", "none"),
            "stems": list(separation_result.get("stems", {}).keys()),
            "qualityScores": separation_result.get("quality_scores", {}),
        },
    }
