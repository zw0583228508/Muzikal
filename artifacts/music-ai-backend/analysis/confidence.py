"""
Global confidence calibration and scoring.

Aggregates per-stage confidences into a single global_confidence score
and generates per-stage quality labels.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

from analysis.schemas import (
    AnalysisResult, AnalysisWarning, TempoResult, KeyResult,
    ChordsResult, MelodyResult, StructureResult, StemsResult
)

logger = logging.getLogger(__name__)


# ─── Weight map (how much each stage contributes to global confidence) ─────────
_STAGE_WEIGHTS: Dict[str, float] = {
    "stems":     0.10,
    "tempo":     0.25,
    "key":       0.20,
    "chords":    0.25,
    "melody":    0.15,
    "structure": 0.05,
}


def _label_confidence(value: float) -> str:
    if value >= 0.80:
        return "high"
    elif value >= 0.55:
        return "medium"
    else:
        return "low"


def _tempo_confidence(tempo: Optional[TempoResult]) -> float:
    if tempo is None:
        return 0.0
    # Penalize if source is basic librosa
    base = tempo.confidence
    if "madmom" in tempo.source:
        return min(1.0, base * 1.1)
    return base * 0.9


def _key_confidence(key: Optional[KeyResult]) -> float:
    if key is None:
        return 0.0
    base = key.global_confidence
    if "essentia" in key.source:
        return min(1.0, base * 1.05)
    return base


def _chords_confidence(chords: Optional[ChordsResult]) -> float:
    if chords is None or not chords.timeline:
        return 0.0
    return chords.global_confidence


def _melody_confidence(melody: Optional[MelodyResult]) -> float:
    if melody is None:
        return 0.0
    base = melody.global_confidence
    if "torchcrepe" in melody.source:
        return min(1.0, base * 1.1)
    return base


def _structure_confidence(structure: Optional[StructureResult]) -> float:
    if structure is None:
        return 0.0
    return structure.confidence


def _stems_confidence(stems: Optional[StemsResult]) -> float:
    if stems is None:
        return 0.0
    return stems.separation_confidence


def compute_global_confidence(result: AnalysisResult) -> float:
    """Weighted average of per-stage confidences."""
    stage_scores = {
        "stems":     _stems_confidence(result.stems),
        "tempo":     _tempo_confidence(result.tempo),
        "key":       _key_confidence(result.key),
        "chords":    _chords_confidence(result.chords),
        "melody":    _melody_confidence(result.melody),
        "structure": _structure_confidence(result.structure),
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for stage, score in stage_scores.items():
        weight = _STAGE_WEIGHTS.get(stage, 0.1)
        if score > 0:  # Only count stages that ran
            weighted_sum += score * weight
            total_weight += weight

    if total_weight < 0.01:
        return 0.0
    return round(float(weighted_sum / total_weight), 3)


def generate_warnings(result: AnalysisResult) -> List[AnalysisWarning]:
    """Generate quality warnings for low-confidence stages."""
    warnings: List[AnalysisWarning] = []

    if result.tempo and result.tempo.confidence < 0.5:
        warnings.append(AnalysisWarning(
            code="LOW_TEMPO_CONFIDENCE",
            message=f"Tempo confidence is low ({result.tempo.confidence:.2f}). BPM may be inaccurate.",
            severity="warning",
        ))

    if result.key and result.key.global_confidence < 0.5:
        warnings.append(AnalysisWarning(
            code="LOW_KEY_CONFIDENCE",
            message=f"Key confidence is low ({result.key.global_confidence:.2f}). Key may be ambiguous.",
            severity="warning",
        ))

    if result.chords and result.chords.global_confidence < 0.4:
        warnings.append(AnalysisWarning(
            code="LOW_CHORD_CONFIDENCE",
            message=f"Chord confidence is low ({result.chords.global_confidence:.2f}). Chord detection may be unreliable.",
            severity="warning",
        ))

    if result.melody and result.melody.voiced_fraction < 0.1:
        warnings.append(AnalysisWarning(
            code="LOW_VOCAL_PRESENCE",
            message="Very little vocal/melodic content detected. Song may be instrumental.",
            severity="info",
        ))

    if result.stems and result.stems.separation_mode == "degraded":
        warnings.append(AnalysisWarning(
            code="STEM_SEPARATION_FAILED",
            message="Stem separation failed. Analysis performed on full mix (lower accuracy).",
            severity="warning",
        ))

    if result.key and result.key.modulations:
        warnings.append(AnalysisWarning(
            code="KEY_MODULATIONS_DETECTED",
            message=f"{len(result.key.modulations)} key modulation(s) detected.",
            severity="info",
        ))

    return warnings


def annotate_confidence(result: AnalysisResult) -> AnalysisResult:
    """Compute global confidence and add warnings in-place."""
    global_conf = compute_global_confidence(result)
    warnings = generate_warnings(result)

    return AnalysisResult(
        audio_meta=result.audio_meta,
        stems=result.stems,
        tempo=result.tempo,
        key=result.key,
        chords=result.chords,
        melody=result.melody,
        structure=result.structure,
        global_confidence=global_conf,
        mode=result.mode,
        pipeline_version=result.pipeline_version,
        warnings=warnings,
    )
