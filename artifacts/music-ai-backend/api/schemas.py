"""Pydantic schemas for the Python backend API."""

from typing import Optional, List, Any
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    job_id: str
    project_id: int
    audio_file_path: str


class ArrangeRequest(BaseModel):
    job_id: str
    project_id: int
    style_id: str
    instruments: Optional[List[str]] = None
    density: float = 0.7
    humanize: bool = True
    tempo_factor: float = 1.0


class JobUpdate(BaseModel):
    job_id: str
    status: str
    progress: float
    current_step: str
    error_message: Optional[str] = None


class RhythmAnalysis(BaseModel):
    bpm: float
    time_signature_numerator: int
    time_signature_denominator: int
    beat_grid: List[float]
    downbeats: List[float]


class Modulation(BaseModel):
    time_seconds: float
    from_key: str
    to_key: str


class KeyAnalysis(BaseModel):
    global_key: str
    mode: str
    confidence: float
    modulations: List[Modulation] = []


class ChordEvent(BaseModel):
    start_time: float
    end_time: float
    chord: str
    roman_numeral: str
    confidence: float
    alternatives: List[str] = []


class ChordAnalysis(BaseModel):
    chords: List[ChordEvent]
    lead_sheet: str


class MelodyNote(BaseModel):
    start_time: float
    end_time: float
    pitch: int
    frequency: float
    velocity: int


class MelodyAnalysis(BaseModel):
    notes: List[MelodyNote]
    inferred_harmony: List[str] = []


class Section(BaseModel):
    label: str
    start_time: float
    end_time: float
    confidence: float


class StructureAnalysis(BaseModel):
    sections: List[Section]


class FullAnalysis(BaseModel):
    project_id: int
    rhythm: RhythmAnalysis
    key: KeyAnalysis
    chords: ChordAnalysis
    melody: MelodyAnalysis
    structure: StructureAnalysis
    waveform_data: List[float]


class ExportRequest(BaseModel):
    job_id: str
    project_id: int
    formats: List[str] = ["midi"]  # midi, musicxml, pdf, wav, flac, mp3, stems
    output_dir: Optional[str] = None


class RenderRequest(BaseModel):
    job_id: str
    project_id: int
    formats: List[str] = ["wav"]  # wav, flac, mp3, stems
    output_dir: Optional[str] = None
