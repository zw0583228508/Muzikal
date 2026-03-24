"""
Muzikal Benchmark Framework — Phase 3 Evaluation Infrastructure.

Provides tools for:
  - Running MIR analysis against annotated ground-truth corpora
  - Computing industry-standard metrics (beat, chord, key, structure)
  - Generating JSON + HTML regression reports
  - CLI access for CI/CD integration

Usage:
    python -m benchmark.cli --corpus path/to/corpus.json --output report.json
"""

__version__ = "1.0.0"
