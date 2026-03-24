"""
Tonal Centroid Features (TCF) — Harte et al. 2006.

Maps 12-dimensional chroma vectors to a 6-dimensional tonal centroid space
using DFT projections. TCF captures harmonic distance and tension more
compactly than raw chroma, and is used as an additional feature by the
HSMM chord recognizer.

Reference:
  Harte, C., Sandler, M. & Gasser, M. (2006).
  "Detecting Harmonic Change in Musical Audio."
  Proceedings of the 1st ACM Workshop on Audio and Music Computing Multimedia.

Usage:
    from analysis.tonal_features import chroma_to_tcf, extract_tcf
    tcf = chroma_to_tcf(hpcp_vector)   # (12,) → (6,)
    tcf_matrix = extract_tcf(chroma)   # (12, T) → (6, T)
"""

from __future__ import annotations

import numpy as np


# DFT projection vectors for the 6 components (Harte 2006, Table 1)
# Each row is the real (cos) and imaginary (sin) component of a DFT bin
# applied across the 12 semitones.
# r_l and phi_l are the radius and phase offsets for bin l.

_r = np.array([1.0, 1.0, 0.5, 0.5, 0.5, 0.5], dtype=float)

# Multiplier for semitone index k in DFT bin l
_M = np.array([2 * np.pi / 12, 2 * np.pi / 12 / 7, 3 * 2 * np.pi / 12,
               2 * 2 * np.pi / 12, 1 * 2 * np.pi / 12, 2 * np.pi / 12 * 2])

# Precompute the 6×12 projection matrix
_k = np.arange(12, dtype=float)  # semitone indices 0…11
_COS = np.cos(np.outer(_M, _k))   # (6, 12)
_SIN = np.sin(np.outer(_M, _k))   # (6, 12)

# Scale each component by its radius
_COS *= _r[:, None]
_SIN *= _r[:, None]

# Full projection: concatenate real (cos) and imaginary (sin) → 12 features
# But per paper, the centroid is 6D (real part + imaginary part together)
# We represent as 6 complex numbers → 12-D real when needed.
# Here we keep 6D using magnitude of each complex component.
_PROJ_REAL = _COS   # (6, 12)
_PROJ_IMAG = _SIN   # (6, 12)


def chroma_to_tcf(chroma_frame: np.ndarray) -> np.ndarray:
    """
    Convert a 12-dimensional chroma frame to a 6-dim tonal centroid.

    Args:
        chroma_frame: shape (12,) — HPCP or CQT chroma, L1 or L2 normalized

    Returns:
        tcf: shape (6,) — tonal centroid features in [-1, 1]
    """
    c = chroma_frame.astype(float)
    norm = np.sum(c) + 1e-8
    c = c / norm

    real_part = _PROJ_REAL @ c   # (6,)
    imag_part = _PROJ_IMAG @ c   # (6,)

    # Return magnitude (captures tonal stability independent of phase)
    return np.sqrt(real_part**2 + imag_part**2)


def chroma_to_tcf_full(chroma_frame: np.ndarray) -> np.ndarray:
    """
    Returns 12-dim full TCF (real + imaginary parts interleaved).
    Useful when phase information is important.
    """
    c = chroma_frame.astype(float)
    norm = np.sum(c) + 1e-8
    c = c / norm

    real_part = _PROJ_REAL @ c
    imag_part = _PROJ_IMAG @ c

    return np.concatenate([real_part, imag_part])


def extract_tcf(chroma: np.ndarray) -> np.ndarray:
    """
    Compute TCF for each frame in a chroma matrix.

    Args:
        chroma: shape (12, T)

    Returns:
        tcf: shape (6, T)
    """
    T = chroma.shape[1]
    tcf = np.zeros((6, T), dtype=float)
    for t in range(T):
        tcf[:, t] = chroma_to_tcf(chroma[:, t])
    return tcf


def tonal_distance(tcf_a: np.ndarray, tcf_b: np.ndarray) -> float:
    """
    Compute the Euclidean tonal distance between two TCF vectors.
    Lower = more harmonically similar.
    """
    return float(np.linalg.norm(tcf_a - tcf_b))


def compute_harmonic_change_curve(chroma: np.ndarray) -> np.ndarray:
    """
    Compute frame-by-frame harmonic change strength using TCF differences.
    High values indicate likely chord boundaries.

    Args:
        chroma: shape (12, T)

    Returns:
        change_curve: shape (T,) — harmonic change strength [0, 1]
    """
    tcf = extract_tcf(chroma)   # (6, T)
    T = tcf.shape[1]

    change = np.zeros(T)
    for t in range(1, T):
        change[t] = tonal_distance(tcf[:, t], tcf[:, t - 1])

    # Normalize to [0, 1]
    if change.max() > 0:
        change /= change.max()

    return change
