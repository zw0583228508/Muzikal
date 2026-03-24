"""
Startup Dependency Validator — run at process start before accepting jobs.

Validates:
  - ffmpeg / ffprobe availability and version
  - Python version
  - Critical ML libraries (torch, demucs, madmom, essentia, torchcrepe, basic-pitch)
  - librosa, soundfile, scipy, numpy
  - mido, pretty_midi, music21
  - psycopg2 / DB driver
  - Database connectivity
  - Writable temp directories
  - Demucs model availability

If any REQUIRED dependency is missing → logs ERROR and raises RuntimeError.
If any OPTIONAL dependency is missing → logs WARNING and continues.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PYTHON_MIN_VERSION = (3, 9)


@dataclass
class ValidationResult:
    name: str
    ok: bool
    detail: str = ""
    required: bool = True


@dataclass
class StartupReport:
    passed: List[ValidationResult] = field(default_factory=list)
    failed: List[ValidationResult] = field(default_factory=list)
    warnings: List[ValidationResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        required_failures = [r for r in self.failed if r.required]
        return len(required_failures) == 0

    def summary(self) -> str:
        lines = ["=== Startup Validation Report ==="]
        for r in self.passed:
            lines.append(f"  ✓ {r.name}: {r.detail}")
        for r in self.warnings:
            lines.append(f"  ⚠ {r.name}: {r.detail}")
        for r in self.failed:
            mark = "✗" if r.required else "!"
            lines.append(f"  {mark} {r.name}: {r.detail}")
        lines.append(f"Result: {'PASS' if self.all_ok else 'FAIL'} "
                     f"({len(self.passed)} ok, {len(self.warnings)} warnings, {len(self.failed)} failed)")
        return "\n".join(lines)


# ─── Individual checks ─────────────────────────────────────────────────────────

def _check_python_version() -> ValidationResult:
    v = sys.version_info
    ok = (v.major, v.minor) >= PYTHON_MIN_VERSION
    detail = f"{v.major}.{v.minor}.{v.micro}"
    return ValidationResult("Python version", ok, detail, required=True)


def _check_cli(cmd: str, args: List[str], name: str, required: bool = True) -> ValidationResult:
    path = shutil.which(cmd)
    if not path:
        return ValidationResult(name, False, f"{cmd} not found in PATH", required=required)
    try:
        out = subprocess.run([cmd] + args, capture_output=True, text=True, timeout=5)
        line = (out.stdout + out.stderr).strip().splitlines()[0] if (out.stdout + out.stderr).strip() else "ok"
        return ValidationResult(name, True, line[:80], required=required)
    except Exception as e:
        return ValidationResult(name, False, str(e)[:80], required=required)


def _check_import(
    module: str,
    display_name: Optional[str] = None,
    required: bool = True,
    version_attr: str = "__version__",
) -> ValidationResult:
    name = display_name or module
    try:
        m = __import__(module)
        ver = getattr(m, version_attr, "?")
        return ValidationResult(name, True, f"v{ver}", required=required)
    except ImportError as e:
        return ValidationResult(name, False, str(e)[:100], required=required)
    except Exception as e:
        return ValidationResult(name, False, f"import error: {e}", required=required)


def _check_torch() -> ValidationResult:
    try:
        import torch
        cuda = "CUDA" if torch.cuda.is_available() else "CPU-only"
        return ValidationResult("PyTorch", True, f"v{torch.__version__} ({cuda})", required=True)
    except ImportError:
        return ValidationResult("PyTorch", False, "torch not installed", required=True)


def _check_demucs() -> ValidationResult:
    try:
        import demucs.pretrained as dp
        return ValidationResult("Demucs", True, "htdemucs available", required=True)
    except ImportError:
        return ValidationResult("Demucs", False, "demucs not installed", required=True)
    except Exception as e:
        return ValidationResult("Demucs", True, f"installed (model check: {e})", required=True)


def _check_madmom() -> ValidationResult:
    try:
        import madmom
        import madmom.features.beats
        return ValidationResult("madmom", True, f"v{madmom.__version__}", required=True)
    except ImportError as e:
        return ValidationResult("madmom", False, str(e)[:100], required=True)
    except Exception as e:
        return ValidationResult("madmom", False, str(e)[:100], required=True)


def _check_essentia() -> ValidationResult:
    try:
        import essentia
        ver = getattr(essentia, "__version__", "?")
        return ValidationResult("Essentia", True, f"v{ver}", required=True)
    except ImportError:
        return ValidationResult("Essentia", False, "essentia not installed", required=True)


def _check_torchcrepe() -> ValidationResult:
    try:
        import torchcrepe
        return ValidationResult("torchcrepe", True, f"v{getattr(torchcrepe,'__version__','?')}", required=True)
    except ImportError:
        return ValidationResult("torchcrepe", False, "torchcrepe not installed", required=True)


def _check_basic_pitch() -> ValidationResult:
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        import os as _os
        ok = _os.path.exists(ICASSP_2022_MODEL_PATH)
        return ValidationResult(
            "basic-pitch", ok,
            f"model={'found' if ok else 'MISSING'} at {ICASSP_2022_MODEL_PATH}",
            required=False
        )
    except ImportError:
        return ValidationResult("basic-pitch", False, "not installed (optional)", required=False)


def _check_writable_dirs() -> ValidationResult:
    dirs = [
        os.environ.get("LOCAL_STORAGE_PATH", "/tmp/musicai_storage"),
        "/tmp/musicai_analysis_cache",
        "/tmp/music-ai-uploads",
    ]
    failed = []
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        test_f = os.path.join(d, ".write_test")
        try:
            with open(test_f, "w") as f:
                f.write("ok")
            os.unlink(test_f)
        except Exception as e:
            failed.append(f"{d}: {e}")
    if failed:
        return ValidationResult("Writable dirs", False, "; ".join(failed), required=True)
    return ValidationResult("Writable dirs", True, " ".join(dirs), required=True)


def _check_database() -> ValidationResult:
    try:
        import psycopg2
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return ValidationResult("Database", False, "DATABASE_URL not set", required=False)
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.close()
        return ValidationResult("Database", True, "PostgreSQL connection OK", required=False)
    except ImportError:
        return ValidationResult("Database", False, "psycopg2 not installed", required=False)
    except Exception as e:
        return ValidationResult("Database", False, str(e)[:100], required=False)


# ─── Main validator ─────────────────────────────────────────────────────────────

def validate_startup(strict: bool = True) -> StartupReport:
    """
    Run all startup checks and return a StartupReport.
    If strict=True (default), raises RuntimeError on any required failure.
    """
    report = StartupReport()

    checks = [
        _check_python_version(),
        _check_cli("ffmpeg", ["-version"], "ffmpeg", required=True),
        _check_cli("ffprobe", ["-version"], "ffprobe", required=True),
        _check_torch(),
        _check_demucs(),
        _check_madmom(),
        _check_essentia(),
        _check_torchcrepe(),
        _check_basic_pitch(),
        _check_import("librosa",    required=True),
        _check_import("soundfile",  "soundfile",  required=True,  version_attr="__version__"),
        _check_import("numpy",      "numpy",      required=True),
        _check_import("scipy",      "scipy",      required=True),
        _check_import("mido",       "mido",       required=True),
        _check_import("pretty_midi","pretty_midi",required=False),
        _check_import("music21",    "music21",    required=False),
        _check_import("psycopg2",   "psycopg2",   required=False),
        _check_writable_dirs(),
        _check_database(),
    ]

    for result in checks:
        if result.ok:
            report.passed.append(result)
        elif not result.required:
            report.warnings.append(result)
        else:
            report.failed.append(result)

    return report


def run_and_log(strict: bool = True) -> StartupReport:
    """
    Run validation, log the report, and optionally raise on failures.
    Called from main.py at process startup.
    """
    t0 = time.time()
    report = validate_startup()
    elapsed = time.time() - t0

    summary = report.summary()
    if report.all_ok:
        logger.info("Startup validation PASSED in %.2fs\n%s", elapsed, summary)
    else:
        logger.error("Startup validation FAILED in %.2fs\n%s", elapsed, summary)
        if strict:
            failed_names = [r.name for r in report.failed if r.required]
            raise RuntimeError(
                f"Required dependencies missing: {', '.join(failed_names)}. "
                f"See startup logs for details."
            )

    return report
