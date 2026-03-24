"""
Canonical Score Layer v1.0

Converts an AnalysisResult into a CanonicalScore — a structured, measure-by-measure
symbolic representation that is ready for:
  - MIDI export (via mido)
  - MusicXML export (via music21)
  - Arrangement planning
  - Visual piano-roll display

Key design decisions:
  - One CanonicalMeasure per bar (using detected meter and tempo)
  - Each measure holds: chord symbol, melody notes, beat grid timestamps
  - Notes are quantized to the nearest 16th-note grid
  - Pitch-class transposition preserved for key modulations
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CanonicalNote:
    """A single sounding note in MIDI terms."""
    pitch: int           # MIDI note number (21–108 typical)
    pitch_name: str      # e.g. "C4"
    onset: float         # seconds from start of piece
    duration: float      # seconds
    velocity: int        # 0–127
    confidence: float    # 0–1 from detector
    # Grid position inside its measure
    beat: int            # 1-based beat index within measure
    subbeat: int         # 1-based sixteenth-note index within beat (1–4)


@dataclass
class CanonicalChord:
    """Chord symbol for a time range."""
    symbol: str           # e.g. "Dm7"
    root: str             # "D"
    quality: str          # "min7"
    onset: float          # seconds
    duration: float       # seconds
    harmonic_function: Optional[str] = None   # "tonic" / "dominant" / …
    scale_degree: Optional[int]      = None   # 1–7
    cadence_role: Optional[str]      = None   # "V" / "I" / None


@dataclass
class CanonicalMeasure:
    """One complete bar."""
    index: int            # 0-based bar number
    onset: float          # absolute start time (seconds)
    duration: float       # bar duration (seconds)
    beats: int            # numerator of time signature (e.g. 4)
    beat_duration: float  # duration of one beat in seconds
    chord: Optional[CanonicalChord] = None
    notes: List[CanonicalNote]      = field(default_factory=list)
    section_label: Optional[str]    = None   # "verse", "chorus", …
    section_group: Optional[int]    = None   # group_id from structure


@dataclass
class CanonicalScore:
    """Complete symbolic representation of an analysed audio file."""
    # Metadata
    title: str            = "Untitled"
    bpm: float            = 120.0
    time_sig_num: int     = 4
    time_sig_den: int     = 4
    key: str              = "C"
    mode: str             = "major"
    duration_sec: float   = 0.0
    pipeline_version: str = "2.0.0"

    # Content
    measures: List[CanonicalMeasure] = field(default_factory=list)

    # Summary stats
    num_measures: int     = 0
    num_notes: int        = 0
    num_unique_chords: int= 0
    diatonic_ratio: float = 0.0

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON / API response."""
        return {
            "title":          self.title,
            "bpm":            self.bpm,
            "timeSignature":  f"{self.time_sig_num}/{self.time_sig_den}",
            "key":            self.key,
            "mode":           self.mode,
            "durationSec":    self.duration_sec,
            "numMeasures":    self.num_measures,
            "numNotes":       self.num_notes,
            "numUniqueChords":self.num_unique_chords,
            "diatonicRatio":  self.diatonic_ratio,
            "pipelineVersion":self.pipeline_version,
            "measures": [
                {
                    "index":        m.index,
                    "onset":        round(m.onset, 3),
                    "duration":     round(m.duration, 3),
                    "beats":        m.beats,
                    "sectionLabel": m.section_label,
                    "sectionGroup": m.section_group,
                    "chord": {
                        "symbol":           m.chord.symbol,
                        "root":             m.chord.root,
                        "quality":          m.chord.quality,
                        "onset":            round(m.chord.onset, 3),
                        "duration":         round(m.chord.duration, 3),
                        "harmonicFunction": m.chord.harmonic_function,
                        "scaleDegree":      m.chord.scale_degree,
                    } if m.chord else None,
                    "notes": [
                        {
                            "pitch":      n.pitch,
                            "pitchName":  n.pitch_name,
                            "onset":      round(n.onset, 4),
                            "duration":   round(n.duration, 4),
                            "velocity":   n.velocity,
                            "confidence": round(n.confidence, 3),
                            "beat":       n.beat,
                            "subbeat":    n.subbeat,
                        }
                        for n in m.notes
                    ],
                }
                for m in self.measures
            ],
        }


# ─── Conversion helpers ────────────────────────────────────────────────────────

def _section_for_time(t: float, sections) -> tuple[Optional[str], Optional[int]]:
    """Return (section_label, group_id) for a given timestamp."""
    if not sections:
        return None, None
    for s in sections:
        if s.start <= t < s.end:
            return s.label, s.group_id
    # After last section
    last = sections[-1]
    return last.label, last.group_id


def _beat_position(onset: float, measure_onset: float, beat_dur: float) -> tuple[int, int]:
    """
    Return (beat, subbeat) — both 1-based.
    Beat: 1…beats_per_bar
    Subbeat: 1…4 (16th-note grid within beat)
    """
    offset = onset - measure_onset
    beat_idx = int(offset / beat_dur)
    sub_offset = offset - beat_idx * beat_dur
    sub_idx = int(sub_offset / (beat_dur / 4.0))
    return beat_idx + 1, min(sub_idx + 1, 4)


def _chord_at_time(t: float, chord_timeline) -> Optional[CanonicalChord]:
    """Return the chord active at time t."""
    for ev in chord_timeline:
        if ev.start <= t < ev.end:
            return CanonicalChord(
                symbol=ev.chord,
                root=ev.root,
                quality=ev.quality,
                onset=ev.start,
                duration=ev.end - ev.start,
                harmonic_function=getattr(ev, "harmonic_function", None),
                scale_degree=getattr(ev, "scale_degree", None),
            )
    return None


# ─── Main entry point ─────────────────────────────────────────────────────────

def to_canonical(analysis_result) -> CanonicalScore:
    """
    Convert an AnalysisResult into a CanonicalScore.

    Args:
        analysis_result: analysis.schemas.AnalysisResult instance

    Returns:
        CanonicalScore with all measures, notes, and chords populated.
    """
    ar = analysis_result

    bpm          = ar.tempo.bpm_global      if ar.tempo     else 120.0
    num          = ar.tempo.meter_numerator  if ar.tempo     else 4
    den          = ar.tempo.meter_denominator if ar.tempo    else 4
    global_key   = ar.key.global_key         if ar.key       else "C"
    global_mode  = ar.key.global_mode        if ar.key       else "major"
    duration     = ar.audio_meta.duration

    beat_dur     = 60.0 / bpm               # seconds per beat
    bar_dur      = beat_dur * num           # seconds per measure
    n_measures   = max(1, math.ceil(duration / bar_dur))

    chord_timeline = ar.chords.timeline  if ar.chords  else []
    note_events    = ar.melody.notes     if ar.melody  else []
    sections       = ar.structure.sections if ar.structure else []

    # Map notes → list for fast lookup by time range
    # Group notes by onset time for assignment to measures
    note_list = sorted(note_events, key=lambda n: n.start)
    note_ptr = 0  # pointer into note_list

    measures: List[CanonicalMeasure] = []
    diatonic_count = 0
    chord_count    = 0
    unique_chords: set = set()

    for m_idx in range(n_measures):
        m_onset  = m_idx * bar_dur
        m_end    = min(m_onset + bar_dur, duration)
        if m_onset >= duration:
            break

        sec_label, sec_group = _section_for_time(m_onset, sections)
        chord = _chord_at_time(m_onset + bar_dur * 0.1, chord_timeline)

        # Collect melody notes that start in this measure
        m_notes: List[CanonicalNote] = []
        while note_ptr < len(note_list) and note_list[note_ptr].start < m_end:
            ne = note_list[note_ptr]
            if ne.start >= m_onset:
                beat, subbeat = _beat_position(ne.start, m_onset, beat_dur)
                m_notes.append(CanonicalNote(
                    pitch=ne.pitch,
                    pitch_name=ne.pitch_name,
                    onset=ne.start,
                    duration=ne.duration,
                    velocity=ne.velocity,
                    confidence=ne.confidence,
                    beat=max(1, min(beat, num)),
                    subbeat=max(1, min(subbeat, 4)),
                ))
            note_ptr += 1

        if chord:
            chord_count += 1
            unique_chords.add(chord.symbol)
            if chord.scale_degree is not None:
                diatonic_count += 1

        measures.append(CanonicalMeasure(
            index=m_idx,
            onset=round(m_onset, 4),
            duration=round(m_end - m_onset, 4),
            beats=num,
            beat_duration=round(beat_dur, 4),
            chord=chord,
            notes=m_notes,
            section_label=sec_label,
            section_group=sec_group,
        ))

    diatonic_ratio = round(diatonic_count / max(chord_count, 1), 3)
    total_notes    = sum(len(m.notes) for m in measures)

    score = CanonicalScore(
        bpm=round(bpm, 2),
        time_sig_num=num,
        time_sig_den=den,
        key=global_key,
        mode=global_mode,
        duration_sec=round(duration, 3),
        pipeline_version=ar.pipeline_version,
        measures=measures,
        num_measures=len(measures),
        num_notes=total_notes,
        num_unique_chords=len(unique_chords),
        diatonic_ratio=diatonic_ratio,
    )

    logger.info(
        "[canonical] %d measures, %d notes, %d unique chords, diatonic=%.0f%%",
        score.num_measures, score.num_notes, score.num_unique_chords,
        score.diatonic_ratio * 100,
    )
    return score
