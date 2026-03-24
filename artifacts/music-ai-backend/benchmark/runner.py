"""
Benchmark Runner — Muzikal Phase 3 Evaluation Infrastructure.

Runs the analysis pipeline against an annotated corpus and computes:
  - Beat F-measure (MIREX ±70ms window)
  - Tempo accuracy (relative error, octave-equivalence)
  - Key accuracy (exact, relative, enharmonic-aware)
  - Chord overlap accuracy (root / majmin / seventh / MIREX modes)
  - Harmonic rhythm accuracy
  - Structure boundary F-measure (±0.5s window)
  - Per-stage pipeline confidence

Usage (programmatic):
    from benchmark.runner import BenchmarkRunner
    from benchmark.schemas import make_synthetic_corpus

    corpus = make_synthetic_corpus()
    runner = BenchmarkRunner(pipeline_mode="mock")
    report = runner.run(corpus)
    report.save_json("report.json")

Usage (CLI):
    python -m benchmark.cli --corpus corpus.json --output report.json
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from tests.eval.metrics import (
    aggregate_metrics,
    beat_fmeasure,
    chord_overlap_accuracy,
    harmonic_rhythm_accuracy,
    key_accuracy,
    structure_boundary_fmeasure,
    tempo_accuracy,
)
from benchmark.schemas import BenchmarkCorpus, GroundTruthEntry

logger = logging.getLogger(__name__)


# ─── Result types ────────────────────────────────────────────────────────────

@dataclass
class SongResult:
    song_id: str
    audio_path: str
    tags: List[str]
    elapsed_sec: float
    error: Optional[str] = None

    # Tempo
    beat_fmeasure: Optional[Dict[str, float]] = None
    tempo_accuracy: Optional[Dict[str, float]] = None

    # Harmony
    key_accuracy: Optional[Dict[str, bool]] = None
    chord_overlap_root: Optional[Dict[str, float]] = None
    chord_overlap_majmin: Optional[Dict[str, float]] = None
    chord_overlap_seventh: Optional[Dict[str, float]] = None
    chord_overlap_mirex: Optional[Dict[str, float]] = None
    harmonic_rhythm: Optional[Dict[str, float]] = None

    # Structure
    structure_boundary: Optional[Dict[str, float]] = None

    # Pipeline metadata
    pipeline_version: Optional[str] = None
    analysis_confidence: Optional[float] = None
    est_bpm: Optional[float] = None
    est_key: Optional[str] = None
    est_mode: Optional[str] = None


@dataclass
class BenchmarkReport:
    corpus_name: str
    corpus_version: str
    pipeline_mode: str
    pipeline_version: str
    timestamp: str
    total_songs: int
    successful_songs: int
    failed_songs: int
    total_elapsed_sec: float

    # Aggregated metrics (averages across all songs)
    agg_beat_fmeasure: Dict[str, float] = field(default_factory=dict)
    agg_tempo_accuracy: Dict[str, float] = field(default_factory=dict)
    agg_key_exact_rate: float = 0.0
    agg_key_relative_rate: float = 0.0
    agg_chord_root: Dict[str, float] = field(default_factory=dict)
    agg_chord_majmin: Dict[str, float] = field(default_factory=dict)
    agg_chord_seventh: Dict[str, float] = field(default_factory=dict)
    agg_chord_mirex: Dict[str, float] = field(default_factory=dict)
    agg_harmonic_rhythm: Dict[str, float] = field(default_factory=dict)
    agg_structure_boundary: Dict[str, float] = field(default_factory=dict)

    songs: List[SongResult] = field(default_factory=list)

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False, default=str)

    def print_summary(self) -> None:
        lines = [
            f"\n{'='*60}",
            f"  BENCHMARK REPORT — {self.corpus_name} v{self.corpus_version}",
            f"  Pipeline: {self.pipeline_mode}  |  Version: {self.pipeline_version}",
            f"  Songs: {self.successful_songs}/{self.total_songs} OK  |  {self.total_elapsed_sec:.1f}s total",
            f"{'='*60}",
            f"  RHYTHM",
            f"    Beat F-measure     : {self.agg_beat_fmeasure.get('f_measure', 0):.3f}",
            f"    Tempo correct (4%) : {self.agg_tempo_accuracy.get('correct', 0):.1%}",
            f"  HARMONY",
            f"    Key exact          : {self.agg_key_exact_rate:.1%}",
            f"    Key relative       : {self.agg_key_relative_rate:.1%}",
            f"    Chord root acc.    : {self.agg_chord_root.get('accuracy', 0):.3f}",
            f"    Chord majmin acc.  : {self.agg_chord_majmin.get('accuracy', 0):.3f}",
            f"    Chord MIREX acc.   : {self.agg_chord_mirex.get('accuracy', 0):.3f}",
            f"    Harmonic rhythm F  : {self.agg_harmonic_rhythm.get('f_measure', 0):.3f}",
            f"  STRUCTURE",
            f"    Boundary F-measure : {self.agg_structure_boundary.get('f_measure', 0):.3f}",
            f"{'='*60}",
        ]
        if self.failed_songs:
            lines.append(f"  FAILED SONGS ({self.failed_songs}):")
            for s in self.songs:
                if s.error:
                    lines.append(f"    - {s.song_id}: {s.error}")
        print("\n".join(lines))


# ─── Pipeline adapter ─────────────────────────────────────────────────────────

class PipelineAdapter:
    """
    Wraps the analysis pipeline for benchmark use.

    In 'mock' mode: returns synthetic analysis without running audio processing.
    In 'real'  mode: calls the actual analysis pipeline on each audio file.
    """

    def __init__(self, mode: str = "mock"):
        self.mode = mode

    def analyze(self, entry: GroundTruthEntry) -> Dict[str, Any]:
        if self.mode == "mock":
            return self._mock_analyze(entry)
        elif self.mode == "real":
            return self._real_analyze(entry)
        else:
            raise ValueError(f"Unknown pipeline mode: {self.mode!r}")

    def _mock_analyze(self, entry: GroundTruthEntry) -> Dict[str, Any]:
        """
        Returns a near-perfect mock analysis that matches ground truth.
        Used for unit testing the benchmark runner itself (not the pipeline).
        Adds ±5% noise so tests are not trivially perfect.
        """
        import random
        rng = random.Random(hash(entry.id))

        def jitter_rel(val: float, pct: float = 0.03) -> float:
            return val * (1 + rng.uniform(-pct, pct))

        def jitter_abs(val: float, max_ms: float = 20.0) -> float:
            return val + rng.uniform(-max_ms / 1000.0, max_ms / 1000.0)

        bpm = jitter_rel(entry.bpm, 0.02)
        beats = [jitter_abs(b, 15.0) for b in entry.beats]
        downbeats = [jitter_abs(b, 20.0) for b in entry.downbeats]

        chords = [
            {"start": c.start, "end": c.end, "chord": c.chord}
            for c in entry.chords
        ]
        structure_boundaries = [s.start for s in entry.structure] + [entry.total_duration]

        return {
            "pipeline_version": "mock-2.0.0",
            "rhythm": {
                "bpm": bpm,
                "beats": beats,
                "downbeats": downbeats,
                "confidence": 0.92,
            },
            "key": {
                "globalKey": entry.key,
                "mode": entry.mode,
                "confidence": 0.88,
            },
            "chords": {
                "segments": chords,
            },
            "structure": {
                "sections": [
                    {"label": s.label, "start": s.start, "end": s.end}
                    for s in entry.structure
                ],
                "boundaries": structure_boundaries,
            },
            "confidence": {"overall": 0.90},
            "isMock": True,
        }

    def _real_analyze(self, entry: GroundTruthEntry) -> Dict[str, Any]:
        """Run actual pipeline. Requires audio file at entry.audio_path."""
        import os
        if not os.path.exists(entry.audio_path):
            raise FileNotFoundError(f"Audio not found: {entry.audio_path}")

        try:
            from analysis.pipeline import analyze
            result = analyze(entry.audio_path, mode="balanced")
            return result if isinstance(result, dict) else result.model_dump()
        except Exception as exc:
            raise RuntimeError(f"Pipeline failed for {entry.id}: {exc}") from exc


# ─── Benchmark runner ─────────────────────────────────────────────────────────

class BenchmarkRunner:
    """
    Main benchmark orchestrator.

    Iterates through a corpus, runs the pipeline on each entry, and
    computes all MIR metrics defined in tests/eval/metrics.py.
    """

    def __init__(self, pipeline_mode: str = "mock"):
        self.adapter = PipelineAdapter(mode=pipeline_mode)
        self.pipeline_mode = pipeline_mode

    def run(self, corpus: BenchmarkCorpus) -> BenchmarkReport:
        from datetime import datetime, timezone

        logger.info(
            "Starting benchmark: corpus=%s entries=%d mode=%s",
            corpus.name, len(corpus.entries), self.pipeline_mode
        )

        songs: List[SongResult] = []
        total_start = time.monotonic()

        for entry in corpus.entries:
            result = self._run_one(entry)
            songs.append(result)

        total_elapsed = time.monotonic() - total_start
        ok = [s for s in songs if s.error is None]
        failed = [s for s in songs if s.error is not None]

        report = BenchmarkReport(
            corpus_name=corpus.name,
            corpus_version=corpus.version,
            pipeline_mode=self.pipeline_mode,
            pipeline_version=ok[0].pipeline_version or "unknown" if ok else "unknown",
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_songs=len(songs),
            successful_songs=len(ok),
            failed_songs=len(failed),
            total_elapsed_sec=round(total_elapsed, 3),
            songs=songs,
        )

        self._aggregate(report, ok)
        logger.info("Benchmark complete: %d ok, %d failed", len(ok), len(failed))
        return report

    def _run_one(self, entry: GroundTruthEntry) -> SongResult:
        t0 = time.monotonic()
        result = SongResult(
            song_id=entry.id,
            audio_path=entry.audio_path,
            tags=entry.tags,
            elapsed_sec=0.0,
        )

        try:
            analysis = self.adapter.analyze(entry)
            result.pipeline_version = analysis.get("pipelineVersion") or analysis.get("pipeline_version")
            result.analysis_confidence = (
                analysis.get("confidence", {}) or {}
            ).get("overall")

            self._score_rhythm(result, entry, analysis)
            self._score_key(result, entry, analysis)
            self._score_chords(result, entry, analysis)
            self._score_structure(result, entry, analysis)

        except Exception as exc:
            logger.warning("Song %s failed: %s", entry.id, exc)
            result.error = str(exc)

        result.elapsed_sec = round(time.monotonic() - t0, 3)
        return result

    def _score_rhythm(self, result: SongResult, entry: GroundTruthEntry, analysis: dict) -> None:
        rhythm = analysis.get("rhythm") or {}
        est_bpm = rhythm.get("bpm") or 0.0
        est_beats = rhythm.get("beats") or []

        result.est_bpm = est_bpm

        if entry.beats and est_beats:
            result.beat_fmeasure = beat_fmeasure(entry.beats, est_beats)

        if entry.bpm and est_bpm:
            result.tempo_accuracy = tempo_accuracy(entry.bpm, est_bpm)

    def _score_key(self, result: SongResult, entry: GroundTruthEntry, analysis: dict) -> None:
        key_data = analysis.get("key") or {}
        est_key = key_data.get("globalKey") or ""
        est_mode = key_data.get("mode") or ""

        result.est_key = est_key
        result.est_mode = est_mode

        if entry.key and est_key:
            result.key_accuracy = key_accuracy(entry.key, entry.mode, est_key, est_mode)

    def _score_chords(self, result: SongResult, entry: GroundTruthEntry, analysis: dict) -> None:
        chords_data = analysis.get("chords") or {}
        est_chords = chords_data.get("segments") or []

        if not entry.chords or not est_chords:
            return

        ref_chords = [{"start": c.start, "end": c.end, "chord": c.chord} for c in entry.chords]
        dur = entry.total_duration

        result.chord_overlap_root   = chord_overlap_accuracy(ref_chords, est_chords, dur, "root")
        result.chord_overlap_majmin = chord_overlap_accuracy(ref_chords, est_chords, dur, "majmin")
        result.chord_overlap_seventh = chord_overlap_accuracy(ref_chords, est_chords, dur, "seventh")
        result.chord_overlap_mirex  = chord_overlap_accuracy(ref_chords, est_chords, dur, "mirex")
        result.harmonic_rhythm      = harmonic_rhythm_accuracy(ref_chords, est_chords)

    def _score_structure(self, result: SongResult, entry: GroundTruthEntry, analysis: dict) -> None:
        structure_data = analysis.get("structure") or {}
        est_sections = structure_data.get("sections") or []

        if not entry.structure or not est_sections:
            return

        ref_boundaries = [s.start for s in entry.structure] + [entry.total_duration]
        est_boundaries = [
            float(s.get("start", s.get("startTime", 0.0))) for s in est_sections
        ] + [entry.total_duration]

        result.structure_boundary = structure_boundary_fmeasure(ref_boundaries, est_boundaries)

    def _aggregate(self, report: BenchmarkReport, ok: List[SongResult]) -> None:
        if not ok:
            return

        report.agg_beat_fmeasure = aggregate_metrics(
            [s.beat_fmeasure for s in ok if s.beat_fmeasure])
        report.agg_tempo_accuracy = aggregate_metrics(
            [s.tempo_accuracy for s in ok if s.tempo_accuracy])

        key_results = [s.key_accuracy for s in ok if s.key_accuracy]
        if key_results:
            report.agg_key_exact_rate = sum(
                1 for r in key_results if r.get("exact_correct")) / len(key_results)
            report.agg_key_relative_rate = sum(
                1 for r in key_results if r.get("relative_correct")) / len(key_results)

        report.agg_chord_root    = aggregate_metrics(
            [s.chord_overlap_root    for s in ok if s.chord_overlap_root])
        report.agg_chord_majmin  = aggregate_metrics(
            [s.chord_overlap_majmin  for s in ok if s.chord_overlap_majmin])
        report.agg_chord_seventh = aggregate_metrics(
            [s.chord_overlap_seventh for s in ok if s.chord_overlap_seventh])
        report.agg_chord_mirex   = aggregate_metrics(
            [s.chord_overlap_mirex   for s in ok if s.chord_overlap_mirex])
        report.agg_harmonic_rhythm = aggregate_metrics(
            [s.harmonic_rhythm for s in ok if s.harmonic_rhythm])
        report.agg_structure_boundary = aggregate_metrics(
            [s.structure_boundary for s in ok if s.structure_boundary])
