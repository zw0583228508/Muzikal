"""
Ensemble / multi-source voting for key detection.

When multiple analyzers are available (Essentia + librosa K-S),
combines their outputs using weighted voting.
Currently applied to key detection — most benefit from ensemble.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from analysis.schemas import KeyResult, KeySegment

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_SOURCE_WEIGHTS: Dict[str, float] = {
    "essentia_other_stem": 1.00,
    "essentia_fullmix":    0.90,
    "librosa":             0.70,
    "librosa_cqt":         0.70,
    "pyin_librosa":        0.65,
    "torchcrepe_vocals":   0.95,
    "madmom_drums":        0.95,
    "madmom_fullmix":      0.85,
    "librosa_fullmix":     0.70,
}


def _source_weight(source: str) -> float:
    for k, w in _SOURCE_WEIGHTS.items():
        if k in source:
            return w
    return 0.7


def ensemble_key(candidates: List[KeyResult]) -> KeyResult:
    """
    Combine multiple KeyResult candidates via weighted voting.
    Returns the highest-voted key/mode combination.
    """
    if not candidates:
        raise ValueError("No key candidates to ensemble")
    if len(candidates) == 1:
        return candidates[0]

    # Weighted vote over (key, mode) pairs
    votes: Dict[Tuple[str, str], float] = {}
    for result in candidates:
        weight = _source_weight(result.source) * result.global_confidence
        pair = (result.global_key, result.global_mode)
        votes[pair] = votes.get(pair, 0.0) + weight

    # Pick winner
    winner = max(votes, key=lambda k: votes[k])
    total_weight = sum(votes.values())
    winning_conf = votes[winner] / total_weight if total_weight > 0 else 0.5

    # Aggregate alternatives from all candidates
    seen = {f"{winner[0]}_{winner[1]}"}
    alts = []
    for result in candidates:
        for alt in result.alternatives:
            key_mode = f"{alt.get('key', '')}_{alt.get('mode', '')}"
            if key_mode not in seen:
                seen.add(key_mode)
                alts.append(alt)

    # Aggregate segments from best candidate
    best = max(candidates, key=lambda r: _source_weight(r.source) * r.global_confidence)

    return KeyResult(
        global_key=winner[0],
        global_mode=winner[1],
        global_confidence=round(float(winning_conf), 3),
        segments=best.segments,
        modulations=best.modulations,
        alternatives=alts[:8],
        source="ensemble_" + "+".join(r.source.split("_")[0] for r in candidates),
    )
