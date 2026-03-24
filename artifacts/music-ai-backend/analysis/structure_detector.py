"""
Musical structure / section detection.

Uses Self-Similarity Matrix (SSM) + spectral novelty curve.
Labels sections heuristically (intro, verse, chorus, bridge, outro).
Detects repeated sections for arrangement insights.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import librosa
import scipy.ndimage

from analysis.schemas import Section, StructureResult
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Section label vocabulary (in typical appearance order)
_SECTION_LABELS = ["intro", "verse", "pre-chorus", "chorus", "bridge", "outro", "instrumental"]
_DEFAULT_LABEL_SEQUENCE = ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"]


def _compute_ssm(y: np.ndarray, sr: int, hop_length: int = 4096) -> np.ndarray:
    """
    Build a Self-Similarity Matrix from MFCC + chroma features.
    Returns normalized SSM of shape (n_frames, n_frames).
    """
    # Concatenated feature vector: MFCC + chroma
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=hop_length)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length, bins_per_octave=36)

    # Stack and normalize each row
    features = np.vstack([mfcc, chroma])
    norms = np.linalg.norm(features, axis=0, keepdims=True) + 1e-8
    features = features / norms

    # Cosine similarity matrix
    ssm = features.T @ features
    ssm = np.clip(ssm, 0, 1)
    return ssm.astype(np.float32)


def _novelty_from_ssm(ssm: np.ndarray, kernel_size: int = 16) -> np.ndarray:
    """
    Compute spectral novelty from SSM using a checkerboard kernel.
    High novelty = structural boundary.
    """
    n = ssm.shape[0]
    half = kernel_size // 2

    # Checkerboard kernel
    kernel = np.zeros((kernel_size, kernel_size))
    kernel[:half, :half] = 1
    kernel[half:, half:] = 1
    kernel[:half, half:] = -1
    kernel[half:, :half] = -1

    # Convolve SSM with kernel
    novelty = np.zeros(n)
    for i in range(half, n - half):
        patch = ssm[i - half:i + half, i - half:i + half]
        if patch.shape == (kernel_size, kernel_size):
            novelty[i] = float(np.sum(patch * kernel))

    # Normalize to [0, 1]
    novelty -= novelty.min()
    if novelty.max() > 0:
        novelty /= novelty.max()

    # Smooth
    novelty = scipy.ndimage.gaussian_filter1d(novelty, sigma=2)
    return novelty


def _pick_boundaries(novelty: np.ndarray, times: np.ndarray, min_gap_sec: float = 8.0) -> List[float]:
    """
    Pick structural boundary times from novelty peaks.
    Enforces minimum gap between boundaries.
    """
    from scipy.signal import find_peaks

    min_gap_frames = int(min_gap_sec / (times[1] - times[0])) if len(times) > 1 else 4
    peaks, props = find_peaks(
        novelty, height=0.3, distance=min_gap_frames, prominence=0.15
    )

    boundary_times = [float(times[p]) for p in peaks if p < len(times)]

    # Always include start and end
    boundaries = sorted(set([0.0] + boundary_times + [float(times[-1])]))
    return boundaries


def _detect_repetitions(
    sections: List[Section],
    ssm: np.ndarray,
    times: np.ndarray,
) -> List[Section]:
    """
    Use SSM to detect repeated sections.
    Compares each section's mean chroma profile against all others.
    """
    if len(sections) < 2:
        return sections

    def section_frames(s: Section) -> Tuple[int, int]:
        if len(times) < 2:
            return 0, 0
        dt = float(times[1] - times[0])
        return int(s.start / dt), int(s.end / dt)

    for i, si in enumerate(sections):
        fi_start, fi_end = section_frames(si)
        if fi_end <= fi_start or fi_end > ssm.shape[0]:
            continue
        pi = ssm[fi_start:fi_end, fi_start:fi_end].mean()

        for j, sj in enumerate(sections):
            if i == j:
                continue
            fj_start, fj_end = section_frames(sj)
            if fj_end <= fj_start or fj_end > ssm.shape[0]:
                continue

            cross_size = (min(fi_end, fj_end) - max(fi_start, fj_start))
            if cross_size < 1:
                cross_sim = 0.0
            else:
                cross_sim = float(ssm[fi_start:fi_end, fj_start:fj_end].mean()) if (
                    fi_end <= ssm.shape[0] and fj_end <= ssm.shape[1]
                ) else 0.0

            if cross_sim > 0.75 and not si.repeated:
                sections[i] = Section(
                    label=si.label,
                    start=si.start,
                    end=si.end,
                    duration=si.duration,
                    confidence=si.confidence,
                    repeated=True,
                    repeat_of=sj.label,
                )
                break

    return sections


def _assign_labels(n_sections: int) -> List[str]:
    """Assign heuristic section labels based on count and position."""
    if n_sections <= 0:
        return []
    if n_sections == 1:
        return ["verse"]
    if n_sections == 2:
        return ["intro", "outro"]

    labels = []
    sequence = _DEFAULT_LABEL_SEQUENCE

    # Map sequence to n_sections by scaling
    scale = n_sections / len(sequence)
    assigned_indices = set()

    for i in range(n_sections):
        idx = min(int(i / scale), len(sequence) - 1)
        if idx in assigned_indices:
            # Find next unique
            idx = min(idx + 1, len(sequence) - 1)
        labels.append(sequence[idx])
        assigned_indices.add(idx)

    # Handle intro/outro specifically
    if n_sections >= 3:
        labels[0] = "intro"
        labels[-1] = "outro"

    return labels


def detect_structure(bundle, force: bool = False) -> StructureResult:
    """
    Main structure detection entry point.
    Uses SSM + novelty curve on the full mono mix.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "structure_detector"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Structure cache hit for %s", file_hash[:8])
            return StructureResult.model_validate(cached)

    y = bundle.y_mono
    sr = bundle.sr
    duration = bundle.duration

    hop_length = 4096

    # SSM
    ssm = _compute_ssm(y, sr, hop_length=hop_length)
    times = librosa.frames_to_time(np.arange(ssm.shape[0]), sr=sr, hop_length=hop_length)

    # Novelty curve
    novelty = _novelty_from_ssm(ssm)

    # Boundary detection
    boundaries = _pick_boundaries(novelty, times, min_gap_sec=max(4.0, duration / 20))

    # Ensure last boundary is at end
    if boundaries[-1] < duration - 1:
        boundaries.append(duration)

    n_sections = len(boundaries) - 1
    if n_sections < 1:
        boundaries = [0.0, duration]
        n_sections = 1

    # Assign labels
    labels = _assign_labels(n_sections)

    # Build sections
    sections: List[Section] = []
    for i, label in enumerate(labels):
        start = round(float(boundaries[i]), 3)
        end = round(float(boundaries[i + 1]) if i + 1 < len(boundaries) else duration, 3)
        dur = round(end - start, 3)

        # Confidence from novelty at boundaries
        boundary_frame = int(boundaries[i] / (times[1] - times[0])) if len(times) > 1 else 0
        boundary_frame = min(boundary_frame, len(novelty) - 1)
        conf = round(float(novelty[boundary_frame]) * 0.8 + 0.2, 3)

        sections.append(Section(
            label=label,
            start=start,
            end=end,
            duration=dur,
            confidence=conf,
        ))

    # Detect repetitions using SSM
    sections = _detect_repetitions(sections, ssm, times)

    global_confidence = round(float(np.mean([s.confidence for s in sections])), 3) if sections else 0.0

    result = StructureResult(
        sections=sections,
        num_sections=len(sections),
        confidence=global_confidence,
        source="ssm_novelty",
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info("Structure: %d sections, conf=%.2f", len(sections), global_confidence)
    return result
