"""
Source Separation Engine.
Uses Demucs (htdemucs model) for state-of-the-art source separation.
Falls back to librosa HPSS when Demucs is unavailable.

Output stems:
  - vocals.wav
  - drums.wav
  - bass.wav
  - other.wav
"""

import os
import logging
import tempfile
import subprocess
import shutil
import numpy as np
import soundfile as sf
import librosa

logger = logging.getLogger(__name__)

DEMUCS_MODEL = "htdemucs"  # 4-stem hybrid model


def separate_with_demucs(audio_path: str, output_dir: str) -> dict:
    """
    Run Demucs source separation via subprocess.
    Returns dict mapping stem name → file path.
    """
    logger.info(f"Running Demucs ({DEMUCS_MODEL}) on: {audio_path}")
    try:
        cmd = [
            "python3", "-m", "demucs",
            "--two-stems", "vocals",  # Fast: only separate vocals vs accompaniment
            "--model", DEMUCS_MODEL,
            "--out", output_dir,
            "--mp3",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning(f"Demucs stderr: {result.stderr}")
            raise RuntimeError(f"Demucs failed: {result.stderr[:200]}")

        # Full 4-stem mode
        cmd_full = [
            "python3", "-m", "demucs",
            "--model", DEMUCS_MODEL,
            "--out", output_dir,
            audio_path,
        ]
        result2 = subprocess.run(cmd_full, capture_output=True, text=True, timeout=600)
        if result2.returncode != 0:
            raise RuntimeError(f"Demucs 4-stem failed: {result2.stderr[:200]}")

        # Find output files
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        stems_dir = os.path.join(output_dir, DEMUCS_MODEL, base_name)

        stems = {}
        for stem in ["vocals", "drums", "bass", "other"]:
            stem_path = os.path.join(stems_dir, f"{stem}.wav")
            if os.path.exists(stem_path):
                stems[stem] = stem_path
            else:
                # Try mp3
                stem_path_mp3 = os.path.join(stems_dir, f"{stem}.mp3")
                if os.path.exists(stem_path_mp3):
                    stems[stem] = stem_path_mp3

        logger.info(f"Demucs produced stems: {list(stems.keys())}")
        return stems

    except Exception as e:
        logger.warning(f"Demucs failed ({e}), falling back to HPSS")
        return {}


def separate_with_hpss(y: np.ndarray, sr: int, output_dir: str) -> dict:
    """
    Fallback: Harmonic-Percussive Source Separation using librosa.
    Not as good as Demucs but works without GPU.
    """
    logger.info("Running HPSS source separation (librosa fallback)")

    # HPSS
    y_harmonic, y_percussive = librosa.effects.hpss(y, margin=8)

    # Estimate vocals using spectral subtraction (simplified)
    # Vocals tend to be in mid-frequency range with harmonic content
    stft = librosa.stft(y)
    stft_harm = librosa.stft(y_harmonic)
    stft_perc = librosa.stft(y_percussive)

    # Bass: low frequencies of harmonic
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = freqs < 300
    stft_bass = stft_harm.copy()
    stft_bass[~bass_mask] = 0
    y_bass = librosa.istft(stft_bass, length=len(y))

    # Other: high frequency harmonic content
    stft_other = stft_harm.copy()
    stft_other[bass_mask] = 0
    y_other = librosa.istft(stft_other, length=len(y))

    stems = {}
    stem_data = {
        "vocals": y_harmonic,
        "drums": y_percussive,
        "bass": y_bass,
        "other": y_other,
    }

    for stem_name, stem_audio in stem_data.items():
        stem_path = os.path.join(output_dir, f"{stem_name}.wav")
        sf.write(stem_path, stem_audio, sr)
        stems[stem_name] = stem_path

    return stems


def score_separation_quality(stems: dict) -> dict:
    """
    Score each stem's quality (signal-to-noise proxy).
    Returns dict of stem → quality score (0-1).
    """
    scores = {}
    for stem_name, path in stems.items():
        try:
            y, _ = librosa.load(path, sr=None, mono=True)
            rms = float(np.sqrt(np.mean(y ** 2)))
            # Higher RMS = more content = higher quality
            scores[stem_name] = min(1.0, rms * 10)
        except Exception:
            scores[stem_name] = 0.0
    return scores


def run_source_separation(audio_path: str, project_id: int, output_base_dir: str) -> dict:
    """
    Main entry point for source separation.
    Tries Demucs first, falls back to HPSS.

    Returns:
        {
            "method": "demucs" or "hpss",
            "stems": {
                "vocals": "/path/to/vocals.wav",
                "drums": "/path/to/drums.wav",
                "bass": "/path/to/bass.wav",
                "other": "/path/to/other.wav",
            },
            "quality_scores": {...},
        }
    """
    project_stems_dir = os.path.join(output_base_dir, f"project_{project_id}", "stems")
    os.makedirs(project_stems_dir, exist_ok=True)

    # Try Demucs first
    stems = separate_with_demucs(audio_path, project_stems_dir)
    method = "demucs"

    if not stems:
        # Load audio for HPSS fallback
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        stems = separate_with_hpss(y, sr, project_stems_dir)
        method = "hpss"

    quality = score_separation_quality(stems)

    logger.info(f"Source separation complete ({method}): {list(stems.keys())}")

    return {
        "method": method,
        "stems": stems,
        "quality_scores": quality,
    }
