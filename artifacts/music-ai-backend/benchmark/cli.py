"""
Benchmark CLI — Muzikal Phase 3 Evaluation.

Usage:
    # Run against synthetic corpus (no audio needed — for CI):
    python -m benchmark.cli --synthetic --output /tmp/benchmark_report.json

    # Run against a real corpus JSON:
    python -m benchmark.cli --corpus /path/to/corpus.json --output /tmp/report.json --mode real

    # Run and generate HTML report:
    python -m benchmark.cli --synthetic --output /tmp/report.json --html /tmp/report.html

    # Fail CI if beat F-measure < threshold:
    python -m benchmark.cli --synthetic --fail-if beat_fmeasure<0.7
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("benchmark.cli")


def _parse_threshold(s: str):
    """Parse 'metric<value' or 'metric>value' into (metric, op, value)."""
    for op in ("<", ">", "<=", ">="):
        if op in s:
            parts = s.split(op, 1)
            return parts[0].strip(), op, float(parts[1].strip())
    raise ValueError(f"Cannot parse threshold: {s!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Muzikal MIR Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--corpus", help="Path to corpus JSON file")
    parser.add_argument("--synthetic", action="store_true",
                        help="Use built-in synthetic corpus (no audio required)")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock",
                        help="Pipeline mode: mock (no audio) or real (runs analysis)")
    parser.add_argument("--output", required=True, help="Output JSON report path")
    parser.add_argument("--html", help="Optional HTML report output path")
    parser.add_argument("--fail-if", dest="fail_conditions", nargs="*", default=[],
                        metavar="CONDITION",
                        help="Exit 1 if metric violates condition (e.g. beat_fmeasure<0.7)")
    args = parser.parse_args(argv)

    from benchmark.runner import BenchmarkRunner
    from benchmark.schemas import BenchmarkCorpus, make_synthetic_corpus

    if args.synthetic:
        corpus = make_synthetic_corpus()
        logger.info("Using synthetic corpus (%d entries)", len(corpus.entries))
    elif args.corpus:
        corpus = BenchmarkCorpus.from_json(args.corpus)
        logger.info("Loaded corpus '%s' (%d entries)", corpus.name, len(corpus.entries))
    else:
        parser.error("Must specify --corpus or --synthetic")

    runner = BenchmarkRunner(pipeline_mode=args.mode)
    report = runner.run(corpus)
    report.print_summary()

    report.save_json(args.output)
    logger.info("JSON report saved: %s", args.output)

    if args.html:
        from benchmark.report import render_html
        html = render_html(report)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("HTML report saved: %s", args.html)

    # Evaluate fail conditions
    metric_map = {
        "beat_fmeasure":        report.agg_beat_fmeasure.get("f_measure", 0.0),
        "beat_precision":       report.agg_beat_fmeasure.get("precision", 0.0),
        "beat_recall":          report.agg_beat_fmeasure.get("recall", 0.0),
        "tempo_correct":        report.agg_tempo_accuracy.get("correct", 0.0),
        "key_exact":            report.agg_key_exact_rate,
        "key_relative":         report.agg_key_relative_rate,
        "chord_root":           report.agg_chord_root.get("accuracy", 0.0),
        "chord_majmin":         report.agg_chord_majmin.get("accuracy", 0.0),
        "chord_seventh":        report.agg_chord_seventh.get("accuracy", 0.0),
        "chord_mirex":          report.agg_chord_mirex.get("accuracy", 0.0),
        "harmonic_rhythm":      report.agg_harmonic_rhythm.get("f_measure", 0.0),
        "structure_boundary":   report.agg_structure_boundary.get("f_measure", 0.0),
        "success_rate":         report.successful_songs / max(report.total_songs, 1),
    }

    fail = False
    for cond in args.fail_conditions:
        metric, op, threshold = _parse_threshold(cond)
        val = metric_map.get(metric)
        if val is None:
            logger.warning("Unknown metric in fail-condition: %s", metric)
            continue

        violated = False
        if op == "<"  and val <  threshold: violated = True
        if op == "<=" and val <= threshold: violated = True
        if op == ">"  and val >  threshold: violated = True
        if op == ">=" and val >= threshold: violated = True

        if violated:
            logger.error("FAIL: %s=%.4f %s %.4f", metric, val, op, threshold)
            fail = True
        else:
            logger.info("PASS: %s=%.4f (threshold %s %.4f)", metric, val, op, threshold)

    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
