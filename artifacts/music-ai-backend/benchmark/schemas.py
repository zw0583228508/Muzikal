"""
Ground-truth schemas for the Muzikal benchmark corpus.

A corpus is a list of GroundTruthEntry objects, each representing one annotated song.
Ground-truth files are JSON with the schema defined here.

Example corpus entry:
{
  "id": "bossa_nova_01",
  "audio_path": "/data/corpus/bossa_nova_01.mp3",
  "bpm": 130.0,
  "time_signature": "4/4",
  "key": "C",
  "mode": "major",
  "beats": [0.0, 0.46, 0.92, 1.38, ...],
  "downbeats": [0.0, 1.84, 3.68, ...],
  "chords": [
    {"start": 0.0, "end": 4.0, "chord": "Cmaj7"},
    {"start": 4.0, "end": 8.0, "chord": "A7"},
    ...
  ],
  "structure": [
    {"label": "intro",  "start": 0.0,  "end": 8.0},
    {"label": "verse",  "start": 8.0,  "end": 24.0},
    {"label": "chorus", "start": 24.0, "end": 40.0},
    ...
  ],
  "total_duration": 180.0,
  "notes": "Clean studio recording, constant tempo, clear harmony"
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class ChordEntry:
    start: float
    end: float
    chord: str

    @classmethod
    def from_dict(cls, d: dict) -> "ChordEntry":
        return cls(start=float(d["start"]), end=float(d["end"]), chord=str(d["chord"]))


@dataclass
class SectionEntry:
    label: str
    start: float
    end: float

    @classmethod
    def from_dict(cls, d: dict) -> "SectionEntry":
        return cls(label=str(d["label"]), start=float(d["start"]), end=float(d["end"]))


@dataclass
class GroundTruthEntry:
    id: str
    audio_path: str
    bpm: float
    key: str
    mode: str
    total_duration: float
    time_signature: str = "4/4"
    beats: List[float] = field(default_factory=list)
    downbeats: List[float] = field(default_factory=list)
    chords: List[ChordEntry] = field(default_factory=list)
    structure: List[SectionEntry] = field(default_factory=list)
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "GroundTruthEntry":
        return cls(
            id=str(d["id"]),
            audio_path=str(d["audio_path"]),
            bpm=float(d["bpm"]),
            key=str(d["key"]),
            mode=str(d["mode"]),
            total_duration=float(d["total_duration"]),
            time_signature=str(d.get("time_signature", "4/4")),
            beats=[float(b) for b in d.get("beats", [])],
            downbeats=[float(b) for b in d.get("downbeats", [])],
            chords=[ChordEntry.from_dict(c) for c in d.get("chords", [])],
            structure=[SectionEntry.from_dict(s) for s in d.get("structure", [])],
            notes=str(d.get("notes", "")),
            tags=list(d.get("tags", [])),
        )


@dataclass
class BenchmarkCorpus:
    name: str
    version: str
    entries: List[GroundTruthEntry]
    description: str = ""

    @classmethod
    def from_json(cls, path: str) -> "BenchmarkCorpus":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = [GroundTruthEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            name=str(data.get("name", "unnamed")),
            version=str(data.get("version", "1.0")),
            entries=entries,
            description=str(data.get("description", "")),
        )

    def to_json(self, path: str) -> None:
        import dataclasses
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(self), f, indent=2, ensure_ascii=False)


def make_synthetic_corpus() -> BenchmarkCorpus:
    """
    Create a minimal synthetic corpus for unit testing (no audio files required).
    Uses synthetic ground-truth data only.
    """
    entries = [
        GroundTruthEntry(
            id="synth_pop_01",
            audio_path="__synthetic__",
            bpm=120.0,
            key="C",
            mode="major",
            total_duration=120.0,
            time_signature="4/4",
            beats=[i * 0.5 for i in range(240)],
            downbeats=[i * 2.0 for i in range(60)],
            chords=[
                ChordEntry(start=i * 4.0, end=(i + 1) * 4.0, chord=c)
                for i, c in enumerate(["Cmaj", "Amin", "Fmaj", "Gmaj"] * 7)
            ],
            structure=[
                SectionEntry("intro", 0.0, 8.0),
                SectionEntry("verse", 8.0, 32.0),
                SectionEntry("chorus", 32.0, 56.0),
                SectionEntry("verse", 56.0, 80.0),
                SectionEntry("chorus", 80.0, 104.0),
                SectionEntry("outro", 104.0, 120.0),
            ],
            tags=["pop", "synthetic", "unit_test"],
        ),
        GroundTruthEntry(
            id="synth_jazz_01",
            audio_path="__synthetic__",
            bpm=95.0,
            key="F",
            mode="major",
            total_duration=90.0,
            time_signature="4/4",
            beats=[i * (60.0 / 95.0) for i in range(144)],
            downbeats=[i * (240.0 / 95.0) for i in range(36)],
            chords=[
                ChordEntry(start=i * 4.0, end=(i + 1) * 4.0, chord=c)
                for i, c in enumerate(["Fmaj7", "Dmin7", "Gmin7", "C7"] * 5)
            ],
            structure=[
                SectionEntry("intro", 0.0, 8.0),
                SectionEntry("head", 8.0, 40.0),
                SectionEntry("solo", 40.0, 72.0),
                SectionEntry("outro", 72.0, 90.0),
            ],
            tags=["jazz", "synthetic", "unit_test"],
        ),
    ]
    return BenchmarkCorpus(
        name="Synthetic Unit Test Corpus",
        version="1.0",
        entries=entries,
        description="Synthetic ground-truth entries for CI/regression testing — no audio files required.",
    )
