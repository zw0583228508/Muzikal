"""
Vocal Analysis Engine.
Extracts pitch, notes, vibrato, phrasing from vocal stem.
Uses pyin for F0 detection + note segmentation.
"""

import logging
import numpy as np
import librosa
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def detect_vibrato(f0: np.ndarray, sr: int, hop_length: int) -> Dict[str, Any]:
    """
    Detect vibrato in F0 track.
    Vibrato = periodic pitch modulation at 5-8 Hz.
    """
    if len(f0) < 10:
        return {"detected": False, "rate_hz": 0.0, "depth_semitones": 0.0, "coverage": 0.0}

    # Filter to voiced frames only (non-zero F0)
    voiced = f0[f0 > 0]
    if len(voiced) < 20:
        return {"detected": False, "rate_hz": 0.0, "depth_semitones": 0.0, "coverage": 0.0}

    # Convert to semitones (cents) for vibrato analysis
    voiced_semitones = 12 * np.log2(voiced / voiced.mean())

    # FFT of semitone track
    fft_freqs = np.fft.rfftfreq(len(voiced_semitones), d=hop_length / sr)
    fft_mag = np.abs(np.fft.rfft(voiced_semitones))

    # Vibrato band: 4-9 Hz
    vib_mask = (fft_freqs >= 4) & (fft_freqs <= 9)
    if not vib_mask.any():
        return {"detected": False, "rate_hz": 0.0, "depth_semitones": 0.0, "coverage": 0.0}

    vib_power = fft_mag[vib_mask].max()
    total_power = fft_mag.max()

    vib_ratio = float(vib_power / (total_power + 1e-8))
    detected = vib_ratio > 0.15

    # Vibrato rate
    vib_rate = float(fft_freqs[vib_mask][fft_mag[vib_mask].argmax()]) if detected else 0.0

    # Vibrato depth in semitones
    depth = float(voiced_semitones.std() * 2) if detected else 0.0

    return {
        "detected": detected,
        "rate_hz": round(vib_rate, 2),
        "depth_semitones": round(depth, 3),
        "coverage": round(float(len(voiced) / max(len(f0), 1)), 3),
    }


def detect_phrasing(notes: List[Dict], total_duration: float) -> List[Dict]:
    """
    Group notes into musical phrases based on silence gaps.
    A phrase break = gap > 0.3s between notes.
    """
    if not notes:
        return []

    phrases = []
    current_phrase_start = notes[0]["startTime"]
    current_phrase_end = notes[0]["endTime"]
    current_phrase_notes = [notes[0]]

    for i in range(1, len(notes)):
        gap = notes[i]["startTime"] - notes[i - 1]["endTime"]
        if gap > 0.3:
            # End phrase
            phrases.append({
                "startTime": round(current_phrase_start, 3),
                "endTime": round(current_phrase_end, 3),
                "noteCount": len(current_phrase_notes),
                "pitchRange": max(n["pitch"] for n in current_phrase_notes) - min(n["pitch"] for n in current_phrase_notes),
            })
            current_phrase_start = notes[i]["startTime"]
            current_phrase_end = notes[i]["endTime"]
            current_phrase_notes = [notes[i]]
        else:
            current_phrase_end = notes[i]["endTime"]
            current_phrase_notes.append(notes[i])

    # Last phrase
    if current_phrase_notes:
        phrases.append({
            "startTime": round(current_phrase_start, 3),
            "endTime": round(current_phrase_end, 3),
            "noteCount": len(current_phrase_notes),
            "pitchRange": max(n["pitch"] for n in current_phrase_notes) - min(n["pitch"] for n in current_phrase_notes),
        })

    return phrases


def analyze_vocal_range(notes: List[Dict]) -> Dict[str, Any]:
    """Compute vocal range from detected notes."""
    if not notes:
        return {"lowest": 0, "highest": 0, "range_semitones": 0, "tessitura": 0}

    pitches = [n["pitch"] for n in notes if 36 <= n["pitch"] <= 84]
    if not pitches:
        return {"lowest": 0, "highest": 0, "range_semitones": 0, "tessitura": 0}

    lowest = min(pitches)
    highest = max(pitches)

    def midi_to_note_name(midi: int) -> str:
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{names[midi % 12]}{midi // 12 - 1}"

    return {
        "lowest": lowest,
        "lowest_name": midi_to_note_name(lowest),
        "highest": highest,
        "highest_name": midi_to_note_name(highest),
        "range_semitones": highest - lowest,
        "tessitura": int(np.median(pitches)),
        "tessitura_name": midi_to_note_name(int(np.median(pitches))),
    }


def analyze_vocals(vocal_audio_path: Optional[str], y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Full vocal analysis pipeline.
    If vocal_audio_path is provided (from Demucs), uses that; otherwise uses full mix.
    """
    logger.info("Running vocal analysis...")

    # Load vocal stem if available
    if vocal_audio_path:
        try:
            y_vocal, sr = librosa.load(vocal_audio_path, sr=sr, mono=True)
            logger.info(f"Using vocal stem: {vocal_audio_path}")
        except Exception as e:
            logger.warning(f"Could not load vocal stem: {e}, using full mix")
            y_vocal = y
    else:
        # Use harmonic component of full mix as proxy for vocals
        y_vocal = librosa.effects.harmonic(y, margin=8)

    hop_length = 512

    # F0 detection (pyin for best accuracy)
    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y_vocal,
            sr=sr,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            hop_length=hop_length,
        )
        f0 = np.nan_to_num(f0, nan=0.0)
    except Exception as e:
        logger.warning(f"pyin failed: {e}")
        f0 = np.zeros(len(y_vocal) // hop_length)
        voiced_flag = np.zeros(len(f0), dtype=bool)

    # Extract melody notes (reuse melody module)
    from audio.melody import extract_notes_from_f0
    f0_times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
    notes = extract_notes_from_f0(f0_times, f0, voiced_flag, hop_length, sr)

    # Vibrato detection
    vibrato = detect_vibrato(f0, sr, hop_length)

    # Phrasing analysis
    phrases = detect_phrasing(notes, len(y_vocal) / sr)

    # Vocal range
    vocal_range = analyze_vocal_range(notes)

    voiced_ratio = round(float(voiced_flag.mean()), 3) if len(voiced_flag) > 0 else 0.0

    confidence = round(min(1.0, voiced_ratio * 1.3 + (0.2 if vibrato["detected"] else 0.0)), 3)
    confidence = max(0.1, confidence)

    warnings: List[str] = []
    if voiced_ratio < 0.1:
        warnings.append("Very low voiced ratio — may be purely instrumental or vocal stem unavailable")
    if len(notes) < 5:
        warnings.append("Too few vocal notes detected — analysis unreliable")
    if vocal_range.get("range_semitones", 0) == 0:
        warnings.append("No valid vocal range detected — check audio quality")
    if not vocal_audio_path:
        warnings.append("No vocal stem provided — analysis run on full mix (less accurate)")

    alternatives: List[str] = []
    if vocal_range.get("tessitura", 0) > 0:
        tess = vocal_range["tessitura"]
        if tess < 57:
            alternatives.append("bass")
        elif tess < 64:
            alternatives.append("baritone")
        elif tess < 69:
            alternatives.append("tenor")
        elif tess < 74:
            alternatives.append("mezzo-soprano")
        else:
            alternatives.append("soprano")

    logger.info(f"Vocal: {len(notes)} notes, {len(phrases)} phrases, vibrato={vibrato['detected']}, confidence={confidence}")

    return {
        "notes": notes,
        "vibrato": vibrato,
        "phrases": phrases,
        "vocal_range": vocal_range,
        "voiced_ratio": voiced_ratio,
        "confidence": confidence,
        "warnings": warnings,
        "alternatives": alternatives,
        "model": "pyin-0.1.1",
    }
