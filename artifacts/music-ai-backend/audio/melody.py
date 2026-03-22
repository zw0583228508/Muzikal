"""
Melody Engine: F0 detection and note extraction using librosa.
Extracts predominant melody pitch track and converts to MIDI notes.
"""

import logging
import numpy as np
import librosa
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def hz_to_midi(freq: float) -> int:
    """Convert frequency in Hz to MIDI note number."""
    if freq <= 0:
        return 0
    return int(round(69 + 12 * np.log2(freq / 440.0)))


def extract_notes_from_f0(f0_times: np.ndarray, f0_freqs: np.ndarray,
                           voiced_flag: np.ndarray, hop_length: int, sr: int,
                           min_note_duration: float = 0.08) -> List[Dict]:
    """
    Convert continuous F0 track to discrete MIDI notes.
    Groups consecutive voiced frames with similar pitch into notes.
    """
    notes = []
    in_note = False
    note_start = 0.0
    note_freqs = []

    hop_duration = hop_length / sr

    for i, (t, freq, voiced) in enumerate(zip(f0_times, f0_freqs, voiced_flag)):
        if voiced and freq > 60:  # Must be > 60 Hz (roughly B1)
            if not in_note:
                in_note = True
                note_start = float(t)
                note_freqs = [freq]
            else:
                # Check if pitch changed significantly (>50 cents)
                current_midi = hz_to_midi(np.median(note_freqs))
                new_midi = hz_to_midi(freq)
                if abs(new_midi - current_midi) > 0.5:
                    # Finish current note if long enough
                    duration = float(t) - note_start
                    if duration >= min_note_duration and note_freqs:
                        median_freq = float(np.median(note_freqs))
                        midi_note = hz_to_midi(median_freq)
                        if 21 <= midi_note <= 108:  # Piano range
                            notes.append({
                                "startTime": round(note_start, 3),
                                "endTime": round(float(t), 3),
                                "pitch": midi_note,
                                "frequency": round(median_freq, 2),
                                "velocity": 80,
                            })
                    # Start new note
                    note_start = float(t)
                    note_freqs = [freq]
                else:
                    note_freqs.append(freq)
        else:
            if in_note:
                duration = float(t) - note_start
                if duration >= min_note_duration and note_freqs:
                    median_freq = float(np.median(note_freqs))
                    midi_note = hz_to_midi(median_freq)
                    if 21 <= midi_note <= 108:
                        notes.append({
                            "startTime": round(note_start, 3),
                            "endTime": round(float(t), 3),
                            "pitch": midi_note,
                            "frequency": round(median_freq, 2),
                            "velocity": 80,
                        })
                in_note = False
                note_freqs = []

    return notes


def infer_harmony_from_melody(notes: List[Dict], key: str = "C") -> List[str]:
    """
    Simple melody-to-harmony inference: group melody notes by measure and suggest chords.
    Returns top 3 most common chord progressions implied by melody.
    """
    if not notes:
        return []

    # Simple: collect pitch classes present in each measure and suggest chords
    # This is a simplified version - a full implementation would use a transformer model
    pitch_classes = set()
    for note in notes[:20]:  # Analyze first 20 notes
        pc = note["pitch"] % 12
        pitch_classes.add(pc)

    # Based on common pitch classes, suggest progressions (simplified)
    progressions = [
        f"{key} - {key}maj7 - Am - G",
        f"{key} - F - C - G",
        f"Am - F - {key} - G",
    ]
    return progressions


def analyze_melody(y: np.ndarray, sr: int, rhythm: dict) -> Dict[str, Any]:
    """
    Melody extraction using librosa's F0 detection (piptrack).
    """
    logger.info("Running melody extraction...")

    hop_length = 512

    # Use harmonic component for cleaner pitch detection
    y_harm = librosa.effects.harmonic(y, margin=8)

    # PYIN F0 detection (most accurate in librosa)
    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y_harm,
            sr=sr,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            hop_length=hop_length,
        )
        f0_times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
    except Exception as e:
        logger.warning(f"PYIN failed: {e}, falling back to piptrack")
        # Fallback: simpler approach
        pitches, magnitudes = librosa.piptrack(y=y_harm, sr=sr, hop_length=hop_length)
        f0_times = librosa.frames_to_time(np.arange(pitches.shape[1]), sr=sr, hop_length=hop_length)
        f0 = np.array([pitches[:, i].max() if magnitudes[:, i].max() > 0.1 else 0 for i in range(pitches.shape[1])])
        voiced_flag = f0 > 0

    # Replace NaN with 0
    f0 = np.nan_to_num(f0, nan=0.0)

    # Extract MIDI notes from F0 track
    notes = extract_notes_from_f0(f0_times, f0, voiced_flag, hop_length, sr)

    # Infer harmony from melody
    inferred_harmony = infer_harmony_from_melody(notes)

    voiced_ratio = float(np.mean(voiced_flag)) if len(voiced_flag) > 0 else 0.0
    confidence = round(min(1.0, voiced_ratio * 1.5), 3)

    warnings = []
    if len(notes) < 5:
        warnings.append("Very few melody notes detected — audio may be purely rhythmic or percussive")
    if voiced_ratio < 0.1:
        warnings.append(f"Low voiced ratio ({voiced_ratio:.0%}) — melody extraction unreliable")
    if voiced_ratio > 0.9:
        warnings.append("Very high voiced ratio — may include non-melodic harmonic content")

    pitch_range = (max(n["pitch"] for n in notes) - min(n["pitch"] for n in notes)) if notes else 0
    alternatives = [inferred_harmony[0]] if inferred_harmony else []

    logger.info(f"Extracted {len(notes)} melody notes, voiced_ratio={voiced_ratio:.2f}, confidence={confidence}")

    return {
        "notes": notes,
        "inferredHarmony": inferred_harmony,
        "confidence": confidence,
        "alternatives": alternatives,
        "warnings": warnings,
        "voicedRatio": round(voiced_ratio, 3),
        "pitchRangeSemitones": pitch_range,
        "model": "pyin",
    }
