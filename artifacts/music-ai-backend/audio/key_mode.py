"""
Key & Mode Engine: Global key, mode, modulation detection.
Uses HPCP/chroma analysis with sliding window.
"""

import logging
import numpy as np
import librosa
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Krumhansl-Schmuckler key profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def chroma_to_key(chroma_vector: np.ndarray):
    """Find best matching key using Krumhansl-Schmuckler profiles."""
    best_score = -np.inf
    best_key = "C"
    best_mode = "major"

    for i, note in enumerate(NOTE_NAMES):
        rolled_major = np.roll(MAJOR_PROFILE, i)
        rolled_minor = np.roll(MINOR_PROFILE, i)

        score_major = np.corrcoef(chroma_vector, rolled_major)[0, 1]
        score_minor = np.corrcoef(chroma_vector, rolled_minor)[0, 1]

        if score_major > best_score:
            best_score = score_major
            best_key = note
            best_mode = "major"
            best_confidence = float(score_major)

        if score_minor > best_score:
            best_score = score_minor
            best_key = note + "m"
            best_mode = "minor"
            best_confidence = float(score_minor)

    return best_key, best_mode, max(0.0, min(1.0, (best_score + 1) / 2))


def chroma_to_key_top_k(chroma_vector: np.ndarray, k: int = 3) -> List[Dict]:
    """Return top-k key candidates with scores."""
    scores = []
    for i, note in enumerate(NOTE_NAMES):
        rolled_major = np.roll(MAJOR_PROFILE, i)
        rolled_minor = np.roll(MINOR_PROFILE, i)
        score_major = float(np.corrcoef(chroma_vector, rolled_major)[0, 1])
        score_minor = float(np.corrcoef(chroma_vector, rolled_minor)[0, 1])
        scores.append((note, "major", score_major))
        scores.append((note + "m", "minor", score_minor))
    scores.sort(key=lambda x: x[2], reverse=True)
    return [
        {"key": s[0], "mode": s[1], "score": round(max(0.0, min(1.0, (s[2] + 1) / 2)), 3)}
        for s in scores[:k]
    ]


def analyze_key(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Full key and mode analysis with modulation detection.
    Uses HPCP chroma features with sliding window.
    """
    logger.info("Running key analysis...")

    hop_length = 512

    # Compute CQT-based chroma for better pitch accuracy
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length, n_chroma=12)

    # Global key from full chroma sum
    global_chroma = chroma.mean(axis=1)
    global_key, global_mode, confidence = chroma_to_key(global_chroma)

    # Top-k alternative keys
    top_keys = chroma_to_key_top_k(global_chroma, k=4)
    alternatives = [k["key"] for k in top_keys if k["key"] != global_key][:3]

    # Sliding window for modulation detection
    window_size = max(int(sr * 8 / hop_length), 32)
    step_size = max(int(sr * 4 / hop_length), 16)

    modulations = []
    prev_key = global_key

    for start in range(0, chroma.shape[1] - window_size, step_size):
        end = start + window_size
        window_chroma = chroma[:, start:end].mean(axis=1)
        key, mode, conf = chroma_to_key(window_chroma)
        time_seconds = start * hop_length / sr

        if key != prev_key and conf > 0.6 and time_seconds > 4.0:
            modulations.append({
                "timeSeconds": round(time_seconds, 2),
                "fromKey": prev_key,
                "toKey": key,
                "confidence": round(float(conf), 3),
            })
            prev_key = key

    warnings = []
    if confidence < 0.55:
        warnings.append(f"Low key confidence ({confidence:.0%}) — chromatic or atonal content possible")
    if len(modulations) > 3:
        warnings.append(f"{len(modulations)} modulations detected — complex harmonic structure")
    if len(modulations) == 0 and confidence < 0.6:
        warnings.append("Key detection uncertain — consider verifying manually")

    logger.info(f"Key: {global_key} {global_mode}, confidence={confidence:.2f}, modulations={len(modulations)}")

    return {
        "globalKey": global_key,
        "mode": global_mode,
        "confidence": round(confidence, 3),
        "alternatives": alternatives,
        "warnings": warnings,
        "modulations": modulations,
        "model": "chroma-cqt-ks",
    }
