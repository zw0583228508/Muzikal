"""
Main audio analysis orchestrator.
Runs the full MIR pipeline: rhythm, key, chords, melody, structure.
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


def load_audio(file_path: str, target_sr: int = 22050):
    """Load and normalize audio file."""
    logger.info(f"Loading audio: {file_path}")
    y, sr = librosa.load(file_path, sr=target_sr, mono=True)
    # Normalize loudness
    y = librosa.util.normalize(y)
    return y, sr


def generate_waveform_data(y: np.ndarray, num_points: int = 1000) -> list:
    """Generate downsampled waveform data for display."""
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
    Returns complete analysis results dict.
    """
    logger.info(f"Starting full analysis for project {project_id}: {audio_file_path}")

    def report(step: str, pct: float):
        logger.info(f"[{pct:.0f}%] {step}")
        if progress_callback:
            progress_callback(step, pct)

    # Step 1: Load audio
    report("Loading and preprocessing audio", 5)
    y, sr = load_audio(audio_file_path)
    duration = len(y) / sr
    logger.info(f"Loaded audio: {duration:.1f}s at {sr}Hz")

    # Step 2: Generate waveform for display
    report("Generating waveform visualization", 10)
    waveform_data = generate_waveform_data(y)

    # Step 3: Rhythm analysis
    report("Analyzing rhythm and tempo", 20)
    rhythm = analyze_rhythm(y, sr)

    # Step 4: Key and mode analysis
    report("Detecting key and mode", 40)
    key = analyze_key(y, sr)

    # Step 5: Chord analysis
    report("Analyzing chord progressions", 55)
    chords = analyze_chords(y, sr, rhythm, key)

    # Step 6: Melody extraction
    report("Extracting melody", 70)
    melody = analyze_melody(y, sr, rhythm)

    # Step 7: Structure analysis
    report("Detecting song structure", 85)
    structure = analyze_structure(y, sr, rhythm)

    report("Analysis complete", 100)

    return {
        "project_id": project_id,
        "rhythm": rhythm,
        "key": key,
        "chords": chords,
        "melody": melody,
        "structure": structure,
        "waveformData": waveform_data,
    }
