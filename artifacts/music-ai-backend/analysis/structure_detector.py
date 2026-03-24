"""
Musical structure / section detection v3.

Multi-signal boundary detection pipeline:
  Signal 1: SSM (Self-Similarity Matrix) + Checkerboard novelty
            — captures large-scale repeated structure
  Signal 2: Spectral flux (onset strength envelope)
            — captures note/transient density changes
  Signal 3: Harmonic change (Tonal Centroid Features, Harte 2006)
            — captures chord change density and key-region shifts
  Signal 4: RMS energy change
            — captures dynamic level shifts (verse→chorus energy jumps)

All four signals are peak-normalized and fused with confidence weights.
The fused novelty curve then feeds boundary peak-picking.

Labeling is still heuristic (position-based), but boundary detection
is now substantially more robust due to multi-signal agreement.

v3 improvements over v2:
  - Harmonic change (TCF) as independent boundary signal
  - Spectral flux in novelty fusion
  - Weighted fusion instead of SSM-only
  - Per-signal confidence output
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import librosa
import scipy.ndimage
import scipy.spatial.distance

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


def _compute_spectral_flux(y: np.ndarray, sr: int, hop_length: int = 4096) -> np.ndarray:
    """
    Compute spectral flux novelty curve — captures timbral changes between frames.
    High flux = sudden spectral change = potential boundary.
    """
    stft = np.abs(librosa.stft(y, hop_length=hop_length))
    flux = np.concatenate([[0], np.sum(np.diff(stft, axis=1) ** 2, axis=0)])
    # Normalize
    if flux.max() > 0:
        flux = flux / flux.max()
    # Smooth
    flux = scipy.ndimage.gaussian_filter1d(flux, sigma=2)
    return flux.astype(np.float32)


def _compute_energy_change(y: np.ndarray, sr: int, hop_length: int = 4096) -> np.ndarray:
    """
    Compute RMS energy change rate — captures volume transitions.
    Uses absolute difference of smoothed RMS envelope.
    """
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    # Smooth first to avoid frame-level noise
    rms_smooth = scipy.ndimage.gaussian_filter1d(rms.astype(float), sigma=4)
    change = np.abs(np.diff(rms_smooth, prepend=rms_smooth[0]))
    if change.max() > 0:
        change = change / change.max()
    change = scipy.ndimage.gaussian_filter1d(change, sigma=3)
    return change.astype(np.float32)


def _compute_harmonic_change(y: np.ndarray, sr: int, hop_length: int = 4096) -> np.ndarray:
    """
    Compute harmonic change curve using Tonal Centroid Features (Harte 2006).
    High values indicate likely chord boundary zones.
    Returns frame-level curve in [0, 1].
    """
    try:
        from analysis.tonal_features import compute_harmonic_change_curve
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length, bins_per_octave=36)
        hcdf = compute_harmonic_change_curve(chroma)   # (T,)
        # Smooth to reduce spurious peaks
        hcdf = scipy.ndimage.gaussian_filter1d(hcdf, sigma=2)
        return hcdf.astype(np.float32)
    except Exception as e:
        logger.debug("Harmonic change curve failed: %s", e)
        return np.zeros(1, dtype=np.float32)


def _resize_to(arr: np.ndarray, target_len: int) -> np.ndarray:
    """Resize a 1-D array to target_len via linear interpolation."""
    if len(arr) == target_len:
        return arr
    from scipy.interpolate import interp1d
    x_old = np.linspace(0, 1, len(arr))
    x_new = np.linspace(0, 1, target_len)
    f = interp1d(x_old, arr, kind="linear", fill_value="extrapolate")
    return f(x_new).astype(np.float32)


def _compute_multisignal_novelty(
    y: np.ndarray,
    sr: int,
    hop_length: int = 4096,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """
    Fuse four boundary-detection signals into a single novelty curve.

    Signals:
      ssm_novelty   (w=0.40): Self-similarity matrix checkerboard
      harmonic_change (w=0.30): TCF-based harmonic change rate
      spectral_flux (w=0.20): Frame-to-frame spectral change
      energy_change  (w=0.10): RMS energy change rate

    Returns:
        (fused_novelty, frame_times, individual_signals)
    """
    if weights is None:
        weights = {
            "ssm":      0.40,
            "harmonic": 0.30,
            "flux":     0.20,
            "energy":   0.10,
        }

    ssm = _compute_ssm(y, sr, hop_length=hop_length)
    T = ssm.shape[0]
    times = librosa.frames_to_time(np.arange(T), sr=sr, hop_length=hop_length)

    ssm_novelty     = _novelty_from_ssm(ssm)
    spectral_flux   = _compute_spectral_flux(y, sr, hop_length=hop_length)
    energy_change   = _compute_energy_change(y, sr, hop_length=hop_length)
    harmonic_change = _compute_harmonic_change(y, sr, hop_length=hop_length)

    # Resize all signals to T frames
    spectral_flux   = _resize_to(spectral_flux, T)
    energy_change   = _resize_to(energy_change, T)
    harmonic_change = _resize_to(harmonic_change, T) if harmonic_change.shape[0] > 1 else np.zeros(T)

    # Weighted sum
    fused = (
        weights["ssm"]      * ssm_novelty
        + weights["harmonic"] * harmonic_change
        + weights["flux"]     * spectral_flux
        + weights["energy"]   * energy_change
    )

    # Re-normalize
    if fused.max() > 0:
        fused = fused / fused.max()

    signals = {
        "ssm_novelty":     ssm_novelty,
        "harmonic_change": harmonic_change,
        "spectral_flux":   spectral_flux,
        "energy_change":   energy_change,
        "fused":           fused,
    }

    return fused, times, signals


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


def _compute_energy_profile(
    y: np.ndarray,
    sr: int,
    boundaries: List[float],
) -> List[Dict[str, float]]:
    """
    Compute RMS energy, onset density, and spectral centroid for each section.

    Returns list of dicts with keys: energy, density, spectral_centroid.
    Length = len(boundaries) - 1 sections.
    """
    profiles: List[Dict[str, float]] = []
    hop = 512

    # Pre-compute global features at hop level
    rms_global = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_max = float(rms_global.max()) + 1e-8

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    spec_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]

    for i in range(len(boundaries) - 1):
        t_start = boundaries[i]
        t_end = boundaries[i + 1]

        f_start = int(t_start * sr / hop)
        f_end   = min(int(t_end * sr / hop), len(rms_global))

        if f_end <= f_start:
            profiles.append({"energy": 0.0, "density": 0.0, "spectral_centroid": 0.0})
            continue

        section_rms = rms_global[f_start:f_end]
        section_ons = onset_env[f_start:f_end]
        section_sc  = spec_centroid[f_start:f_end]

        energy = round(float(section_rms.mean()) / rms_max, 4)

        # Onset density: peaks per second
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(section_ons, height=section_ons.mean() * 0.8)
        section_dur = max(t_end - t_start, 0.01)
        density = round(float(len(peaks)) / section_dur, 3)

        sc_mean = round(float(section_sc.mean()), 1)

        profiles.append({
            "energy":            energy,
            "density":           density,
            "spectral_centroid": sc_mean,
        })

    return profiles


def _group_similar_sections(
    sections: List[Section],
    ssm: np.ndarray,
    times: np.ndarray,
) -> List[Section]:
    """
    Cluster sections into similarity groups using their SSM fingerprint.

    Each section gets a `group_id`; sections that sound alike share an ID.
    Uses simple greedy agglomerative clustering with cosine distance.
    """
    if len(sections) < 2:
        for i, s in enumerate(sections):
            sections[i] = s.model_copy(update={"group_id": 0})
        return sections

    dt = float(times[1] - times[0]) if len(times) > 1 else 1.0

    def section_ssm_vector(s: Section) -> np.ndarray:
        f_start = int(s.start / dt)
        f_end   = int(s.end   / dt)
        f_end   = min(f_end, ssm.shape[0])
        if f_end <= f_start:
            return np.zeros(ssm.shape[0])
        row_slice = ssm[f_start:f_end, :].mean(axis=0)
        return row_slice / (np.linalg.norm(row_slice) + 1e-8)

    fingerprints = [section_ssm_vector(s) for s in sections]

    # Greedy grouping: two sections merge if cosine similarity > threshold
    THRESHOLD = 0.72
    group_ids = [-1] * len(sections)
    next_group = 0

    for i, fp_i in enumerate(fingerprints):
        if group_ids[i] >= 0:
            continue
        group_ids[i] = next_group
        for j in range(i + 1, len(sections)):
            if group_ids[j] >= 0:
                continue
            sim = float(np.dot(fp_i, fingerprints[j]))
            if sim >= THRESHOLD:
                group_ids[j] = next_group
        next_group += 1

    # Apply group IDs
    updated: List[Section] = []
    for s, gid in zip(sections, group_ids):
        updated.append(s.model_copy(update={"group_id": gid}))
    return updated


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

    # Multi-signal novelty fusion
    fused_novelty, times, signals = _compute_multisignal_novelty(y, sr, hop_length=hop_length)
    ssm = _compute_ssm(y, sr, hop_length=hop_length)   # still needed for repetition/grouping

    logger.info(
        "[structure] Multi-signal novelty: ssm=%.3f, harmonic=%.3f, flux=%.3f, energy=%.3f",
        signals["ssm_novelty"].max(),
        signals["harmonic_change"].max(),
        signals["spectral_flux"].max(),
        signals["energy_change"].max(),
    )

    # Boundary detection on fused novelty
    boundaries = _pick_boundaries(fused_novelty, times, min_gap_sec=max(4.0, duration / 20))

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

    # Energy / density / spectral-centroid profile per section
    energy_profiles = _compute_energy_profile(y, sr, boundaries)
    for i, ep in enumerate(energy_profiles):
        if i < len(sections):
            sections[i] = sections[i].model_copy(update={
                "energy":            ep["energy"],
                "density":           ep["density"],
                "spectral_centroid": ep["spectral_centroid"],
            })

    # Similarity grouping
    sections = _group_similar_sections(sections, ssm, times)

    num_groups = len(set(s.group_id for s in sections if s.group_id is not None))
    global_confidence = round(float(np.mean([s.confidence for s in sections])), 3) if sections else 0.0

    result = StructureResult(
        sections=sections,
        num_sections=len(sections),
        confidence=global_confidence,
        source="multisignal_v3:ssm+harmonic+flux+energy",
        num_groups=num_groups,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info(
        "Structure: %d sections, %d groups, conf=%.2f",
        len(sections), num_groups, global_confidence,
    )
    return result
