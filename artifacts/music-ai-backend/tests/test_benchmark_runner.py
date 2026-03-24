"""
Tests for the Phase 3 benchmark runner framework.

Validates:
  - Synthetic corpus creation and schema loading
  - BenchmarkRunner execution in mock mode (no audio required)
  - Metric aggregation correctness
  - Report generation (JSON + HTML)
  - CLI entry point
"""

import json
import os
import tempfile

import pytest

from benchmark.runner import BenchmarkRunner, BenchmarkReport
from benchmark.schemas import (
    BenchmarkCorpus,
    GroundTruthEntry,
    ChordEntry,
    SectionEntry,
    make_synthetic_corpus,
)


# ─── Corpus schema tests ──────────────────────────────────────────────────────

class TestGroundTruthSchema:

    def test_make_synthetic_corpus(self):
        corpus = make_synthetic_corpus()
        assert corpus.name
        assert len(corpus.entries) >= 2
        for entry in corpus.entries:
            assert entry.id
            assert entry.bpm > 0
            assert entry.key
            assert entry.mode
            assert entry.total_duration > 0

    def test_chord_entry_from_dict(self):
        c = ChordEntry.from_dict({"start": 0.0, "end": 4.0, "chord": "Cmaj7"})
        assert c.start == 0.0
        assert c.chord == "Cmaj7"

    def test_section_entry_from_dict(self):
        s = SectionEntry.from_dict({"label": "chorus", "start": 32.0, "end": 56.0})
        assert s.label == "chorus"
        assert s.start == 32.0

    def test_corpus_json_roundtrip(self):
        corpus = make_synthetic_corpus()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            path = f.name
        try:
            corpus.to_json(path)
            loaded = BenchmarkCorpus.from_json(path)
            assert loaded.name == corpus.name
            assert len(loaded.entries) == len(corpus.entries)
            assert loaded.entries[0].id == corpus.entries[0].id
            assert loaded.entries[0].bpm == corpus.entries[0].bpm
        finally:
            os.unlink(path)


# ─── BenchmarkRunner tests ────────────────────────────────────────────────────

class TestBenchmarkRunner:

    @pytest.fixture
    def corpus(self):
        return make_synthetic_corpus()

    @pytest.fixture
    def runner(self):
        return BenchmarkRunner(pipeline_mode="mock")

    def test_run_returns_report(self, runner, corpus):
        report = runner.run(corpus)
        assert isinstance(report, BenchmarkReport)
        assert report.total_songs == len(corpus.entries)
        assert report.successful_songs == len(corpus.entries)
        assert report.failed_songs == 0

    def test_all_songs_succeed_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        for song in report.songs:
            assert song.error is None, f"Song {song.song_id} failed: {song.error}"

    def test_beat_fmeasure_high_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        f_measure = report.agg_beat_fmeasure.get("f_measure", 0.0)
        assert f_measure > 0.8, f"Beat F-measure too low: {f_measure}"

    def test_tempo_accuracy_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        tempo_err = report.agg_tempo_accuracy.get("relative_error", 1.0)
        assert tempo_err < 0.10, f"Tempo error too high: {tempo_err}"

    def test_key_accuracy_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        assert report.agg_key_exact_rate > 0.8

    def test_chord_overlap_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        majmin_acc = report.agg_chord_majmin.get("accuracy", 0.0)
        assert majmin_acc > 0.7, f"Chord majmin accuracy too low: {majmin_acc}"

    def test_structure_boundary_in_mock_mode(self, runner, corpus):
        report = runner.run(corpus)
        f_measure = report.agg_structure_boundary.get("f_measure", 0.0)
        assert f_measure > 0.7

    def test_report_save_json(self, runner, corpus):
        report = runner.run(corpus)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            report.save_json(path)
            with open(path, "r") as f:
                data = json.load(f)
            assert data["corpus_name"] == corpus.name
            assert data["successful_songs"] == len(corpus.entries)
            assert "songs" in data
            assert "agg_beat_fmeasure" in data
        finally:
            os.unlink(path)

    def test_report_print_summary(self, runner, corpus, capsys):
        report = runner.run(corpus)
        report.print_summary()
        captured = capsys.readouterr()
        assert "BENCHMARK REPORT" in captured.out
        assert "Beat F-measure" in captured.out
        assert "Chord" in captured.out

    def test_song_results_have_metadata(self, runner, corpus):
        report = runner.run(corpus)
        for song in report.songs:
            assert song.song_id in [e.id for e in corpus.entries]
            assert song.elapsed_sec >= 0
            assert song.est_bpm is not None and song.est_bpm > 0
            assert song.est_key is not None

    def test_real_mode_fails_for_synthetic_audio(self, corpus):
        runner = BenchmarkRunner(pipeline_mode="real")
        report = runner.run(corpus)
        for song in report.songs:
            assert song.error is not None, \
                "Real mode should fail for __synthetic__ audio paths"


# ─── HTML report tests ────────────────────────────────────────────────────────

class TestReportGeneration:

    def test_render_html(self):
        from benchmark.report import render_html
        corpus = make_synthetic_corpus()
        runner = BenchmarkRunner(pipeline_mode="mock")
        report = runner.run(corpus)
        html = render_html(report)
        assert "<!DOCTYPE html>" in html
        assert "Benchmark Report" in html
        assert "Beat F-measure" in html
        assert corpus.name in html
        assert all(e.id in html for e in corpus.entries)


# ─── CLI tests ────────────────────────────────────────────────────────────────

class TestBenchmarkCLI:

    def _run_cli(self, argv):
        """Run CLI, tolerate SystemExit(0) as success, re-raise SystemExit(non-0)."""
        from benchmark.cli import main
        try:
            main(argv)
        except SystemExit as e:
            if e.code != 0:
                raise

    def test_cli_synthetic_mode(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            self._run_cli(["--synthetic", "--output", out_path, "--mode", "mock"])
            with open(out_path) as f:
                data = json.load(f)
            assert data["successful_songs"] > 0
        finally:
            os.unlink(out_path)

    def test_cli_fail_condition_pass(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            self._run_cli(["--synthetic", "--output", out_path,
                           "--fail-if", "beat_fmeasure<0.5"])
        finally:
            os.unlink(out_path)

    def test_cli_fail_condition_fail(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            with pytest.raises(SystemExit) as exc:
                from benchmark.cli import main
                main(["--synthetic", "--output", out_path,
                      "--fail-if", "success_rate<1.1"])
            assert exc.value.code == 1
        finally:
            os.unlink(out_path)

    def test_cli_html_output(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as jf:
            json_path = jf.name
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as hf:
            html_path = hf.name
        try:
            self._run_cli(["--synthetic", "--output", json_path, "--html", html_path])
            assert os.path.exists(html_path)
            with open(html_path) as f:
                html = f.read()
            assert "<!DOCTYPE html>" in html
        finally:
            os.unlink(json_path)
            if os.path.exists(html_path):
                os.unlink(html_path)
