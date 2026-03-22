"""
Mixing & Mastering Engine.
Applies professional mixing chain:
  1. Per-track: high-pass filter, EQ, compression
  2. Master bus: EQ, multiband compression, peak limiting, LUFS normalization
"""

import numpy as np
import logging
from scipy import signal
from typing import Optional

logger = logging.getLogger(__name__)

SR = 44100


# ── Utility Filters ──────────────────────────────────────────────────────────

def highpass_filter(audio: np.ndarray, cutoff_hz: float, sr: int = SR,
                    order: int = 2) -> np.ndarray:
    """Remove rumble below cutoff."""
    sos = signal.butter(order, cutoff_hz, btype='high', fs=sr, output='sos')
    if audio.ndim == 2:
        return np.column_stack([signal.sosfilt(sos, audio[:, i]) for i in range(audio.shape[1])])
    return signal.sosfilt(sos, audio)


def lowpass_filter(audio: np.ndarray, cutoff_hz: float, sr: int = SR,
                   order: int = 2) -> np.ndarray:
    """Remove harshness above cutoff."""
    sos = signal.butter(order, cutoff_hz, btype='low', fs=sr, output='sos')
    if audio.ndim == 2:
        return np.column_stack([signal.sosfilt(sos, audio[:, i]) for i in range(audio.shape[1])])
    return signal.sosfilt(sos, audio)


def shelf_eq(audio: np.ndarray, freq: float, gain_db: float,
             shelf_type: str = 'high', sr: int = SR) -> np.ndarray:
    """Apply shelving EQ."""
    gain_lin = 10 ** (gain_db / 20)
    if abs(gain_db) < 0.1:
        return audio
    # Simple shelf via blend of highpass/lowpass
    if shelf_type == 'high':
        hp = highpass_filter(audio, freq, sr)
        return audio + hp * (gain_lin - 1)
    else:
        lp = lowpass_filter(audio, freq, sr)
        return audio + lp * (gain_lin - 1)


def peak_eq(audio: np.ndarray, freq: float, gain_db: float,
            q: float = 1.0, sr: int = SR) -> np.ndarray:
    """Apply peaking EQ band."""
    if abs(gain_db) < 0.1:
        return audio
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / sr
    alpha = np.sin(w0) / (2 * q)

    b0 = 1 + alpha * A
    b1 = -2 * np.cos(w0)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha / A

    b = np.array([b0 / a0, b1 / a0, b2 / a0])
    a = np.array([1.0, a1 / a0, a2 / a0])

    if audio.ndim == 2:
        return np.column_stack([signal.lfilter(b, a, audio[:, i]) for i in range(audio.shape[1])])
    return signal.lfilter(b, a, audio)


# ── Dynamics Processing ──────────────────────────────────────────────────────

def rms_compression(audio: np.ndarray, threshold_db: float = -18.0,
                    ratio: float = 4.0, attack_ms: float = 5.0,
                    release_ms: float = 50.0, makeup_db: float = 0.0,
                    sr: int = SR) -> np.ndarray:
    """
    RMS-based dynamic compressor with attack/release smoothing.
    """
    threshold_lin = 10 ** (threshold_db / 20)
    makeup_lin = 10 ** (makeup_db / 20)
    attack_coeff = np.exp(-1 / (sr * attack_ms / 1000))
    release_coeff = np.exp(-1 / (sr * release_ms / 1000))

    mono = audio if audio.ndim == 1 else np.mean(audio, axis=1)

    # Compute RMS envelope
    window = max(1, int(sr * 0.005))  # 5ms window
    rms = np.zeros_like(mono)
    for i in range(len(mono)):
        start = max(0, i - window)
        rms[i] = np.sqrt(np.mean(mono[start:i + 1] ** 2) + 1e-12)

    # Gain reduction
    gain = np.ones(len(mono))
    current_gain = 1.0

    for i in range(len(mono)):
        level = rms[i]
        if level > threshold_lin:
            target_gain = (threshold_lin + (level - threshold_lin) / ratio) / (level + 1e-12)
        else:
            target_gain = 1.0

        if target_gain < current_gain:
            current_gain = attack_coeff * current_gain + (1 - attack_coeff) * target_gain
        else:
            current_gain = release_coeff * current_gain + (1 - release_coeff) * target_gain

        gain[i] = current_gain * makeup_lin

    # Apply gain
    if audio.ndim == 2:
        return audio * gain[:, np.newaxis]
    return audio * gain


def peak_limiter(audio: np.ndarray, ceiling_db: float = -0.3) -> np.ndarray:
    """
    Brickwall peak limiter. Ensures no sample exceeds ceiling.
    """
    ceiling_lin = 10 ** (ceiling_db / 20)
    peak = np.max(np.abs(audio))
    if peak > ceiling_lin:
        audio = audio * (ceiling_lin / peak)
    # Soft clip near ceiling for warmth
    audio = np.tanh(audio * 1.5) * ceiling_lin / np.tanh(1.5)
    return audio


def lufs_normalize(audio: np.ndarray, target_lufs: float = -14.0,
                   sr: int = SR) -> np.ndarray:
    """
    Normalize audio to target LUFS (simplified integrated loudness).
    Uses RMS as proxy for LUFS.
    """
    if audio.ndim == 2:
        rms = np.sqrt(np.mean(audio ** 2))
    else:
        rms = np.sqrt(np.mean(audio ** 2))

    if rms < 1e-12:
        return audio

    # Convert target LUFS to RMS (approximate mapping)
    # LUFS ≈ RMS - 0.691 dB for typical music
    target_rms_db = target_lufs + 0.691
    current_rms_db = 20 * np.log10(rms + 1e-12)
    gain_db = target_rms_db - current_rms_db
    gain_lin = 10 ** (gain_db / 20)

    logger.info(f"LUFS normalization: {current_rms_db:.1f} dBFS → {target_rms_db:.1f} dBFS ({gain_db:+.1f} dB)")
    return audio * gain_lin


# ── Per-Track Processing Chain ───────────────────────────────────────────────

TRACK_EQ_PRESETS = {
    "drums": {
        "hp_hz": 30, "ls_freq": 80, "ls_gain": 2.0,
        "peaks": [(3000, 2.0, 2.0), (8000, 1.5, 1.5)],
    },
    "bass": {
        "hp_hz": 20, "ls_freq": 60, "ls_gain": 3.0,
        "peaks": [(250, -2.0, 1.0), (800, 1.5, 2.0)],
    },
    "piano": {
        "hp_hz": 60, "ls_freq": 80, "ls_gain": -1.0,
        "peaks": [(3000, 1.5, 1.5), (10000, 2.0, 1.5)],
    },
    "guitar": {
        "hp_hz": 80, "ls_freq": 100, "ls_gain": -2.0,
        "peaks": [(2500, 2.0, 2.0), (5000, 1.5, 2.0)],
    },
    "strings": {
        "hp_hz": 60, "ls_freq": 80, "ls_gain": -1.0,
        "peaks": [(4000, 1.5, 1.5), (10000, 2.0, 1.5)],
    },
    "pad": {
        "hp_hz": 80, "ls_freq": 100, "ls_gain": -2.0,
        "peaks": [(1000, -1.0, 1.0), (8000, 1.0, 2.0)],
    },
    "lead": {
        "hp_hz": 100, "ls_freq": 120, "ls_gain": -3.0,
        "peaks": [(2000, 2.0, 1.5), (6000, 2.0, 2.0)],
    },
    "vocals": {
        "hp_hz": 80, "ls_freq": 100, "ls_gain": -1.0,
        "peaks": [(3000, 2.5, 1.5), (8000, 2.0, 1.5), (250, -1.5, 1.0)],
    },
    "default": {
        "hp_hz": 40, "ls_freq": 80, "ls_gain": 0.0,
        "peaks": [],
    },
}

TRACK_COMP_PRESETS = {
    "drums": {"threshold_db": -20, "ratio": 5.0, "attack_ms": 2, "release_ms": 30, "makeup_db": 3},
    "bass": {"threshold_db": -18, "ratio": 4.0, "attack_ms": 5, "release_ms": 50, "makeup_db": 2},
    "piano": {"threshold_db": -22, "ratio": 3.0, "attack_ms": 10, "release_ms": 80, "makeup_db": 2},
    "guitar": {"threshold_db": -20, "ratio": 4.0, "attack_ms": 5, "release_ms": 60, "makeup_db": 2},
    "strings": {"threshold_db": -24, "ratio": 2.5, "attack_ms": 20, "release_ms": 100, "makeup_db": 2},
    "pad": {"threshold_db": -24, "ratio": 2.0, "attack_ms": 30, "release_ms": 150, "makeup_db": 1},
    "lead": {"threshold_db": -18, "ratio": 4.0, "attack_ms": 5, "release_ms": 40, "makeup_db": 3},
    "vocals": {"threshold_db": -20, "ratio": 4.0, "attack_ms": 5, "release_ms": 60, "makeup_db": 4},
    "default": {"threshold_db": -22, "ratio": 3.0, "attack_ms": 10, "release_ms": 60, "makeup_db": 2},
}


def process_track(audio: np.ndarray, inst_type: str, sr: int = SR) -> np.ndarray:
    """Apply per-track mixing chain: EQ → Compression."""
    eq_preset = TRACK_EQ_PRESETS.get(inst_type, TRACK_EQ_PRESETS["default"])
    comp_preset = TRACK_COMP_PRESETS.get(inst_type, TRACK_COMP_PRESETS["default"])

    # High-pass to remove rumble
    audio = highpass_filter(audio, eq_preset["hp_hz"], sr)

    # Low shelf EQ
    if abs(eq_preset["ls_gain"]) > 0.1:
        audio = shelf_eq(audio, eq_preset["ls_freq"], eq_preset["ls_gain"], "low", sr)

    # Peaking EQ bands
    for freq, gain_db, q in eq_preset.get("peaks", []):
        audio = peak_eq(audio, freq, gain_db, q, sr)

    # Compression
    audio = rms_compression(audio, sr=sr, **comp_preset)

    return audio


# ── Master Bus Chain ─────────────────────────────────────────────────────────

def apply_master_bus(mix: np.ndarray, sr: int = SR,
                     target_lufs: float = -14.0) -> np.ndarray:
    """
    Master bus processing:
    1. Gentle high-shelf air boost
    2. Low-shelf warmth boost
    3. Mid-side slight widening
    4. Glue compression
    5. Peak limiter
    6. LUFS normalization
    """
    # 1. High shelf air boost (+1.5 dB at 12kHz)
    mix = shelf_eq(mix, 12000, 1.5, "high", sr)

    # 2. Low shelf warmth (+1 dB at 120Hz)
    mix = shelf_eq(mix, 120, 1.0, "low", sr)

    # 3. Mid-side stereo widening (subtle 15%)
    if mix.ndim == 2 and mix.shape[1] == 2:
        mid = (mix[:, 0] + mix[:, 1]) * 0.5
        side = (mix[:, 0] - mix[:, 1]) * 0.5
        side *= 1.15  # Widen sides slightly
        mix = np.column_stack([mid + side, mid - side])

    # 4. Glue compression (gentle bus comp)
    mix = rms_compression(
        mix, threshold_db=-18, ratio=2.0,
        attack_ms=30, release_ms=200, makeup_db=1.5, sr=sr
    )

    # 5. Peak limiter (-0.3 dBFS ceiling)
    mix = peak_limiter(mix, ceiling_db=-0.3)

    # 6. LUFS normalization to streaming target
    mix = lufs_normalize(mix, target_lufs, sr)

    # Final peak limiter safety pass
    mix = peak_limiter(mix, ceiling_db=-0.1)

    return mix.astype(np.float32)


# ── Full Mix Pipeline ─────────────────────────────────────────────────────────

def mix_tracks(rendered_tracks: list, inst_types: list,
               sr: int = SR, progress_callback=None) -> np.ndarray:
    """
    Mix multiple rendered track buffers with per-track processing.
    Args:
        rendered_tracks: list of (np.ndarray shape [n_samples, 2])
        inst_types: list of instrument type strings (matching rendered_tracks)
    Returns:
        Stereo float32 mix array
    """
    if not rendered_tracks:
        return np.zeros((sr, 2), dtype=np.float32)

    n_samples = max(len(t) for t in rendered_tracks)
    mix = np.zeros((n_samples, 2), dtype=np.float64)

    for i, (track_audio, inst_type) in enumerate(zip(rendered_tracks, inst_types)):
        if progress_callback:
            pct = int(80 + (i / len(rendered_tracks)) * 10)
            progress_callback(f"Mixing {inst_type}", pct)

        try:
            processed = process_track(track_audio, inst_type, sr)
            # Pad/trim to mix length
            if len(processed) < n_samples:
                pad = np.zeros((n_samples - len(processed), 2))
                processed = np.vstack([processed, pad])
            elif len(processed) > n_samples:
                processed = processed[:n_samples]
            mix += processed
        except Exception as e:
            logger.warning(f"Track mixing failed ({inst_type}): {e}")
            # Add unprocessed
            if len(track_audio) <= n_samples:
                mix[:len(track_audio)] += track_audio
            else:
                mix += track_audio[:n_samples]

    return mix.astype(np.float32)
