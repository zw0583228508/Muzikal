"""
High-accuracy multi-stage music analysis pipeline — v2.0.0

Usage:
    from analysis.pipeline import analyze

    result = analyze("/path/to/audio.mp3", mode="balanced")
    legacy_dict = result.to_legacy_format()

Modes:
    'fast'          — Single-pass librosa only, skips stem separation. ~5s
    'balanced'      — Full Demucs + madmom + Essentia + torchcrepe + basic-pitch.
                      Recommended for production. ~30–90s first run.
    'high_accuracy' — Same as balanced + ensemble voting + stronger smoothing.
                      Best accuracy, same runtime as balanced (cached).

Caching:
    All stages are cached per file hash (7-day TTL).
    Subsequent calls on the same file return results instantly.

Pipeline stages (balanced / high_accuracy):
    1.  Preprocess        — load, normalize, resample
    2.  Stem separation   — Demucs htdemucs (vocals/drums/bass/other)
    3.  Beat tracking     — madmom RNN+DBN on drums stem
    4a. Key detection     — Essentia HPCP on other stem
    4b. Key detection     — librosa K-S (second opinion for fusion)
    5.  Chord detection   — CQT chroma + bass stem weighting + template matching
    6.  Melody detection  — torchcrepe (pitch curve) + basic-pitch (note events)
    7.  Structure         — SSM + novelty on full mix
    8.  Smoothing         — median filter, chord merging, pitch smoothing
    9.  Theory correction — tempo trap fix, diatonic boosting
    10. FUSION ENGINE     — confidence-weighted fusion of all candidates
    11. Theory Guard      — final harmonic validity check + scale snapping
    12. Confidence        — global confidence annotation + warnings
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from analysis.schemas import AnalysisResult, AudioMeta, StemsResult
from analysis.preprocess import preprocess, AudioBundle
from analysis.cache import cache_get, cache_set
from analysis.confidence import annotate_confidence

logger = logging.getLogger(__name__)

VALID_MODES = {"fast", "balanced", "high_accuracy"}


def _run_fast(bundle: AudioBundle) -> AnalysisResult:
    """Fast mode: librosa only, no stem separation."""
    from audio.rhythm import analyze_rhythm
    from audio.key_mode import analyze_key
    from audio.chords import analyze_chords
    from audio.structure import analyze_structure

    from analysis.schemas import TempoResult, KeyResult, ChordsResult, StructureResult

    # Use existing audio/ modules as fast path
    rhythm = analyze_rhythm(bundle.y_mono, bundle.sr)
    key_data = analyze_key(bundle.y_mono, bundle.sr)
    chords_data = analyze_chords(bundle.y_mono, bundle.sr, rhythm, key_data)
    structure_data = analyze_structure(bundle.y_mono, bundle.sr, rhythm)

    # ── helpers to map legacy field formats to schemas ───────────────────────
    def _str_alts_to_dicts(alts) -> list:
        """Convert ['Am', 'F#m'] → [{'key': 'Am', 'mode': 'minor', 'confidence': 0.5}, ...]"""
        result = []
        for a in (alts or []):
            if isinstance(a, dict):
                result.append(a)
            elif isinstance(a, str):
                mode = "minor" if a.endswith("m") and not a.endswith("maj") else "major"
                result.append({"key": a, "mode": mode, "confidence": 0.5})
        return result

    def _parse_chord_root_quality(chord_str: str):
        """Parse 'Am7' → ('A', 'min7'), 'Cmaj7' → ('C', 'maj7'), etc."""
        notes = ["C#", "D#", "F#", "G#", "A#", "Db", "Eb", "Gb", "Ab", "Bb",
                 "C", "D", "E", "F", "G", "A", "B"]
        root = "C"
        for n in notes:
            if chord_str.startswith(n):
                root = n
                break
        quality_str = chord_str[len(root):]
        # Map common quality strings
        quality_map = {
            "": "maj", "m": "min", "min": "min", "maj": "maj",
            "m7": "min7", "min7": "min7", "maj7": "maj7",
            "7": "dom7", "dim": "dim", "aug": "aug", "dim7": "dim7",
            "sus2": "sus2", "sus4": "sus4", "add9": "add9",
            "m9": "min9", "maj9": "maj9",
        }
        quality = quality_map.get(quality_str, quality_str or "maj")
        return root, quality

    # ── Convert to schema types ───────────────────────────────────────────────
    ts = rhythm.get("timeSignature", {})
    if isinstance(ts, str):
        parts = ts.split("/")
        ts_num, ts_den = int(parts[0]) if parts else 4, int(parts[1]) if len(parts) > 1 else 4
        ts_str = ts
    else:
        ts_num = ts.get("numerator", 4)
        ts_den = ts.get("denominator", 4)
        ts_str = f"{ts_num}/{ts_den}"

    tempo = TempoResult(
        bpm_global=float(rhythm.get("bpm", 120.0)),
        beats=rhythm.get("beats", []),
        downbeats=rhythm.get("downbeats", []),
        meter=ts_str,
        meter_numerator=ts_num,
        meter_denominator=ts_den,
        confidence=float(rhythm.get("confidence", 0.7)),
        source="librosa_fast",
    )

    key_alts_raw = key_data.get("alternatives", [])
    key = KeyResult(
        global_key=key_data.get("key", "C"),
        global_mode=key_data.get("mode", "major"),
        global_confidence=float(key_data.get("confidence", 0.6)),
        alternatives=_str_alts_to_dicts(key_alts_raw),
        source="librosa_fast",
    )

    from analysis.schemas import ChordEvent
    chord_timeline = []
    # Legacy format uses "chords" key with startTime/endTime
    raw_chords = chords_data.get("chords", chords_data.get("timeline", []))
    for c in raw_chords:
        try:
            chord_str = c.get("chord", "C")
            root, quality = _parse_chord_root_quality(chord_str)
            alts_raw = c.get("alternatives", [])
            alts = []
            for a in alts_raw:
                if isinstance(a, str):
                    ar, aq = _parse_chord_root_quality(a)
                    alts.append({"chord": a, "root": ar, "quality": aq, "confidence": 0.4})
                elif isinstance(a, dict):
                    alts.append(a)
            chord_timeline.append(ChordEvent(
                start=float(c.get("start", c.get("startTime", 0.0))),
                end=float(c.get("end", c.get("endTime", 1.0))),
                chord=chord_str,
                root=root,
                quality=quality,
                confidence=float(c.get("confidence", 0.5)),
                alternatives=alts,
            ))
        except Exception:
            pass

    chords = ChordsResult(
        timeline=chord_timeline,
        global_confidence=float(chords_data.get("confidence", 0.5)),
        unique_chords=list(dict.fromkeys(e.chord for e in chord_timeline)),
        source="librosa_fast",
    )

    from analysis.schemas import Section
    sections = []
    for s in structure_data.get("sections", []):
        try:
            sections.append(Section(
                label=s.get("label", "verse"),
                start=float(s.get("start", s.get("startTime", 0.0))),
                end=float(s.get("end", s.get("endTime", 1.0))),
                duration=float(s.get("end", s.get("endTime", 1.0))) - float(s.get("start", s.get("startTime", 0.0))),
                confidence=float(s.get("confidence", 0.6)),
            ))
        except Exception:
            pass

    structure = StructureResult(
        sections=sections,
        num_sections=len(sections),
        confidence=float(structure_data.get("confidence", 0.6)),
        source="librosa_fast",
    )

    return AnalysisResult(
        audio_meta=bundle.meta,
        stems=StemsResult(separation_mode="skipped"),
        tempo=tempo,
        key=key,
        chords=chords,
        structure=structure,
        mode="fast",
    )


def _run_full(bundle: AudioBundle, mode: str) -> AnalysisResult:
    """
    Balanced / high_accuracy mode: full multi-engine pipeline.

    Stage sequence:
      2.  Stem separation (Demucs)
      3.  Beat tracking (madmom)
      4a. Key detection (Essentia HPCP)
      4b. Key detection (librosa K-S, second opinion)
      5.  Chord detection (CQT + bass weighting)
      6.  Melody (torchcrepe + basic-pitch)
      7.  Structure (SSM)
      8.  Smoothing
      9.  Theory correction (pre-fusion)
      10. FUSION ENGINE (confidence-weighted multi-source)
      11. Theory Guard (final harmonic validation)
    """
    from analysis.separation import separate_stems
    from analysis.beat_tracker import track_beats
    from analysis.key_detector import detect_key, _detect_key_librosa
    from analysis.chord_detector import detect_chords
    from analysis.melody_detector import detect_melody
    from analysis.structure_detector import detect_structure
    from analysis.smoothing import (
        smooth_bpm_curve, smooth_chords, smooth_pitch_curve, consolidate_key_segments
    )
    from analysis.theory_correction import apply_theory_corrections
    from analysis.fusion_engine import fuse as fusion_fuse
    from analysis.theory_guard import apply_theory_guard

    t0 = time.time()

    # ── Stage 2: Stem separation ──────────────────────────────────────────────
    logger.info("[pipeline] Stage 2: Stem separation")
    stems = separate_stems(bundle)
    logger.info("[pipeline] Separation done in %.1fs", time.time() - t0)

    # ── Stage 3: Beat tracking (madmom on drums stem) ─────────────────────────
    logger.info("[pipeline] Stage 3: Beat tracking")
    tempo = track_beats(bundle, stems=stems)
    logger.info("[pipeline] Beats: BPM=%.1f conf=%.2f (%.1fs)", tempo.bpm_global, tempo.confidence, time.time() - t0)

    # ── Stage 4a: Key detection — Essentia HPCP (primary) ─────────────────────
    logger.info("[pipeline] Stage 4a: Key detection (Essentia)")
    key_essentia = detect_key(bundle, stems=stems)
    logger.info("[pipeline] Key (Essentia): %s %s conf=%.2f", key_essentia.global_key, key_essentia.global_mode, key_essentia.global_confidence)

    # ── Stage 4b: Key detection — librosa K-S (second opinion) ───────────────
    key_librosa = None
    try:
        logger.info("[pipeline] Stage 4b: Key detection (librosa K-S)")
        ks_key, ks_mode, ks_conf, ks_alts = _detect_key_librosa(bundle.y_mono, bundle.sr)
        from analysis.schemas import KeyResult
        key_librosa = KeyResult(
            global_key=ks_key,
            global_mode=ks_mode,
            global_confidence=round(float(ks_conf), 3),
            alternatives=ks_alts,
            source="librosa",
        )
        logger.info("[pipeline] Key (librosa): %s %s conf=%.2f", ks_key, ks_mode, ks_conf)
    except Exception as e:
        logger.warning("[pipeline] librosa key failed: %s", e)

    # Collect key candidates for fusion
    key_candidates = [key_essentia]
    if key_librosa:
        key_candidates.append(key_librosa)

    # ── Stage 5: Chord detection — HSMM primary, template fallback ──────────
    logger.info("[pipeline] Stage 5: Chord detection (HSMM Viterbi)")
    try:
        from analysis.chord_hsmm import detect_chords_hsmm
        # Run HSMM with key conditioning (key detected in Stage 4a)
        chords = detect_chords_hsmm(
            bundle, stems=stems, tempo=tempo, key=key_essentia, force=False
        )
        if not chords.timeline:
            raise ValueError("HSMM returned empty timeline")
        logger.info(
            "[pipeline] HSMM chords: %d events, src=%s (%.1fs)",
            len(chords.timeline), chords.source, time.time() - t0
        )
    except Exception as hsmm_err:
        logger.warning("[pipeline] HSMM failed (%s) — falling back to template", hsmm_err)
        chords = detect_chords(bundle, stems=stems, tempo=tempo)
        logger.info(
            "[pipeline] Template chords (fallback): %d events (%.1fs)",
            len(chords.timeline), time.time() - t0
        )

    # ── Stage 6: Melody (torchcrepe + basic-pitch) ────────────────────────────
    logger.info("[pipeline] Stage 6: Melody detection")
    melody = detect_melody(bundle, stems=stems)
    logger.info("[pipeline] Melody: %d notes src=%s (%.1fs)", len(melody.notes), melody.source, time.time() - t0)

    # ── Stage 7: Structure (SSM) ──────────────────────────────────────────────
    logger.info("[pipeline] Stage 7: Structure detection")
    structure = detect_structure(bundle)
    logger.info("[pipeline] Structure: %d sections (%.1fs)", len(structure.sections), time.time() - t0)

    # ── Stage 8: Smoothing ────────────────────────────────────────────────────
    logger.info("[pipeline] Stage 8: Smoothing")
    smooth_window = 7 if mode == "high_accuracy" else 5
    tempo   = smooth_bpm_curve(tempo, window=smooth_window)
    chords  = smooth_chords(chords, min_duration=0.75)
    melody  = smooth_pitch_curve(melody)
    key_essentia = consolidate_key_segments(key_essentia)
    if key_librosa:
        key_librosa = consolidate_key_segments(key_librosa)

    # ── Stage 9: Theory correction (pre-fusion) ───────────────────────────────
    logger.info("[pipeline] Stage 9: Theory correction")
    tempo, key_essentia, chords = apply_theory_corrections(
        tempo=tempo, key=key_essentia, chords=chords
    )
    # Re-sync librosa key candidates after theory correction
    key_candidates = [key_essentia]
    if key_librosa:
        key_candidates.append(key_librosa)

    # ── Stage 10: FUSION ENGINE ───────────────────────────────────────────────
    logger.info("[pipeline] Stage 10: Fusion engine (viterbi=%s, beat_align=%s)", True, True)
    result = fusion_fuse(
        audio_meta=bundle.meta,
        stems=stems,
        tempo_candidates=[tempo],            # single madmom source (high trust)
        key_candidates=key_candidates,       # Essentia + librosa voting
        chords=chords,                       # Viterbi + beat-alignment applied inside
        melody_candidates=[melody],          # merged crepe+bp
        structure=structure,
        mode=mode,
        apply_viterbi=True,
        apply_beat_alignment=(mode in ("balanced", "high_accuracy")),
    )
    logger.info("[pipeline] Fusion done (%.1fs)", time.time() - t0)

    # ── Stage 11: Theory Guard (final harmonic validation) ────────────────────
    logger.info("[pipeline] Stage 11: Theory Guard")
    result = apply_theory_guard(result)
    logger.info("[pipeline] Theory Guard done — %d warnings total", len(result.warnings))

    # ── Stage 12: Harmonic classification + Canonical Score ───────────────────
    logger.info("[pipeline] Stage 12: Harmonic classification + Canonical score")
    from analysis.chord_classifier import classify as chord_classify
    from analysis.canonical import to_canonical

    if result.chords:
        result.chords = chord_classify(result.chords, result.key)
        logger.info(
            "[pipeline] Chord classifier: diatonic=%.0f%%, cadences=%d",
            result.chords.diatonic_ratio * 100, len(result.chords.cadences),
        )

    canonical = to_canonical(result)
    result.canonical = canonical  # type: ignore[attr-defined]  — duck-typed field

    logger.info(
        "[pipeline] Canonical: %d bars, %d notes, %.0f%% diatonic (%.1fs)",
        canonical.num_measures, canonical.num_notes,
        canonical.diatonic_ratio * 100, time.time() - t0,
    )

    logger.info("[pipeline] Full pipeline DONE in %.1fs", time.time() - t0)
    return result


def analyze(
    audio_path: str,
    mode: str = "balanced",
    force: bool = False,
) -> AnalysisResult:
    """
    Main pipeline entry point.

    Args:
        audio_path: Path to the audio file (MP3, WAV, FLAC, OGG, M4A, etc.)
        mode:       'fast' | 'balanced' | 'high_accuracy'
        force:      If True, bypass all caches and recompute everything.

    Returns:
        AnalysisResult with all stages populated.
        Call .to_legacy_format() for the JSON-serializable dict expected by the API.
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        logger.warning("Unknown analysis mode '%s', defaulting to 'balanced'", mode)
        mode = "balanced"

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    t_start = time.time()
    logger.info("[pipeline] Starting analysis — mode=%s file=%s", mode, os.path.basename(audio_path))

    # Stage 1: Preprocess
    bundle = preprocess(audio_path)

    # Check full-pipeline cache
    if not force and mode != "fast":
        stage_key = f"pipeline_{mode}"
        cached = cache_get(bundle.file_hash, stage_key)
        if cached is not None:
            logger.info("[pipeline] Full pipeline cache hit (%.1fs)", time.time() - t_start)
            result = AnalysisResult.model_validate(cached)
            return result

    # Run appropriate pipeline
    if mode == "fast":
        result = _run_fast(bundle)
    else:
        result = _run_full(bundle, mode)

    # Stage 10: Confidence annotation
    result = annotate_confidence(result)

    # Cache full pipeline result
    if not force and mode != "fast":
        stage_key = f"pipeline_{mode}"
        cache_set(bundle.file_hash, stage_key, result.model_dump())

    elapsed = time.time() - t_start
    logger.info(
        "[pipeline] DONE in %.1fs — key=%s %s, bpm=%.1f, conf=%.2f, warnings=%d",
        elapsed, result.key.global_key if result.key else "?",
        result.key.global_mode if result.key else "?",
        result.tempo.bpm_global if result.tempo else 0,
        result.global_confidence,
        len(result.warnings),
    )

    return result


def analyze_to_dict(
    audio_path: str,
    mode: str = "balanced",
    force: bool = False,
) -> dict:
    """
    Convenience wrapper — returns the legacy dict format directly.
    Drop-in replacement for the existing analyzer.analyze_audio().
    """
    result = analyze(audio_path, mode=mode, force=force)
    return result.to_legacy_format()
