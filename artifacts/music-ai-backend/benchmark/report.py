"""
Benchmark report generator — produces JSON and HTML reports.

Usage:
    from benchmark.report import render_html
    html = render_html(report)
    with open("report.html", "w") as f:
        f.write(html)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmark.runner import BenchmarkReport


def _pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.1%}"


def _flt(val: float | None, digits: int = 3) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}"


def render_html(report: "BenchmarkReport") -> str:
    songs_rows = ""
    for s in report.songs:
        status = "✅" if s.error is None else f"❌ {s.error[:60]}"
        bpm_err = _flt(
            s.tempo_accuracy.get("relative_error") if s.tempo_accuracy else None, 3
        )
        beat_f = _flt(
            s.beat_fmeasure.get("f_measure") if s.beat_fmeasure else None, 3
        )
        key_ok = "✓" if (s.key_accuracy or {}).get("exact_correct") else "✗"
        chord_mm = _flt(
            (s.chord_overlap_majmin or {}).get("accuracy"), 3
        )
        struct_f = _flt(
            (s.structure_boundary or {}).get("f_measure"), 3
        )
        est_bpm_str = f"{s.est_bpm:.1f}" if s.est_bpm else "—"
        songs_rows += f"""
        <tr>
            <td>{s.song_id}</td>
            <td>{status}</td>
            <td dir="ltr">{est_bpm_str}</td>
            <td>{bpm_err}</td>
            <td>{beat_f}</td>
            <td>{s.est_key or "—"} {s.est_mode or ""}</td>
            <td>{key_ok}</td>
            <td>{chord_mm}</td>
            <td>{struct_f}</td>
            <td>{s.elapsed_sec:.2f}s</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Muzikal Benchmark — {report.corpus_name}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0a10; color: #e0e0e0; padding: 2rem; }}
  h1, h2 {{ color: #7c6af7; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #333; padding: 0.4rem 0.7rem; text-align: right; font-size: 0.85rem; }}
  th {{ background: #1a1a2e; color: #7c6af7; }}
  tr:nth-child(even) {{ background: #12121c; }}
  .metric {{ display: inline-block; margin: 0.3rem; padding: 0.4rem 0.8rem;
             background: #1a1a2e; border-radius: 6px; border: 1px solid #333; }}
  .metric .val {{ font-size: 1.4rem; font-weight: bold; color: #7c6af7; }}
  .metric .lbl {{ font-size: 0.75rem; color: #888; }}
  .ok {{ color: #4caf50; }} .err {{ color: #f44336; }}
  pre {{ background: #12121c; border: 1px solid #333; border-radius: 4px; padding: 1rem;
         overflow-x: auto; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>Muzikal Benchmark Report</h1>
<p>
  <strong>Corpus:</strong> {report.corpus_name} v{report.corpus_version} &nbsp;|&nbsp;
  <strong>Pipeline:</strong> {report.pipeline_mode} ({report.pipeline_version}) &nbsp;|&nbsp;
  <strong>{report.successful_songs}/{report.total_songs}</strong> songs OK &nbsp;|&nbsp;
  {report.total_elapsed_sec:.1f}s total &nbsp;|&nbsp;
  {report.timestamp}
</p>

<h2>Summary Metrics</h2>
<div>
  <div class="metric">
    <div class="val">{_flt(report.agg_beat_fmeasure.get('f_measure'), 3)}</div>
    <div class="lbl">Beat F-measure</div>
  </div>
  <div class="metric">
    <div class="val">{_pct(report.agg_tempo_accuracy.get('correct'))}</div>
    <div class="lbl">Tempo Accuracy</div>
  </div>
  <div class="metric">
    <div class="val">{_pct(report.agg_key_exact_rate)}</div>
    <div class="lbl">Key Exact</div>
  </div>
  <div class="metric">
    <div class="val">{_flt(report.agg_chord_majmin.get('accuracy'), 3)}</div>
    <div class="lbl">Chord Maj/Min</div>
  </div>
  <div class="metric">
    <div class="val">{_flt(report.agg_chord_mirex.get('accuracy'), 3)}</div>
    <div class="lbl">Chord MIREX</div>
  </div>
  <div class="metric">
    <div class="val">{_flt(report.agg_harmonic_rhythm.get('f_measure'), 3)}</div>
    <div class="lbl">Harm. Rhythm F</div>
  </div>
  <div class="metric">
    <div class="val">{_flt(report.agg_structure_boundary.get('f_measure'), 3)}</div>
    <div class="lbl">Structure F</div>
  </div>
</div>

<h2>Per-Song Results</h2>
<table>
  <tr>
    <th>ID</th><th>Status</th><th>Est BPM</th><th>Tempo Err</th>
    <th>Beat F</th><th>Est Key</th><th>Key OK</th>
    <th>Chord Maj/Min</th><th>Structure F</th><th>Time</th>
  </tr>
  {songs_rows}
</table>

<h2>Raw JSON</h2>
<pre>{json.dumps(asdict(report), indent=2, default=str)[:8000]}...</pre>

</body>
</html>"""
    return html
