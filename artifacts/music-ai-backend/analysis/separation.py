"""
Stem separation using Demucs 4.0.1 (htdemucs model).
Separates: vocals / drums / bass / other.
Results cached by file_hash to avoid repeated GPU computation.
"""

from __future__ import annotations

import os
import logging
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from analysis.schemas import StemInfo, StemsResult
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

STEMS_DIR = os.environ.get("STEMS_DIR", "/tmp/musicai_stems")
DEMUCS_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")
STEM_NAMES = ["vocals", "drums", "bass", "other"]


def _stem_energy(y: np.ndarray) -> float:
    if y is None or len(y) == 0:
        return 0.0
    return float(np.sqrt(np.mean(y ** 2)))


def _stem_confidence(energy: float, total_energy: float) -> float:
    if total_energy < 1e-8:
        return 0.0
    return float(min(1.0, energy / (total_energy + 1e-8)))


def separate_stems(
    bundle,  # AudioBundle
    force: bool = False,
) -> StemsResult:
    """
    Run Demucs stem separation.
    Returns StemsResult with paths to separated stem WAV files.
    Caches results so subsequent calls are instant.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = f"stems_{DEMUCS_MODEL}"

    # Cache check
    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Stems cache hit for %s", file_hash[:8])
            return _deserialize_stems(cached)

    # Make output dir
    output_dir = Path(STEMS_DIR) / file_hash[:2] / file_hash
    output_dir.mkdir(parents=True, exist_ok=True)

    stems_data: Dict[str, Optional[str]] = {n: None for n in STEM_NAMES}

    try:
        stems_data = _run_demucs(bundle.file_path, output_dir)
        logger.info("Demucs separation complete for %s", file_hash[:8])
    except Exception as e:
        logger.error("Demucs failed: %s — using degraded mode", e)
        return _degraded_stems_result()

    # Compute energies
    stem_energies: Dict[str, float] = {}
    stem_arrays: Dict[str, Optional[np.ndarray]] = {}

    for name, path in stems_data.items():
        if path and os.path.exists(path):
            try:
                import soundfile as sf
                y, _ = sf.read(path)
                if y.ndim > 1:
                    y = y.mean(axis=1)
                stem_arrays[name] = y.astype(np.float32)
                stem_energies[name] = _stem_energy(y)
            except Exception:
                stem_arrays[name] = None
                stem_energies[name] = 0.0
        else:
            stem_arrays[name] = None
            stem_energies[name] = 0.0

    total_energy = sum(stem_energies.values()) + 1e-8
    separation_confidence = _compute_separation_confidence(stem_energies, total_energy)

    def make_stem_info(name: str) -> StemInfo:
        energy = stem_energies.get(name, 0.0)
        path = stems_data.get(name)
        return StemInfo(
            path=path,
            energy_ratio=float(energy / total_energy),
            confidence=_stem_confidence(energy, total_energy),
            available=bool(path and os.path.exists(path or "")),
        )

    result = StemsResult(
        vocals=make_stem_info("vocals"),
        drums=make_stem_info("drums"),
        bass=make_stem_info("bass"),
        other=make_stem_info("other"),
        separation_mode="demucs_htdemucs",
        separation_confidence=separation_confidence,
    )

    # Cache serialized result
    cache_set(file_hash, stage, _serialize_stems(result))
    return result


def _run_demucs(file_path: str, output_dir: Path) -> Dict[str, Optional[str]]:
    """Run Demucs CLI or Python API and return {stem_name: wav_path}."""
    import torch

    # Try Python API (faster, no subprocess overhead)
    try:
        return _run_demucs_api(file_path, output_dir)
    except Exception as api_err:
        logger.warning("Demucs Python API failed (%s), trying CLI", api_err)
        return _run_demucs_cli(file_path, output_dir)


def _run_demucs_api(file_path: str, output_dir: Path) -> Dict[str, Optional[str]]:
    """Use demucs.api for in-process separation."""
    import torch
    from demucs.api import Separator
    from demucs.audio import save_audio

    device = "cuda" if torch.cuda.is_available() else "cpu"
    separator = Separator(model=DEMUCS_MODEL, device=device, progress=False)

    _, separated = separator.separate_audio_file(file_path)

    stems_data: Dict[str, Optional[str]] = {}
    for stem_name, waveform in separated.items():
        out_path = output_dir / f"{stem_name}.wav"
        save_audio(waveform, str(out_path), samplerate=separator.samplerate)
        stems_data[stem_name] = str(out_path)

    return stems_data


def _run_demucs_cli(file_path: str, output_dir: Path) -> Dict[str, Optional[str]]:
    """Fallback: subprocess demucs CLI."""
    import subprocess

    cmd = [
        "python3", "-m", "demucs",
        "--name", DEMUCS_MODEL,
        "--out", str(output_dir.parent.parent),
        "--filename", "{track}/{stem}.{ext}",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Demucs CLI failed: {result.stderr[:500]}")

    track_name = Path(file_path).stem
    stems_data: Dict[str, Optional[str]] = {}
    for stem_name in STEM_NAMES:
        p = output_dir.parent.parent / DEMUCS_MODEL / track_name / f"{stem_name}.wav"
        stems_data[stem_name] = str(p) if p.exists() else None

    return stems_data


def _compute_separation_confidence(energies: Dict[str, float], total: float) -> float:
    """Confidence based on how evenly distributed energy is across stems."""
    if total < 1e-8:
        return 0.0
    ratios = [e / total for e in energies.values()]
    # High confidence if no single stem dominates (good separation)
    max_ratio = max(ratios)
    if max_ratio > 0.9:
        return 0.3  # One stem dominates — poor separation
    non_zero = sum(1 for r in ratios if r > 0.05)
    return float(min(1.0, 0.5 + non_zero * 0.1))


def _serialize_stems(result: StemsResult) -> dict:
    return result.model_dump()


def _deserialize_stems(data: dict) -> StemsResult:
    return StemsResult.model_validate(data)


def _degraded_stems_result() -> StemsResult:
    """Return empty StemsResult when separation fails completely."""
    return StemsResult(
        separation_mode="degraded",
        separation_confidence=0.0,
    )
