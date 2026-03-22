"""
Rendering Engine: Synthesizes audio from MIDI track data.
Uses wavetable synthesis with ADSR envelopes for each instrument family.
No external soundfonts required — pure numpy synthesis.
"""

import numpy as np
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

SR = 44100  # Sample rate for rendering


# ── ADSR Envelope ────────────────────────────────────────────────────────────

def adsr_envelope(n_samples: int, attack: float, decay: float,
                  sustain: float, release: float, note_duration: float,
                  sr: int = SR) -> np.ndarray:
    """Generate ADSR amplitude envelope."""
    a_samp = int(attack * sr)
    d_samp = int(decay * sr)
    r_samp = int(release * sr)
    total = n_samples

    env = np.zeros(total)
    pos = 0

    # Attack
    end_a = min(pos + a_samp, total)
    if end_a > pos:
        env[pos:end_a] = np.linspace(0, 1, end_a - pos)
    pos = end_a

    # Decay
    end_d = min(pos + d_samp, total)
    if end_d > pos:
        env[pos:end_d] = np.linspace(1, sustain, end_d - pos)
    pos = end_d

    # Sustain
    sustain_end = max(pos, total - r_samp)
    if sustain_end > pos:
        env[pos:sustain_end] = sustain
    pos = sustain_end

    # Release
    if pos < total:
        env[pos:total] = np.linspace(sustain, 0, total - pos)

    return env


# ── Oscillators ──────────────────────────────────────────────────────────────

def sine_wave(freq: float, duration: float, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def sawtooth_wave(freq: float, duration: float, sr: int = SR, harmonics: int = 12) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    wave = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        wave += ((-1) ** (k + 1)) / k * np.sin(2 * np.pi * k * freq * t)
    return wave * (2 / np.pi)


def square_wave(freq: float, duration: float, sr: int = SR, harmonics: int = 8) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    wave = np.zeros_like(t)
    for k in range(1, harmonics + 1, 2):  # odd harmonics only
        wave += (1 / k) * np.sin(2 * np.pi * k * freq * t)
    return wave * (4 / np.pi)


def triangle_wave(freq: float, duration: float, sr: int = SR, harmonics: int = 8) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    wave = np.zeros_like(t)
    for k in range(1, harmonics + 1, 2):
        sign = (-1) ** ((k - 1) // 2)
        wave += sign / (k ** 2) * np.sin(2 * np.pi * k * freq * t)
    return wave * (8 / (np.pi ** 2))


# ── Instrument Definitions ────────────────────────────────────────────────────

INSTRUMENT_CONFIGS = {
    # name: (waveform_type, attack, decay, sustain, release, harmonic_mix, brightness)
    "drums_kick": {
        "type": "kick",
        "attack": 0.003, "decay": 0.08, "sustain": 0.0, "release": 0.04,
    },
    "drums_snare": {
        "type": "snare",
        "attack": 0.002, "decay": 0.05, "sustain": 0.0, "release": 0.03,
    },
    "drums_hihat": {
        "type": "hihat",
        "attack": 0.001, "decay": 0.04, "sustain": 0.0, "release": 0.02,
    },
    "bass": {
        "type": "bass",
        "attack": 0.01, "decay": 0.1, "sustain": 0.7, "release": 0.08,
    },
    "piano": {
        "type": "piano",
        "attack": 0.005, "decay": 0.3, "sustain": 0.4, "release": 0.4,
    },
    "guitar": {
        "type": "guitar",
        "attack": 0.003, "decay": 0.2, "sustain": 0.3, "release": 0.3,
    },
    "strings": {
        "type": "strings",
        "attack": 0.12, "decay": 0.1, "sustain": 0.8, "release": 0.5,
    },
    "pad": {
        "type": "pad",
        "attack": 0.3, "decay": 0.2, "sustain": 0.9, "release": 0.8,
    },
    "lead": {
        "type": "lead",
        "attack": 0.02, "decay": 0.1, "sustain": 0.7, "release": 0.15,
    },
    "brass": {
        "type": "brass",
        "attack": 0.04, "decay": 0.1, "sustain": 0.8, "release": 0.2,
    },
    "default": {
        "type": "sine",
        "attack": 0.01, "decay": 0.1, "sustain": 0.7, "release": 0.2,
    },
}


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2 ** ((midi - 69) / 12.0))


def render_note_kick(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize kick drum: pitched sine sweep + noise click."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Pitch sweep from 150Hz → 40Hz
    f_sweep = np.linspace(150, 40, n)
    wave = np.sin(2 * np.pi * np.cumsum(f_sweep / SR))
    # Add click transient
    click = np.random.randn(n) * np.exp(-t * 200)
    env = np.exp(-t * 15)
    return (wave * env + click * 0.3) * velocity


def render_note_snare(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize snare: pitched body + noise."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    body = sine_wave(200, duration) * np.exp(-t * 25)
    noise = np.random.randn(n) * np.exp(-t * 18)
    return (body * 0.5 + noise * 0.7) * velocity


def render_note_hihat(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize hi-hat: filtered noise."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.randn(n)
    # High-pass via differentiation
    noise = np.diff(noise, prepend=noise[0])
    env = np.exp(-t * 30)
    return noise * env * velocity * 0.5


def render_note_bass(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize bass guitar: sawtooth with warmth."""
    n = int(SR * duration)
    wave = sawtooth_wave(freq, duration, harmonics=8)
    t = np.linspace(0, duration, n, endpoint=False)
    # Low-pass via moving average (simple warmth)
    from numpy import convolve
    window = 8
    kernel = np.ones(window) / window
    wave = convolve(wave, kernel, mode='same')
    env = adsr_envelope(n, 0.01, 0.1, 0.7, 0.08, duration)
    return wave * env * velocity


def render_note_piano(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize piano: multiple harmonics with decay."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Piano harmonic mix
    wave = (
        np.sin(2 * np.pi * freq * t) * 1.0 +
        np.sin(2 * np.pi * 2 * freq * t) * 0.5 +
        np.sin(2 * np.pi * 3 * freq * t) * 0.3 +
        np.sin(2 * np.pi * 4 * freq * t) * 0.15 +
        np.sin(2 * np.pi * 5 * freq * t) * 0.08 +
        np.sin(2 * np.pi * 7 * freq * t) * 0.04
    )
    # Inharmonicity shift for piano character
    wave += np.sin(2 * np.pi * (freq * 2.01) * t) * 0.1
    env = adsr_envelope(n, 0.005, 0.3, 0.4, 0.4, duration)
    return wave * env * velocity * 0.3


def render_note_guitar(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize plucked string using Karplus-Strong algorithm."""
    n = int(SR * duration)
    period = int(SR / freq)
    if period < 2:
        return np.zeros(n)
    # Initialize buffer with noise
    buf = np.random.randn(period) * velocity
    output = np.zeros(n)
    for i in range(n):
        output[i] = buf[i % period]
        # Low-pass filter: average of current and next sample
        idx = i % period
        next_idx = (i + 1) % period
        buf[idx] = 0.996 * 0.5 * (buf[idx] + buf[next_idx])
    return output * 0.8


def render_note_strings(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize strings: sawtooth + chorus effect."""
    n = int(SR * duration)
    # Detuned sawtooths for ensemble
    wave1 = sawtooth_wave(freq, duration, harmonics=6)
    wave2 = sawtooth_wave(freq * 1.005, duration, harmonics=6)  # slight detune
    wave3 = sawtooth_wave(freq * 0.995, duration, harmonics=6)
    wave = (wave1 + wave2 * 0.7 + wave3 * 0.7) / 2.4
    env = adsr_envelope(n, 0.12, 0.1, 0.8, 0.5, duration)
    return wave * env * velocity * 0.35


def render_note_pad(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize pad: soft sine mix with slow attack."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    wave = (
        np.sin(2 * np.pi * freq * t) * 1.0 +
        np.sin(2 * np.pi * freq * 2 * t) * 0.3 +
        np.sin(2 * np.pi * freq * 0.5 * t) * 0.4  # sub octave
    )
    env = adsr_envelope(n, 0.3, 0.2, 0.9, 0.8, duration)
    return wave * env * velocity * 0.4


def render_note_lead(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize lead synth: square wave."""
    n = int(SR * duration)
    wave = square_wave(freq, duration, harmonics=6)
    env = adsr_envelope(n, 0.02, 0.1, 0.7, 0.15, duration)
    return wave * env * velocity * 0.35


def render_note_brass(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Synthesize brass: sawtooth + bandpass emphasis."""
    n = int(SR * duration)
    wave = sawtooth_wave(freq, duration, harmonics=10)
    # Add harmonics brightness
    t = np.linspace(0, duration, n, endpoint=False)
    wave += np.sin(2 * np.pi * 3 * freq * t) * 0.3
    env = adsr_envelope(n, 0.04, 0.1, 0.8, 0.2, duration)
    return wave * env * velocity * 0.3


def render_note_sine(freq: float, duration: float, velocity: float) -> np.ndarray:
    """Generic sine fallback."""
    n = int(SR * duration)
    wave = sine_wave(freq, duration)
    env = adsr_envelope(n, 0.01, 0.1, 0.7, 0.2, duration)
    return wave * env * velocity * 0.5


# ── Instrument Router ────────────────────────────────────────────────────────

INSTRUMENT_RENDERERS = {
    "kick": render_note_kick,
    "snare": render_note_snare,
    "hihat": render_note_hihat,
    "bass": render_note_bass,
    "piano": render_note_piano,
    "guitar": render_note_guitar,
    "strings": render_note_strings,
    "pad": render_note_pad,
    "lead": render_note_lead,
    "brass": render_note_brass,
    "sine": render_note_sine,
}

DRUM_PITCH_MAP = {
    36: "kick",  # Bass drum
    35: "kick",
    38: "snare",  # Snare
    40: "snare",
    42: "hihat",  # Closed hat
    44: "hihat",
    46: "hihat",  # Open hat
    49: "hihat",  # Crash
    51: "hihat",  # Ride
}


def detect_instrument_type(track: dict) -> str:
    """Detect instrument type from track metadata."""
    name = (track.get("name", "") + " " + track.get("instrument", "")).lower()
    channel = track.get("channel", 0)

    if channel == 9:
        return "drums"

    patterns = [
        ("bass", "bass"),
        ("piano|keys|keyboard|grand", "piano"),
        ("guitar|gtr|pick", "guitar"),
        ("strings|violin|viola|cello|string ensemble", "strings"),
        ("pad|ambient|atmosphere", "pad"),
        ("lead|melody|synth lead", "lead"),
        ("brass|trumpet|trombone|horn", "brass"),
    ]
    for pattern, inst_type in patterns:
        import re
        if re.search(pattern, name):
            return inst_type
    return "piano"  # default


def render_track(track: dict, total_duration: float, sr: int = SR) -> np.ndarray:
    """
    Render a single MIDI track to a stereo audio buffer.
    Returns shape: (n_samples, 2)
    """
    n_samples = int(total_duration * sr)
    buf = np.zeros(n_samples)
    inst_type = detect_instrument_type(track)
    notes = track.get("notes", [])
    volume = float(track.get("volume", 0.8))

    for note in notes:
        start_sec = float(note.get("startTime", 0))
        duration_sec = float(note.get("duration", note.get("endTime", start_sec + 0.25) - start_sec))
        pitch = int(note.get("pitch", 60))
        velocity = float(note.get("velocity", 80)) / 127.0

        if duration_sec <= 0 or start_sec >= total_duration:
            continue

        # Clamp duration
        max_dur = min(duration_sec + 0.2, total_duration - start_sec)

        if inst_type == "drums":
            # Route by pitch
            drum_type = DRUM_PITCH_MAP.get(pitch, "hihat")
            renderer = INSTRUMENT_RENDERERS[drum_type]
            freq = 60.0  # ignored by most drum renderers
        else:
            renderer = INSTRUMENT_RENDERERS.get(inst_type, render_note_sine)
            freq = midi_to_freq(pitch)

        try:
            note_audio = renderer(freq, max_dur, velocity * volume)
        except Exception as e:
            logger.debug(f"Note render failed ({inst_type} {pitch}): {e}")
            continue

        start_idx = int(start_sec * sr)
        end_idx = start_idx + len(note_audio)

        if end_idx > n_samples:
            note_audio = note_audio[:n_samples - start_idx]
            end_idx = n_samples

        buf[start_idx:end_idx] += note_audio

    # Soft clip to avoid harsh clipping
    buf = np.tanh(buf)

    # Pan to stereo
    pan = float(track.get("pan", 0.0))  # -1=left, 0=center, +1=right
    pan_l = np.sqrt((1 - pan) / 2)
    pan_r = np.sqrt((1 + pan) / 2)
    stereo = np.column_stack([buf * pan_l, buf * pan_r])

    logger.debug(f"Rendered track '{track.get('name', '?')}' ({inst_type}): {len(notes)} notes")
    return stereo


def render_arrangement(tracks: List[dict], total_duration: float,
                        sr: int = SR, progress_callback=None) -> np.ndarray:
    """
    Render all tracks to a stereo mix.
    Returns stereo float32 array, shape (n_samples, 2).
    """
    n_samples = int(total_duration * sr)
    mix = np.zeros((n_samples, 2), dtype=np.float64)

    active_tracks = [t for t in tracks if not t.get("muted", False)]
    solo_tracks = [t for t in active_tracks if t.get("soloed", False)]
    render_tracks = solo_tracks if solo_tracks else active_tracks

    logger.info(f"Rendering {len(render_tracks)} tracks, {total_duration:.1f}s @ {sr}Hz")

    for i, track in enumerate(render_tracks):
        if progress_callback:
            pct = int(10 + (i / len(render_tracks)) * 70)
            progress_callback(f"Rendering {track.get('name', 'Track')}", pct)

        try:
            track_audio = render_track(track, total_duration, sr)
            # Pad or trim to mix length
            if len(track_audio) < n_samples:
                pad = np.zeros((n_samples - len(track_audio), 2))
                track_audio = np.vstack([track_audio, pad])
            elif len(track_audio) > n_samples:
                track_audio = track_audio[:n_samples]
            mix += track_audio
        except Exception as e:
            logger.warning(f"Failed to render track {track.get('name', '?')}: {e}")

    return mix.astype(np.float32)
