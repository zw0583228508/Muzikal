"""
Key / scale / mode detection.

Primary:  Essentia KeyExtractor + HPCP on the "other" stem
Secondary: Essentia on full mix
Fallback: librosa chroma + Krumhansl-Schmuckler correlation

Supports:
  - Global key detection
  - Segmented key detection (time-varying key analysis)
  - Modulation detection
  - Parallel / relative key alternatives
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

import numpy as np
import librosa

from analysis.schemas import KeyResult, KeySegment
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Krumhansl-Schmuckler key profiles (major / minor)
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENHARMONIC = {
    "C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb",
}

# Relative / parallel key relationships
_RELATIVE_MAJOR_OFFSET = 3  # minor root + 3 semitones = relative major
_RELATIVE_MINOR_OFFSET = -3  # major root - 3 semitones = relative minor


def _note_to_idx(note: str) -> int:
    note = note.replace("b", "#").strip()
    clean = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}.get(note, note)
    return NOTE_NAMES.index(clean) if clean in NOTE_NAMES else 0


def _idx_to_note(idx: int, prefer_sharp: bool = True) -> str:
    name = NOTE_NAMES[idx % 12]
    if not prefer_sharp and name in ENHARMONIC:
        return ENHARMONIC[name]
    return name


def _ks_correlation(chroma_mean: np.ndarray) -> Tuple[int, str, float]:
    """
    Krumhansl-Schmuckler key correlation.
    Returns (root_idx, mode, confidence).
    """
    best_corr = -999.0
    best_root = 0
    best_mode = "major"

    for root in range(12):
        rolled_major = np.roll(_KS_MAJOR, root)
        rolled_minor = np.roll(_KS_MINOR, root)

        corr_major = float(np.corrcoef(chroma_mean, rolled_major)[0, 1])
        corr_minor = float(np.corrcoef(chroma_mean, rolled_minor)[0, 1])

        if corr_major > best_corr:
            best_corr = corr_major
            best_root = root
            best_mode = "major"
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_root = root
            best_mode = "minor"

    # Normalize correlation to [0, 1]
    confidence = float(np.clip((best_corr + 1) / 2, 0, 1))
    return best_root, best_mode, confidence


def _detect_key_librosa(y: np.ndarray, sr: int) -> Tuple[str, str, float, List[dict]]:
    """Librosa-based key detection via CQT chroma + K-S profiles."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=36, hop_length=512)
    chroma_mean = chroma.mean(axis=1)

    # Get all 24 keys ranked
    scores = []
    for root in range(12):
        for mode, profile in [("major", _KS_MAJOR), ("minor", _KS_MINOR)]:
            rolled = np.roll(profile, root)
            corr = float(np.corrcoef(chroma_mean, rolled)[0, 1])
            scores.append((corr, root, mode))

    scores.sort(key=lambda x: -x[0])
    best_corr, best_root, best_mode = scores[0]
    confidence = float(np.clip((best_corr + 1) / 2, 0, 1))

    note = _idx_to_note(best_root)
    alternatives = [
        {"key": _idx_to_note(r), "mode": m, "confidence": round((c + 1) / 2, 3)}
        for c, r, m in scores[1:5]
    ]
    return note, best_mode, confidence, alternatives


def _detect_key_essentia(y: np.ndarray, sr: int, stem_path: Optional[str] = None) -> Tuple[str, str, float, List[dict]]:
    """Essentia-based key detection."""
    try:
        import essentia.standard as es

        # Load audio from path or use array
        if stem_path and __import__("os").path.exists(stem_path):
            loader = es.MonoLoader(filename=stem_path, sampleRate=44100)
            audio = loader()
        else:
            # Resample to 44100 if needed
            if sr != 44100:
                y_44k = librosa.resample(y, orig_sr=sr, target_sr=44100)
            else:
                y_44k = y
            audio = y_44k.astype(np.float32)

        # HPCP (Harmonic Pitch Class Profile)
        windowing = es.Windowing(type="blackmanharris62")
        spectrum = es.Spectrum()
        spectral_peaks = es.SpectralPeaks(
            magnitudeThreshold=0.00001, maxPeaks=60, maxFrequency=3500,
            minFrequency=40, orderBy="magnitude", sampleRate=44100
        )
        hpcp = es.HPCP(size=36, referenceFrequency=440)
        key_extractor = es.KeyExtractor(profileType="temperley", useThreeChords=True)

        # Build HPCP vector
        frame_size = 4096
        hop_size = 2048
        hpcp_frames = []

        for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size, startFromZero=True):
            windowed = windowing(frame)
            spec = spectrum(windowed)
            freqs, mags = spectral_peaks(spec)
            hpcp_frame = hpcp(freqs, mags)
            hpcp_frames.append(hpcp_frame)

        if not hpcp_frames:
            return _detect_key_librosa(y, sr)

        hpcp_mean = np.mean(hpcp_frames, axis=0)

        # Key extraction from HPCP
        key_alg = es.Key(profileType="temperley")
        key_name, scale, strength, _ = key_alg(hpcp_mean.astype(np.float32))

        confidence = float(min(1.0, strength))
        mode = "minor" if scale == "minor" else "major"

        # Build alternatives via librosa K-S
        _, _, _, alternatives = _detect_key_librosa(y, sr)

        return key_name, mode, confidence, alternatives

    except Exception as e:
        logger.warning("Essentia key detection failed: %s — using librosa", e)
        return _detect_key_librosa(y, sr)


def _segment_keys(y: np.ndarray, sr: int, duration: float, segment_duration: float = 30.0) -> List[KeySegment]:
    """Detect key in sliding windows to capture modulations."""
    segments = []
    hop = segment_duration / 2
    t = 0.0

    while t < duration - segment_duration / 2:
        start = t
        end = min(t + segment_duration, duration)
        s_start = int(start * sr)
        s_end = int(end * sr)
        y_seg = y[s_start:s_end]

        if len(y_seg) < sr * 2:
            break

        note, mode, conf, _ = _detect_key_librosa(y_seg, sr)
        segments.append(KeySegment(
            start=round(start, 3),
            end=round(end, 3),
            key=note,
            mode=mode,
            confidence=round(conf, 3),
        ))
        t += hop

    return segments


def _detect_modulations(segments: List[KeySegment]) -> List[dict]:
    """Find key changes between consecutive segments."""
    modulations = []
    for i in range(1, len(segments)):
        prev, curr = segments[i - 1], segments[i]
        if prev.key != curr.key or prev.mode != curr.mode:
            modulations.append({
                "time": curr.start,
                "from_key": f"{prev.key} {prev.mode}",
                "to_key": f"{curr.key} {curr.mode}",
                "confidence": round((prev.confidence + curr.confidence) / 2, 3),
            })
    return modulations


def _build_key_alternatives(root_idx: int, mode: str, base_confidence: float) -> List[dict]:
    """Generate parallel, relative, and neighbour key alternatives."""
    alts = []

    # Relative key
    if mode == "major":
        rel_root = (root_idx - 3) % 12
        rel_mode = "minor"
    else:
        rel_root = (root_idx + 3) % 12
        rel_mode = "major"

    alts.append({
        "key": _idx_to_note(rel_root),
        "mode": rel_mode,
        "label": "relative",
        "confidence": round(base_confidence * 0.9, 3),
    })

    # Parallel key
    par_mode = "minor" if mode == "major" else "major"
    alts.append({
        "key": _idx_to_note(root_idx),
        "mode": par_mode,
        "label": "parallel",
        "confidence": round(base_confidence * 0.75, 3),
    })

    # Dominant (V)
    dom_root = (root_idx + 7) % 12
    alts.append({
        "key": _idx_to_note(dom_root),
        "mode": mode,
        "label": "dominant",
        "confidence": round(base_confidence * 0.6, 3),
    })

    return alts


def detect_key(bundle, stems=None, force: bool = False) -> KeyResult:
    """
    Main key detection entry point.
    Uses Essentia on "other" stem when available, falls back to librosa.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "key_detector"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Key cache hit for %s", file_hash[:8])
            return KeyResult.model_validate(cached)

    y = bundle.y_mono
    sr = bundle.sr

    # Try Essentia on "other" stem first (harmonic content without drums)
    other_path = None
    if stems and stems.other.available and stems.other.path:
        other_path = stems.other.path

    note, mode, confidence, alternatives = _detect_key_essentia(y, sr, stem_path=other_path)

    # Segment-based key analysis for modulation detection
    segments = _segment_keys(y, sr, bundle.duration)
    modulations = _detect_modulations(segments)

    # Merge segment alternatives into global alternatives
    root_idx = _note_to_idx(note)
    global_alts = _build_key_alternatives(root_idx, mode, confidence)

    # Merge with detector alternatives (deduplicate)
    seen = {f"{note}_{mode}"}
    for alt in alternatives + global_alts:
        key_mode = f"{alt.get('key', '')}_{alt.get('mode', '')}"
        if key_mode not in seen:
            seen.add(key_mode)

    source = "essentia_other_stem" if other_path else "librosa"

    result = KeyResult(
        global_key=note,
        global_mode=mode,
        global_confidence=round(confidence, 3),
        segments=segments,
        modulations=modulations,
        alternatives=global_alts + alternatives,
        source=source,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info("Key=%s %s conf=%.2f src=%s mods=%d", note, mode, confidence, source, len(modulations))
    return result
