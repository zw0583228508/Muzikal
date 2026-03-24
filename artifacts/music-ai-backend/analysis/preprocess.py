"""
Audio preprocessing stage.
Loads, normalizes, resamples, and produces a normalized artifact bundle.
"""

from __future__ import annotations

import os
import logging
import hashlib
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
import librosa

from analysis.schemas import AudioMeta

logger = logging.getLogger(__name__)

# Standard sample rates
SR_STANDARD = 44100   # for stem separation
SR_ANALYSIS = 22050   # for most analysis tasks
SR_PITCH = 16000      # for torchcrepe (optional downsampled path)

TARGET_LOUDNESS_DBFS = -23.0  # EBU R128 reference


def _rms_dbfs(y: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(y ** 2)))
    if rms < 1e-10:
        return -120.0
    return float(20 * np.log10(rms))


def _normalize_loudness(y: np.ndarray, target_dbfs: float = TARGET_LOUDNESS_DBFS) -> np.ndarray:
    """RMS-based loudness normalization."""
    current = _rms_dbfs(y)
    if current < -90:
        return y
    gain_db = target_dbfs - current
    gain_linear = 10 ** (gain_db / 20)
    normalized = y * gain_linear
    # Peak limit to avoid clipping
    peak = np.max(np.abs(normalized))
    if peak > 0.99:
        normalized = normalized * (0.99 / peak)
    return normalized


def _trim_silence(y: np.ndarray, sr: int, top_db: float = 40.0) -> np.ndarray:
    """Conservative silence trim — removes only leading/trailing silence."""
    try:
        yt, _ = librosa.effects.trim(y, top_db=top_db, frame_length=2048, hop_length=512)
        # Only trim if we removed < 10 seconds total
        if len(y) - len(yt) < sr * 10:
            return yt
        return y
    except Exception:
        return y


def load_audio(
    file_path: str,
    target_sr: int = SR_STANDARD,
    mono: bool = True,
    normalize: bool = True,
    trim: bool = True,
) -> Tuple[np.ndarray, int]:
    """
    Load audio file to numpy array.
    Returns (waveform, sample_rate).
    """
    try:
        y, sr = librosa.load(file_path, sr=target_sr, mono=mono)
    except Exception as e:
        logger.warning("librosa.load failed (%s), trying soundfile", e)
        data, sr = sf.read(file_path, always_2d=True)
        y = data.mean(axis=1) if mono else data.T
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr

    if normalize:
        y = _normalize_loudness(y)
    if trim:
        y = _trim_silence(y, sr)

    return y, sr


class AudioBundle:
    """Normalized audio artifact bundle produced by preprocessing."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_hash: Optional[str] = None

        # Full-res stereo for separation
        self.y_stereo: Optional[np.ndarray] = None
        self.sr_stereo: int = SR_STANDARD

        # Mono analysis waveform
        self.y_mono: np.ndarray = np.zeros(1)
        self.sr: int = SR_ANALYSIS

        self.duration: float = 0.0
        self.channels: int = 1
        self.rms: float = 0.0

    @property
    def meta(self) -> AudioMeta:
        return AudioMeta(
            duration=self.duration,
            sample_rate=self.sr,
            channels=self.channels,
            rms=self.rms,
            file_path=self.file_path,
            file_hash=self.file_hash,
        )


def preprocess(file_path: str) -> AudioBundle:
    """
    Full preprocessing pipeline.
    Returns an AudioBundle ready for all downstream analyzers.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    bundle = AudioBundle(file_path)

    # Compute file hash for caching
    from analysis.cache import compute_file_hash
    bundle.file_hash = compute_file_hash(file_path)

    # Load high-res for stem separation (stereo, 44100)
    try:
        bundle.y_stereo, bundle.sr_stereo = load_audio(
            file_path, target_sr=SR_STANDARD, mono=False, normalize=True, trim=False
        )
        bundle.channels = bundle.y_stereo.shape[0] if bundle.y_stereo.ndim > 1 else 1
    except Exception as e:
        logger.warning("Stereo load failed: %s — falling back to mono", e)
        bundle.y_stereo = None
        bundle.channels = 1

    # Load mono for analysis
    bundle.y_mono, bundle.sr = load_audio(
        file_path, target_sr=SR_ANALYSIS, mono=True, normalize=True, trim=True
    )

    bundle.duration = float(len(bundle.y_mono)) / bundle.sr
    bundle.rms = float(np.sqrt(np.mean(bundle.y_mono ** 2)))

    logger.info(
        "Preprocessed %s: duration=%.1fs sr=%d hash=%s",
        os.path.basename(file_path), bundle.duration, bundle.sr, bundle.file_hash[:8]
    )
    return bundle
