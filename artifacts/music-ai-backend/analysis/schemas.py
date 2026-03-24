"""
Pydantic v2 schemas for all analysis outputs.
Every analyzer returns a dataclass or dict that conforms to these schemas.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ─── Audio Metadata ────────────────────────────────────────────────────────────

class AudioMeta(BaseModel):
    duration: float
    sample_rate: int
    channels: int
    rms: float
    loudness_lufs: Optional[float] = None
    file_path: str
    file_hash: Optional[str] = None


# ─── Stems ─────────────────────────────────────────────────────────────────────

class StemInfo(BaseModel):
    path: Optional[str] = None
    energy_ratio: float = 0.0
    confidence: float = 0.0
    available: bool = False


class StemsResult(BaseModel):
    vocals: StemInfo = Field(default_factory=StemInfo)
    drums: StemInfo = Field(default_factory=StemInfo)
    bass: StemInfo = Field(default_factory=StemInfo)
    other: StemInfo = Field(default_factory=StemInfo)
    separation_mode: str = "degraded"
    separation_confidence: float = 0.0


# ─── Tempo / Beat ──────────────────────────────────────────────────────────────

class TempoResult(BaseModel):
    bpm_global: float
    bpm_curve: List[Dict[str, float]] = Field(default_factory=list)
    beats: List[float] = Field(default_factory=list)
    downbeats: List[float] = Field(default_factory=list)
    meter: str = "4/4"
    meter_numerator: int = 4
    meter_denominator: int = 4
    confidence: float = 0.0
    source: str = "librosa"
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)


# ─── Key / Scale ───────────────────────────────────────────────────────────────

class KeySegment(BaseModel):
    start: float
    end: float
    key: str
    mode: str
    confidence: float


class KeyResult(BaseModel):
    global_key: str
    global_mode: str
    global_confidence: float
    segments: List[KeySegment] = Field(default_factory=list)
    modulations: List[Dict[str, Any]] = Field(default_factory=list)
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    source: str = "librosa"


# ─── Chords ────────────────────────────────────────────────────────────────────

class ChordEvent(BaseModel):
    start: float
    end: float
    chord: str
    root: str
    quality: str
    confidence: float
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    # Harmonic function in current key (tonic / subdominant / dominant / secondary / chromatic)
    harmonic_function: Optional[str] = None
    # Scale degree of chord root (1–7, or None if chromatic)
    scale_degree: Optional[int] = None


class CadenceEvent(BaseModel):
    kind: str        # "authentic" | "half" | "plagal" | "deceptive" | "evaded"
    start: float
    end: float
    chords: List[str]
    strength: float  # 0–1


class ChordsResult(BaseModel):
    timeline: List[ChordEvent] = Field(default_factory=list)
    global_confidence: float = 0.0
    unique_chords: List[str] = Field(default_factory=list)
    source: str = "chroma_template"
    # Key-aware harmonic analysis (populated by chord_classifier)
    cadences: List[CadenceEvent] = Field(default_factory=list)
    harmonic_rhythm: float = 0.0     # Mean chord duration in beats
    diatonic_ratio: float = 0.0      # Fraction of chords that are diatonic


# ─── Melody ────────────────────────────────────────────────────────────────────

class NoteEvent(BaseModel):
    pitch: int
    pitch_name: str
    start: float
    end: float
    duration: float
    velocity: int
    confidence: float


class MelodyResult(BaseModel):
    pitch_curve: List[Dict[str, float]] = Field(default_factory=list)
    notes: List[NoteEvent] = Field(default_factory=list)
    global_confidence: float = 0.0
    voiced_fraction: float = 0.0
    mean_pitch_hz: float = 0.0
    source: str = "pyin"


# ─── Structure ─────────────────────────────────────────────────────────────────

class Section(BaseModel):
    label: str
    start: float
    end: float
    duration: float
    confidence: float
    repeated: bool = False
    repeat_of: Optional[str] = None
    # Energy/density profile
    energy: float = 0.0              # RMS energy (normalized 0–1)
    density: float = 0.0             # Onset density events/sec
    spectral_centroid: float = 0.0   # Mean spectral centroid (Hz)
    # Similarity grouping (sections with same group_id are structurally similar)
    group_id: Optional[int] = None


class StructureResult(BaseModel):
    sections: List[Section] = Field(default_factory=list)
    num_sections: int = 0
    confidence: float = 0.0
    source: str = "ssm_novelty"
    # Section-level grouping statistics
    num_groups: int = 0


# ─── Full Analysis Result ──────────────────────────────────────────────────────

class AnalysisWarning(BaseModel):
    code: str
    message: str
    severity: str = "info"


class AnalysisResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    audio_meta: AudioMeta
    stems: StemsResult = Field(default_factory=StemsResult)
    tempo: Optional[TempoResult] = None
    key: Optional[KeyResult] = None
    chords: Optional[ChordsResult] = None
    melody: Optional[MelodyResult] = None
    structure: Optional[StructureResult] = None
    global_confidence: float = 0.0
    mode: str = "balanced"
    pipeline_version: str = "2.0.0"
    warnings: List[AnalysisWarning] = Field(default_factory=list)
    # Quality flags — machine-readable issues detected during analysis
    quality_flags: List[str] = Field(default_factory=list)
    # Which model versions were used for each stage
    model_versions: Dict[str, str] = Field(default_factory=dict)
    # Canonical Score (CanonicalScore dataclass — set by pipeline Stage 12)
    canonical: Optional[Any] = Field(default=None, exclude=True)

    def to_legacy_format(self) -> dict:
        """Convert to the legacy format expected by existing API routes."""
        result: dict = {}

        if self.tempo:
            result["rhythm"] = {
                "bpm": self.tempo.bpm_global,
                "beats": self.tempo.beats,
                "downbeats": self.tempo.downbeats,
                "timeSignature": {
                    "numerator": self.tempo.meter_numerator,
                    "denominator": self.tempo.meter_denominator,
                },
                "confidence": self.tempo.confidence,
                "bpmCurve": self.tempo.bpm_curve,
            }

        if self.key:
            result["key"] = {
                "key": self.key.global_key,
                "mode": self.key.global_mode,
                "confidence": self.key.global_confidence,
                "alternatives": self.key.alternatives,
                "modulations": self.key.modulations,
                "segments": [s.model_dump() for s in self.key.segments],
            }

        if self.chords:
            result["chords"] = {
                "timeline": [c.model_dump() for c in self.chords.timeline],
                "confidence": self.chords.global_confidence,
                "uniqueChords": self.chords.unique_chords,
            }

        if self.melody:
            result["melody"] = {
                "notes": [n.model_dump() for n in self.melody.notes],
                "pitchCurve": self.melody.pitch_curve,
                "confidence": self.melody.global_confidence,
                "voicedFraction": self.melody.voiced_fraction,
            }

        if self.structure:
            result["structure"] = {
                "sections": [s.model_dump() for s in self.structure.sections],
                "confidence": self.structure.confidence,
            }

        result["stems"] = self.stems.model_dump()
        result["globalConfidence"] = self.global_confidence
        result["pipelineVersion"] = self.pipeline_version
        result["warnings"] = [w.model_dump() for w in self.warnings]
        result["qualityFlags"] = self.quality_flags
        result["isMock"] = False
        result["modelVersions"] = self.model_versions or {
            "demucs":     "4.0.1",
            "madmom":     "0.16.1",
            "essentia":   "2.1b6",
            "torchcrepe": "0.0.24",
            "basicPitch": "0.4.0",
            "librosa":    "0.11.0",
        }

        if self.canonical is not None:
            result["canonical"] = self.canonical.to_dict()

        if self.chords and self.chords.cadences:
            result["cadences"] = [c.model_dump() for c in self.chords.cadences]
            result["harmonicRhythm"] = self.chords.harmonic_rhythm
            result["diatonicRatio"]  = self.chords.diatonic_ratio

        return result
