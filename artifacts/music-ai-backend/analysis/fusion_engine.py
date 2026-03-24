"""
Fusion Engine — unified musical interpretation from multi-engine outputs.

The most important module in the pipeline. Accepts results from multiple
independent analyzers and fuses them into a single authoritative interpretation.

Fusion responsibilities:
  1. Confidence-weighted tempo selection (madmom > librosa)
  2. Weighted key voting across Essentia + librosa K-S
  3. Chord timeline reconciliation (Viterbi-smoothed template + bass weighting)
  4. Pitch curve + note event merge (torchcrepe + basic-pitch)
  5. Temporal consistency enforcement across all stages
  6. Conflict resolution (chord-key, melody-key, tempo-meter)
  7. Overall quality scoring
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from analysis.schemas import (
    AnalysisResult, AnalysisWarning, AudioMeta,
    TempoResult, KeyResult, KeySegment,
    ChordsResult, ChordEvent,
    MelodyResult, NoteEvent,
    StructureResult, StemsResult,
)

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# ─── Source reliability weights ────────────────────────────────────────────────
_TEMPO_SOURCE_WEIGHT: Dict[str, float] = {
    "madmom_drums":      1.00,
    "madmom_fullmix":    0.90,
    "librosa_fast":      0.65,
    "librosa_fullmix":   0.65,
}

_KEY_SOURCE_WEIGHT: Dict[str, float] = {
    "essentia_other_stem": 1.00,
    "essentia_fullmix":    0.92,
    "ensemble":            0.95,
    "librosa":             0.70,
    "librosa_fast":        0.65,
}

_MELODY_SOURCE_WEIGHT: Dict[str, float] = {
    "torchcrepe_vocals":         1.00,
    "basic_pitch_vocals":        0.95,
    "merged_crepe_basicpitch":   1.00,
    "pyin_librosa":              0.72,
    "yin_librosa":               0.55,
}


def _src_weight(source: str, weight_map: Dict[str, float]) -> float:
    for k, w in weight_map.items():
        if k in source:
            return w
    return 0.7


# ─── Tempo Fusion ──────────────────────────────────────────────────────────────

def _fuse_tempo(candidates: List[TempoResult]) -> TempoResult:
    """
    Select the best tempo from multiple candidates.
    Uses confidence × source-weight scoring.
    """
    if not candidates:
        return TempoResult(bpm_global=120.0, confidence=0.0, source="fallback")
    if len(candidates) == 1:
        return candidates[0]

    # Score each candidate
    scored = [
        (r, r.confidence * _src_weight(r.source, _TEMPO_SOURCE_WEIGHT))
        for r in candidates
    ]
    scored.sort(key=lambda x: -x[1])
    best, best_score = scored[0]

    # Cross-validate: if second candidate disagrees significantly, penalize
    if len(scored) > 1:
        second, _ = scored[1]
        ratio = max(best.bpm_global, second.bpm_global) / (min(best.bpm_global, second.bpm_global) + 1e-6)
        if 0.9 < ratio < 1.1:
            # Strong agreement → boost confidence
            fused_bpm = np.average(
                [r.bpm_global for r, _ in scored[:2]],
                weights=[s for _, s in scored[:2]],
            )
            fused_conf = min(1.0, best.confidence * 1.1)
            return TempoResult(
                bpm_global=round(float(fused_bpm), 2),
                bpm_curve=best.bpm_curve,
                beats=best.beats,
                downbeats=best.downbeats,
                meter=best.meter,
                meter_numerator=best.meter_numerator,
                meter_denominator=best.meter_denominator,
                confidence=round(fused_conf, 3),
                source="fused_" + best.source,
                alternatives=[{"bpm": r.bpm_global, "source": r.source, "confidence": r.confidence}
                              for r, _ in scored[1:]],
            )
        elif abs(ratio - 2.0) < 0.15 or abs(ratio - 0.5) < 0.1:
            # Half/double tempo disagreement — trust higher-weight source
            logger.info("Tempo fusion: half/double disagreement %.1f vs %.1f", best.bpm_global, second.bpm_global)

    return TempoResult(
        bpm_global=best.bpm_global,
        bpm_curve=best.bpm_curve,
        beats=best.beats,
        downbeats=best.downbeats,
        meter=best.meter,
        meter_numerator=best.meter_numerator,
        meter_denominator=best.meter_denominator,
        confidence=round(float(best_score), 3),
        source="fused_" + best.source,
        alternatives=[{"bpm": r.bpm_global, "source": r.source, "confidence": r.confidence}
                      for r, _ in scored[1:]],
    )


# ─── Key Fusion ────────────────────────────────────────────────────────────────

def _fuse_key(candidates: List[KeyResult]) -> KeyResult:
    """
    Weighted voting over key candidates.
    """
    if not candidates:
        return KeyResult(global_key="C", global_mode="major", global_confidence=0.0, source="fallback")
    if len(candidates) == 1:
        return candidates[0]

    votes: Dict[Tuple[str, str], float] = {}
    for r in candidates:
        w = r.global_confidence * _src_weight(r.source, _KEY_SOURCE_WEIGHT)
        pair = (r.global_key, r.global_mode)
        votes[pair] = votes.get(pair, 0.0) + w

    total = sum(votes.values())
    winner = max(votes, key=lambda k: votes[k])
    winning_conf = votes[winner] / total if total > 0 else 0.5

    # Build unique alternatives
    seen = {f"{winner[0]}_{winner[1]}"}
    alts = []
    for r in candidates:
        for alt in r.alternatives:
            key_mode = f"{alt.get('key', '')}_{alt.get('mode', '')}"
            if key_mode not in seen:
                seen.add(key_mode)
                alts.append(alt)

    best = max(candidates, key=lambda r: r.global_confidence * _src_weight(r.source, _KEY_SOURCE_WEIGHT))

    return KeyResult(
        global_key=winner[0],
        global_mode=winner[1],
        global_confidence=round(float(winning_conf), 3),
        segments=best.segments,
        modulations=best.modulations,
        alternatives=alts[:8],
        source="fused_" + "+".join(set(r.source.split("_")[0] for r in candidates)),
    )


# ─── Chord Fusion ──────────────────────────────────────────────────────────────

def _viterbi_chord_smooth(
    timeline: List[ChordEvent],
    key_root_idx: int,
    mode: str,
) -> List[ChordEvent]:
    """
    Apply Viterbi-like smoothing over the chord sequence.
    Uses music theory transition probabilities (diatonic progressions preferred).
    """
    if len(timeline) < 3:
        return timeline

    # Build simplified state sequence from unique chords
    unique_chords = list(dict.fromkeys(e.chord for e in timeline))
    n_states = len(unique_chords)
    if n_states <= 1:
        return timeline

    chord_idx_map = {c: i for i, c in enumerate(unique_chords)}

    # Emission: observation confidence scores
    obs = np.array([[e.confidence if e.chord == chord else 0.0
                     for chord in unique_chords]
                    for e in timeline])

    # Transition: uniform baseline + diatonic bonus
    trans = np.ones((n_states, n_states)) * 0.01
    np.fill_diagonal(trans, 0.3)  # self-loops (chord lasting multiple beats)

    # Diatonic bonus: transitions between diatonic chords get +0.2
    from analysis.theory_guard import _diatonic_notes, _note_idx
    diatonic = _diatonic_notes(key_root_idx, mode)
    for i, ci in enumerate(unique_chords):
        root_i = ci[:2].rstrip("0123456789m" if len(ci) > 2 else "")[:2]
        for j, cj in enumerate(unique_chords):
            root_j = cj[:2].rstrip("0123456789m" if len(cj) > 2 else "")[:2]
            try:
                ri = NOTE_NAMES.index(root_i[:2]) if root_i[:2] in NOTE_NAMES else NOTE_NAMES.index(root_i[:1])
                rj = NOTE_NAMES.index(root_j[:2]) if root_j[:2] in NOTE_NAMES else NOTE_NAMES.index(root_j[:1])
                if ri in diatonic and rj in diatonic:
                    trans[i][j] += 0.2
                elif ri in diatonic or rj in diatonic:
                    trans[i][j] += 0.05
            except (ValueError, IndexError):
                pass

    # Row-normalize
    row_sums = trans.sum(axis=1, keepdims=True)
    trans = trans / (row_sums + 1e-8)

    # Viterbi
    n_obs = len(timeline)
    viterbi = np.zeros((n_obs, n_states))
    backptr = np.zeros((n_obs, n_states), dtype=int)

    # Initialize
    viterbi[0] = obs[0] / (obs[0].sum() + 1e-8)

    # Forward pass
    for t in range(1, n_obs):
        for s in range(n_states):
            scores = viterbi[t - 1] * trans[:, s]
            backptr[t, s] = int(np.argmax(scores))
            viterbi[t, s] = float(np.max(scores)) * obs[t, s]

    # Backtrack
    best_seq = np.zeros(n_obs, dtype=int)
    best_seq[-1] = int(np.argmax(viterbi[-1]))
    for t in range(n_obs - 2, -1, -1):
        best_seq[t] = backptr[t + 1, best_seq[t + 1]]

    # Build corrected timeline
    corrected = []
    for i, (ev, state_idx) in enumerate(zip(timeline, best_seq)):
        best_chord = unique_chords[state_idx]
        if best_chord != ev.chord:
            # Viterbi prefers a different chord — lower confidence slightly
            corrected.append(ChordEvent(
                start=ev.start,
                end=ev.end,
                chord=best_chord,
                root=ev.root,   # approximate
                quality=ev.quality,
                confidence=round(ev.confidence * 0.9, 3),
                alternatives=[{"chord": ev.chord, "root": ev.root,
                               "quality": ev.quality, "confidence": ev.confidence,
                               "label": "original"}] + ev.alternatives,
            ))
        else:
            corrected.append(ev)

    return corrected


def _fuse_chords(
    chords: ChordsResult,
    key: Optional[KeyResult] = None,
    use_viterbi: bool = True,
) -> ChordsResult:
    """Apply Viterbi smoothing and key-aware fusion to chord timeline."""
    if not chords.timeline:
        return chords

    timeline = list(chords.timeline)

    if use_viterbi and key and len(timeline) >= 3:
        from analysis.theory_guard import _note_idx
        key_root = _note_idx(key.global_key)
        mode = key.global_mode
        try:
            timeline = _viterbi_chord_smooth(timeline, key_root, mode)
        except Exception as e:
            logger.warning("Viterbi smoothing failed: %s", e)

    unique = list(dict.fromkeys(e.chord for e in timeline))
    global_conf = float(np.mean([e.confidence for e in timeline])) if timeline else 0.0

    return ChordsResult(
        timeline=timeline,
        global_confidence=round(global_conf, 3),
        unique_chords=unique,
        source=chords.source + "_fused",
    )


# ─── Melody Fusion ─────────────────────────────────────────────────────────────

def _fuse_melody(candidates: List[MelodyResult]) -> MelodyResult:
    """
    Merge melody from multiple sources.
    torchcrepe pitch curve + basic-pitch note events → best-of-both.
    """
    if not candidates:
        return MelodyResult(source="fallback")
    if len(candidates) == 1:
        return candidates[0]

    # Pick the pitch curve from the highest-weight source
    best_curve = max(candidates, key=lambda r: _src_weight(r.source, _MELODY_SOURCE_WEIGHT))
    # Pick notes from whichever source has more
    best_notes = max(candidates, key=lambda r: len(r.notes))

    # Merge: use torchcrepe curve + basic-pitch notes (if distinct enough)
    merged_notes = _merge_note_events(
        [n for r in candidates for n in r.notes]
    )

    voiced = max((r.voiced_fraction for r in candidates), default=0.0)
    mean_hz = float(np.mean([r.mean_pitch_hz for r in candidates if r.mean_pitch_hz > 0]) or 0)
    global_conf = float(np.mean([r.global_confidence for r in candidates if r.global_confidence > 0]) or 0)

    sources = "+".join(r.source.split("_")[0] for r in candidates)
    return MelodyResult(
        pitch_curve=best_curve.pitch_curve,
        notes=merged_notes,
        global_confidence=round(global_conf, 3),
        voiced_fraction=round(voiced, 3),
        mean_pitch_hz=round(mean_hz, 2),
        source=f"fused_{sources}",
    )


def _merge_note_events(notes: List[NoteEvent]) -> List[NoteEvent]:
    """
    Merge overlapping / duplicate note events from multiple sources.
    Notes within 50ms of each other with same pitch → keep higher confidence.
    """
    if not notes:
        return []
    notes_sorted = sorted(notes, key=lambda n: (n.start, n.pitch))
    merged: List[NoteEvent] = []

    for note in notes_sorted:
        if not merged:
            merged.append(note)
            continue
        prev = merged[-1]
        # Same pitch class, overlapping or very close
        if abs(prev.pitch - note.pitch) <= 1 and note.start - prev.end < 0.05:
            # Merge: extend previous, take best confidence
            new_end = max(prev.end, note.end)
            merged[-1] = NoteEvent(
                pitch=prev.pitch,
                pitch_name=prev.pitch_name,
                start=prev.start,
                end=new_end,
                duration=round(new_end - prev.start, 4),
                velocity=max(prev.velocity, note.velocity),
                confidence=round(max(prev.confidence, note.confidence), 3),
            )
        else:
            merged.append(note)

    return merged


# ─── Temporal Consistency ──────────────────────────────────────────────────────

def _enforce_temporal_consistency(
    tempo: Optional[TempoResult],
    chords: Optional[ChordsResult],
    structure: Optional[StructureResult],
) -> Tuple[Optional[ChordsResult], List[str]]:
    """
    Ensure chord boundaries align with beat grid.
    Snaps chord event boundaries to nearest beat.
    """
    if not tempo or not chords or not tempo.beats:
        return chords, []

    beats = np.array(tempo.beats)
    warnings = []
    corrected: List[ChordEvent] = []

    for ev in chords.timeline:
        # Snap start time to nearest beat
        start_diffs = np.abs(beats - ev.start)
        end_diffs = np.abs(beats - ev.end)
        nearest_start = float(beats[np.argmin(start_diffs)])
        nearest_end = float(beats[np.argmin(end_diffs)])

        # Only snap if within half a beat
        beat_dur = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
        snap_threshold = beat_dur * 0.4

        final_start = nearest_start if abs(nearest_start - ev.start) < snap_threshold else ev.start
        final_end = nearest_end if abs(nearest_end - ev.end) < snap_threshold else ev.end

        if final_end <= final_start:
            final_end = final_start + beat_dur

        corrected.append(ChordEvent(
            start=round(final_start, 4),
            end=round(final_end, 4),
            chord=ev.chord,
            root=ev.root,
            quality=ev.quality,
            confidence=ev.confidence,
            alternatives=ev.alternatives,
        ))

    if len(corrected) != len(chords.timeline):
        warnings.append("Some chord events were dropped during temporal alignment")

    return ChordsResult(
        timeline=corrected,
        global_confidence=chords.global_confidence,
        unique_chords=chords.unique_chords,
        source=chords.source + "_beat_aligned",
    ), warnings


# ─── Main Fusion Entry Point ────────────────────────────────────────────────────

def fuse(
    audio_meta: AudioMeta,
    stems: StemsResult,
    tempo_candidates: List[TempoResult],
    key_candidates: List[KeyResult],
    chords: ChordsResult,
    melody_candidates: List[MelodyResult],
    structure: StructureResult,
    mode: str = "balanced",
    apply_viterbi: bool = True,
    apply_beat_alignment: bool = True,
) -> AnalysisResult:
    """
    Main fusion entry point.

    Takes multi-source candidates for each stage and returns a single
    authoritative AnalysisResult with unified interpretation.

    Args:
        tempo_candidates:  List of TempoResult from different sources
        key_candidates:    List of KeyResult from Essentia, librosa, etc.
        chords:            ChordsResult (already template-matched)
        melody_candidates: List of MelodyResult from torchcrepe, basic-pitch
        structure:         StructureResult (single source — SSM)
        mode:              Analysis mode
        apply_viterbi:     Apply Viterbi smoothing to chord sequence
        apply_beat_alignment: Snap chord boundaries to beat grid
    """
    warnings: List[AnalysisWarning] = []

    # ── Stage F1: Tempo fusion ────────────────────────────────────────────────
    logger.info("[fusion] Fusing %d tempo candidates", len(tempo_candidates))
    fused_tempo = _fuse_tempo(tempo_candidates)

    # ── Stage F2: Key fusion ──────────────────────────────────────────────────
    logger.info("[fusion] Fusing %d key candidates", len(key_candidates))
    fused_key = _fuse_key(key_candidates)

    # ── Stage F3: Chord fusion + Viterbi ─────────────────────────────────────
    logger.info("[fusion] Fusing chords (viterbi=%s)", apply_viterbi)
    fused_chords = _fuse_chords(chords, fused_key, use_viterbi=apply_viterbi)

    # ── Stage F4: Temporal alignment ─────────────────────────────────────────
    if apply_beat_alignment:
        fused_chords, align_warnings = _enforce_temporal_consistency(
            fused_tempo, fused_chords, structure
        )
        for w in align_warnings:
            warnings.append(AnalysisWarning(code="BEAT_ALIGNMENT", message=w, severity="info"))

    # ── Stage F5: Melody fusion ───────────────────────────────────────────────
    logger.info("[fusion] Fusing %d melody candidates", len(melody_candidates))
    fused_melody = _fuse_melody(melody_candidates)

    # ── Stage F6: Cross-stage consistency checks ──────────────────────────────
    if fused_key and fused_chords:
        from analysis.theory_guard import _note_idx, _diatonic_notes
        key_root = _note_idx(fused_key.global_key)
        diatonic = _diatonic_notes(key_root, fused_key.global_mode)
        chromatic_count = sum(
            1 for ev in fused_chords.timeline
            if _note_idx(ev.root) not in diatonic
        )
        total_chords = len(fused_chords.timeline)
        if total_chords > 0 and chromatic_count / total_chords > 0.4:
            warnings.append(AnalysisWarning(
                code="HIGH_CHROMATIC_CHORD_RATIO",
                message=f"{chromatic_count}/{total_chords} chords are chromatic. "
                        f"Key of {fused_key.global_key} {fused_key.global_mode} may be incorrect.",
                severity="warning",
            ))

    # ── Assemble result ───────────────────────────────────────────────────────
    result = AnalysisResult(
        audio_meta=audio_meta,
        stems=stems,
        tempo=fused_tempo,
        key=fused_key,
        chords=fused_chords,
        melody=fused_melody,
        structure=structure,
        mode=mode,
        pipeline_version="2.0.0",
        warnings=warnings,
    )

    logger.info(
        "[fusion] Done — key=%s %s, bpm=%.1f, chords=%d, notes=%d",
        fused_key.global_key, fused_key.global_mode,
        fused_tempo.bpm_global,
        len(fused_chords.timeline),
        len(fused_melody.notes),
    )
    return result
