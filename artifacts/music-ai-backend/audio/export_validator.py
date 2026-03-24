"""
Export Artifact Validator — Phase 5.

Validates exported audio, MIDI, and MusicXML files for integrity,
loudness compliance, and format correctness.

Checks:
  - Audio: file exists, non-zero size, readable, duration correct, LUFS within range
  - MIDI: valid MIDI file, tracks > 0, tempo set, not empty
  - MusicXML: valid XML, proper root element, measure content present
  - General: checksums, file size sanity

Usage:
    from audio.export_validator import validate_export
    result = validate_export("/tmp/export.wav", kind="audio", expected_duration=60.0)
    if not result.ok:
        for issue in result.issues:
            print(issue)
"""

from __future__ import annotations

import hashlib
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    path: str
    kind: str           # "audio", "midi", "musicxml", "zip"
    ok: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        n = len(self.issues)
        return (
            f"[{status}] {os.path.basename(self.path)}"
            + (f" — {n} issue(s): {self.issues[0]}" if n else "")
        )


# ─── Audio validation ─────────────────────────────────────────────────────────

def validate_audio(
    path: str,
    expected_duration_sec: Optional[float] = None,
    max_duration_tolerance_sec: float = 3.0,
    check_loudness: bool = True,
    min_lufs: float = -40.0,
    max_lufs: float = -3.0,
) -> ValidationResult:
    """
    Validate an audio export file (WAV / FLAC / MP3).

    Checks:
    - File exists and is non-empty
    - Readable by soundfile or ffprobe
    - Sample rate is standard (22050, 44100, 48000, 88200, 96000)
    - Duration matches expected (if provided)
    - Loudness is within expected bounds
    - No silent output
    - No clipping (peak <= 0 dBFS)
    """
    issues = []
    warnings = []
    meta: Dict[str, Any] = {}

    if not os.path.exists(path):
        return ValidationResult(path=path, kind="audio", ok=False,
                                issues=[f"File not found: {path}"])

    size = os.path.getsize(path)
    meta["size_bytes"] = size
    if size == 0:
        return ValidationResult(path=path, kind="audio", ok=False,
                                issues=["File is empty (0 bytes)"])
    if size < 1000:
        warnings.append(f"File is suspiciously small: {size} bytes")

    # Try reading with soundfile
    try:
        import soundfile as sf
        import numpy as np

        info = sf.info(path)
        meta["samplerate"] = info.samplerate
        meta["channels"] = info.channels
        meta["duration_sec"] = info.duration
        meta["format"] = info.format
        meta["subtype"] = info.subtype

        standard_srs = {22050, 44100, 48000, 88200, 96000}
        if info.samplerate not in standard_srs:
            warnings.append(f"Non-standard sample rate: {info.samplerate} Hz")

        if expected_duration_sec is not None:
            diff = abs(info.duration - expected_duration_sec)
            if diff > max_duration_tolerance_sec:
                issues.append(
                    f"Duration mismatch: expected {expected_duration_sec:.1f}s, "
                    f"got {info.duration:.1f}s (diff {diff:.1f}s)"
                )

        if info.duration < 0.5:
            issues.append(f"File is too short: {info.duration:.2f}s")

        # Read audio for loudness + peak check
        if check_loudness and info.duration < 600:  # skip for very long files
            audio, sr = sf.read(path, dtype="float32")
            if audio.ndim == 1:
                audio = audio[:, None]

            peak = float(np.max(np.abs(audio)))
            meta["peak_linear"] = round(peak, 6)

            if peak == 0.0:
                issues.append("Audio is completely silent (all zeros)")
            elif peak > 0.9995:
                warnings.append(f"Audio is clipping: peak={peak:.5f} (> 0.9995)")

            try:
                from audio.loudness_normalizer import measure_loudness
                lm = measure_loudness(audio, sr)
                meta["lufs"] = lm.lufs
                meta["true_peak_dbtp"] = lm.true_peak_dbtp

                if lm.lufs < min_lufs and not lm.is_silent:
                    warnings.append(
                        f"Audio may be too quiet: {lm.lufs:.1f} LUFS "
                        f"(expected ≥ {min_lufs:.0f} LUFS)"
                    )
                if lm.lufs > max_lufs:
                    warnings.append(
                        f"Audio may be too loud: {lm.lufs:.1f} LUFS "
                        f"(expected ≤ {max_lufs:.0f} LUFS)"
                    )
            except Exception as lm_err:
                warnings.append(f"Loudness measurement unavailable: {lm_err}")

    except Exception as exc:
        issues.append(f"Cannot read audio file: {exc}")

    ok = len(issues) == 0
    return ValidationResult(path=path, kind="audio", ok=ok,
                            issues=issues, warnings=warnings, metadata=meta)


# ─── MIDI validation ──────────────────────────────────────────────────────────

def validate_midi(
    path: str,
    min_tracks: int = 1,
    require_tempo: bool = True,
) -> ValidationResult:
    """
    Validate a MIDI export file.

    Checks:
    - File exists and is non-empty
    - Valid MIDI header (MThd)
    - At least min_tracks instrument tracks
    - Tempo message present
    - At least one note event
    """
    issues = []
    warnings = []
    meta: Dict[str, Any] = {}

    if not os.path.exists(path):
        return ValidationResult(path=path, kind="midi", ok=False,
                                issues=[f"File not found: {path}"])

    size = os.path.getsize(path)
    meta["size_bytes"] = size
    if size < 14:  # MThd header is 14 bytes minimum
        return ValidationResult(path=path, kind="midi", ok=False,
                                issues=[f"File too small to be valid MIDI: {size} bytes"])

    # Check MIDI header magic
    with open(path, "rb") as f:
        header = f.read(4)
    if header != b"MThd":
        issues.append(f"Invalid MIDI header: {header!r} (expected b'MThd')")

    try:
        import mido  # type: ignore
        mid = mido.MidiFile(path)
        meta["midi_type"] = mid.type
        meta["ticks_per_beat"] = mid.ticks_per_beat
        meta["track_count"] = len(mid.tracks)

        # Count instrument tracks (non-empty)
        instrument_tracks = sum(
            1 for t in mid.tracks
            if any(msg.type in ("note_on", "note_off") for msg in t)
        )
        meta["instrument_tracks"] = instrument_tracks

        if instrument_tracks < min_tracks:
            issues.append(
                f"Too few instrument tracks: {instrument_tracks} "
                f"(expected ≥ {min_tracks})"
            )

        # Check for tempo
        has_tempo = any(
            msg.type == "set_tempo"
            for t in mid.tracks
            for msg in t
        )
        meta["has_tempo"] = has_tempo
        if require_tempo and not has_tempo:
            warnings.append("No tempo message found (will play at 120 BPM default)")

        # Check for note events
        total_notes = sum(
            1 for t in mid.tracks for msg in t
            if msg.type == "note_on" and msg.velocity > 0
        )
        meta["total_notes"] = total_notes
        if total_notes == 0:
            issues.append("MIDI file has no note events")
        elif total_notes < 4:
            warnings.append(f"MIDI file has very few notes: {total_notes}")

    except ImportError:
        warnings.append("mido not available — limited MIDI validation")
    except Exception as exc:
        issues.append(f"Cannot parse MIDI: {exc}")

    ok = len(issues) == 0
    return ValidationResult(path=path, kind="midi", ok=ok,
                            issues=issues, warnings=warnings, metadata=meta)


# ─── MusicXML validation ──────────────────────────────────────────────────────

def validate_musicxml(path: str) -> ValidationResult:
    """
    Validate a MusicXML export file.

    Checks:
    - File exists and is non-empty
    - Valid XML
    - Root element is <score-partwise> or <score-timewise>
    - At least one measure with notes
    - Chord symbols present
    """
    issues = []
    warnings = []
    meta: Dict[str, Any] = {}

    if not os.path.exists(path):
        return ValidationResult(path=path, kind="musicxml", ok=False,
                                issues=[f"File not found: {path}"])

    size = os.path.getsize(path)
    meta["size_bytes"] = size
    if size == 0:
        return ValidationResult(path=path, kind="musicxml", ok=False,
                                issues=["File is empty"])

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as exc:
        return ValidationResult(path=path, kind="musicxml", ok=False,
                                issues=[f"Invalid XML: {exc}"])

    # Check root element
    tag = root.tag
    if "}" in tag:
        tag = tag.split("}")[1]
    meta["root_element"] = tag

    valid_roots = {"score-partwise", "score-timewise"}
    if tag not in valid_roots:
        issues.append(f"Invalid root element: <{tag}> (expected score-partwise or score-timewise)")

    # Count measures and notes
    measures = root.findall(".//{http://www.musicxml.org/dtd/MusicXML}measure") or \
               root.findall(".//measure")
    meta["measure_count"] = len(measures)

    notes = root.findall(".//{http://www.musicxml.org/dtd/MusicXML}note") or \
            root.findall(".//note")
    meta["note_count"] = len(notes)

    if len(measures) == 0:
        issues.append("No measures found in MusicXML")
    elif len(measures) < 2:
        warnings.append(f"Only {len(measures)} measure(s) found")

    if len(notes) == 0:
        issues.append("No notes found in MusicXML")

    # Check for chord symbols
    harmonies = root.findall(".//{http://www.musicxml.org/dtd/MusicXML}harmony") or \
                root.findall(".//harmony")
    meta["harmony_count"] = len(harmonies)
    if len(harmonies) == 0:
        warnings.append("No chord symbols in MusicXML")

    ok = len(issues) == 0
    return ValidationResult(path=path, kind="musicxml", ok=ok,
                            issues=issues, warnings=warnings, metadata=meta)


# ─── Generic dispatch ─────────────────────────────────────────────────────────

def validate_export(
    path: str,
    kind: Optional[str] = None,
    expected_duration_sec: Optional[float] = None,
    **kwargs,
) -> ValidationResult:
    """
    Validate an exported artifact by path and optional kind hint.

    Auto-detects kind from file extension if not specified.

    Args:
        path:                 Path to the artifact
        kind:                 "audio", "midi", "musicxml", "zip" (auto-detected if None)
        expected_duration_sec: Expected duration for audio validation
        **kwargs:             Passed to the specific validator

    Returns:
        ValidationResult
    """
    if kind is None:
        ext = os.path.splitext(path)[1].lower()
        kind_map = {
            ".wav": "audio", ".flac": "audio", ".mp3": "audio", ".aif": "audio",
            ".mid": "midi", ".midi": "midi",
            ".musicxml": "musicxml", ".xml": "musicxml", ".mxl": "musicxml",
            ".zip": "zip",
        }
        kind = kind_map.get(ext, "audio")

    if kind == "audio":
        return validate_audio(path, expected_duration_sec=expected_duration_sec, **kwargs)
    elif kind == "midi":
        return validate_midi(path, **kwargs)
    elif kind == "musicxml":
        return validate_musicxml(path)
    elif kind == "zip":
        return _validate_zip(path)
    else:
        return ValidationResult(
            path=path, kind=kind, ok=False,
            issues=[f"Unknown artifact kind: {kind}"]
        )


def _validate_zip(path: str) -> ValidationResult:
    """Basic ZIP bundle validation."""
    import zipfile
    issues = []
    meta: Dict[str, Any] = {}

    if not os.path.exists(path):
        return ValidationResult(path=path, kind="zip", ok=False,
                                issues=["File not found"])

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            meta["file_count"] = len(names)
            meta["files"] = names[:20]

            if len(names) == 0:
                issues.append("ZIP is empty")

            # Check for common expected files
            has_midi = any(n.endswith((".mid", ".midi")) for n in names)
            has_audio = any(n.endswith((".wav", ".flac", ".mp3")) for n in names)
            if not has_midi and not has_audio:
                issues.append("ZIP contains neither MIDI nor audio files")

    except zipfile.BadZipFile:
        issues.append("Not a valid ZIP file")
    except Exception as exc:
        issues.append(f"Cannot open ZIP: {exc}")

    return ValidationResult(
        path=path, kind="zip", ok=len(issues) == 0,
        issues=issues, metadata=meta,
    )


def compute_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
