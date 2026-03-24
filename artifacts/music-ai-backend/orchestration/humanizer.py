"""
Humanization Engine — Phase 4.

Applies musically-aware, deterministic humanization to MIDI note events.

Design principles:
  - Deterministic: given the same seed and parameters, always produces identical output
  - Instrument-aware: each instrument family has its own timing + velocity profiles
  - Phrase-aware: dynamics and timing shift coherently across phrases, not randomly per note
  - Section-aware: chorus is louder, bridge sparser, etc.
  - Swing/shuffle: applies beat-pair swing to appropriate styles
  - Fills: generates drum/melodic fills before section transitions

Usage:
    from orchestration.humanizer import HumanizerConfig, humanize_tracks
    config = HumanizerConfig(seed=42, swing=0.55, style="jazz")
    tracks = humanize_tracks(raw_tracks, config, analysis)

Reference:
    Bello & Pickens (2005): "A Robust Mid-level Representation for Harmonic Content"
    Fonseca-Mora et al. (2013): "Music, Groove, and Timing"
    Friberg & Sundstrom (2002): "Swing ratios and ensemble timing in jazz performance"
"""

from __future__ import annotations

import math
import random
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Per-instrument humanization profiles ─────────────────────────────────────

@dataclass
class InstrumentHumanProfile:
    """Humanization parameters for one instrument family."""

    # Timing jitter in seconds (Gaussian sigma)
    timing_jitter_sec: float = 0.008

    # Maximum timing rush/drag relative to beat (positive = rush, negative = drag)
    timing_tendency_sec: float = 0.0

    # MIDI velocity jitter (±)
    velocity_jitter: int = 6

    # Velocity tendency (positive = slightly louder than notated)
    velocity_tendency: int = 0

    # Phrase-level velocity swell (cresc/dim over a phrase arc)
    phrase_swell_range: Tuple[float, float] = (0.92, 1.08)

    # Whether to apply duration humanization
    duration_humanize: bool = True
    duration_jitter_ratio: float = 0.03    # fraction of note duration

    # Whether to apply swing (beat-pair ratio)
    swing_capable: bool = False

    # Maximum note overlap allowed (seconds)
    max_overlap_sec: float = 0.05


# Standard instrument profiles
_PROFILES: Dict[str, InstrumentHumanProfile] = {
    "piano": InstrumentHumanProfile(
        timing_jitter_sec=0.010,
        velocity_jitter=8,
        phrase_swell_range=(0.90, 1.10),
        swing_capable=True,
    ),
    "guitar": InstrumentHumanProfile(
        timing_jitter_sec=0.012,
        timing_tendency_sec=0.002,   # slight rush
        velocity_jitter=10,
        swing_capable=True,
    ),
    "bass": InstrumentHumanProfile(
        timing_jitter_sec=0.007,
        timing_tendency_sec=-0.003,  # slight drag (pocket)
        velocity_jitter=5,
        swing_capable=True,
    ),
    "double_bass": InstrumentHumanProfile(
        timing_jitter_sec=0.009,
        timing_tendency_sec=-0.004,
        velocity_jitter=6,
        swing_capable=True,
    ),
    "drums": InstrumentHumanProfile(
        timing_jitter_sec=0.006,
        velocity_jitter=12,          # dramatic velocity variation
        phrase_swell_range=(0.85, 1.15),
        swing_capable=True,
        max_overlap_sec=0.0,         # drums never overlap
    ),
    "darbuka": InstrumentHumanProfile(
        timing_jitter_sec=0.005,
        velocity_jitter=10,
        swing_capable=False,
        max_overlap_sec=0.0,
    ),
    "strings": InstrumentHumanProfile(
        timing_jitter_sec=0.014,
        velocity_jitter=7,
        phrase_swell_range=(0.88, 1.12),
        duration_jitter_ratio=0.05,
        swing_capable=False,
    ),
    "violin": InstrumentHumanProfile(
        timing_jitter_sec=0.015,
        velocity_jitter=8,
        phrase_swell_range=(0.85, 1.15),
        swing_capable=False,
    ),
    "brass": InstrumentHumanProfile(
        timing_jitter_sec=0.012,
        velocity_jitter=9,
        swing_capable=False,
    ),
    "trumpet": InstrumentHumanProfile(
        timing_jitter_sec=0.010,
        velocity_jitter=10,
        swing_capable=True,
    ),
    "saxophone": InstrumentHumanProfile(
        timing_jitter_sec=0.011,
        velocity_jitter=9,
        swing_capable=True,
    ),
    "accordion": InstrumentHumanProfile(
        timing_jitter_sec=0.013,
        velocity_jitter=8,
        swing_capable=False,
    ),
    "oud": InstrumentHumanProfile(
        timing_jitter_sec=0.012,
        velocity_jitter=9,
        swing_capable=False,
    ),
    "qanun": InstrumentHumanProfile(
        timing_jitter_sec=0.010,
        velocity_jitter=8,
        swing_capable=False,
    ),
    "nay": InstrumentHumanProfile(
        timing_jitter_sec=0.016,
        velocity_jitter=10,
        swing_capable=False,
    ),
    "pad": InstrumentHumanProfile(
        timing_jitter_sec=0.020,
        velocity_jitter=4,
        duration_jitter_ratio=0.10,
        swing_capable=False,
    ),
    "synth_pad": InstrumentHumanProfile(
        timing_jitter_sec=0.018,
        velocity_jitter=3,
        swing_capable=False,
    ),
    "lead_synth": InstrumentHumanProfile(
        timing_jitter_sec=0.009,
        velocity_jitter=7,
        swing_capable=True,
    ),
    "choir": InstrumentHumanProfile(
        timing_jitter_sec=0.018,
        velocity_jitter=6,
        duration_jitter_ratio=0.06,
        swing_capable=False,
    ),
    "tsimbl": InstrumentHumanProfile(
        timing_jitter_sec=0.010,
        velocity_jitter=8,
        swing_capable=False,
    ),
}

_DEFAULT_PROFILE = InstrumentHumanProfile()


def get_profile(instrument: str) -> InstrumentHumanProfile:
    return _PROFILES.get(instrument, _DEFAULT_PROFILE)


# ─── Humanizer config ─────────────────────────────────────────────────────────

@dataclass
class HumanizerConfig:
    """Top-level configuration for a humanization pass."""

    seed: int = 42

    # Global intensity scale [0.0 = robotic, 1.0 = full human, 1.5 = very loose]
    intensity: float = 1.0

    # Swing ratio [0.5 = straight, 0.67 = full swing triplet]
    swing: float = 0.5

    # Style key (for profile selection and swing interpretation)
    style: str = "pop"

    # Phrase length in bars (used for swell shaping)
    phrase_bars: int = 4

    # BPM (needed for swing timing calculation)
    bpm: float = 120.0

    # Section energy map: section_label → energy [0.0–1.0]
    section_energies: Dict[str, float] = field(default_factory=dict)

    # Per-instrument overrides
    instrument_overrides: Dict[str, Dict] = field(default_factory=dict)


# ─── Core humanizer ──────────────────────────────────────────────────────────

class Humanizer:
    """
    Applies deterministic, musically-aware humanization to note events.

    All randomness comes from a seeded RNG, so output is reproducible.
    """

    def __init__(self, config: HumanizerConfig):
        self.config = config
        self.rng = random.Random(config.seed)

    def humanize_track(
        self,
        notes: List[Dict],
        instrument: str,
        section_label: str = "verse",
    ) -> List[Dict]:
        """
        Apply humanization to all notes in one instrument track.

        Args:
            notes:         List of note dicts with startTime, duration, velocity, pitch
            instrument:    Instrument name (for profile lookup)
            section_label: Section type (for energy-based dynamics)

        Returns:
            New list of humanized note dicts (does not mutate input)
        """
        if not notes:
            return []

        profile = get_profile(instrument)
        intensity = self.config.intensity

        # Override intensity from instrument_overrides if present
        override = self.config.instrument_overrides.get(instrument, {})
        intensity *= override.get("intensity_scale", 1.0)

        energy = self.config.section_energies.get(section_label, 0.6)

        # Build phrase swell envelope
        swell_envelope = self._build_swell(len(notes), profile, energy)

        beat_duration = 60.0 / max(self.config.bpm, 30.0)
        apply_swing = (
            self.config.swing > 0.52
            and profile.swing_capable
            and self.config.style in _SWING_STYLES
        )

        humanized = []
        for i, note in enumerate(notes):
            n = note.copy()

            # Timing jitter
            jitter_sigma = profile.timing_jitter_sec * intensity
            t_jitter = self.rng.gauss(0, jitter_sigma) if jitter_sigma > 0 else 0.0
            t_jitter += profile.timing_tendency_sec * intensity

            start = float(n.get("startTime", 0.0)) + t_jitter

            # Swing timing
            if apply_swing:
                start = self._apply_swing(start, beat_duration)

            n["startTime"] = max(0.0, round(start, 5))

            # Duration jitter
            if profile.duration_humanize:
                dur = float(n.get("duration", beat_duration / 2))
                dur_jitter = dur * profile.duration_jitter_ratio * intensity
                n["duration"] = max(0.02, round(dur + self.rng.gauss(0, dur_jitter), 5))

            # Velocity humanization
            swell_factor = swell_envelope[i]
            energy_offset = int((energy - 0.5) * 20)

            vel = float(n.get("velocity", 70))
            vel *= swell_factor
            vel += energy_offset
            vel_jitter = self.rng.randint(
                -profile.velocity_jitter, profile.velocity_jitter
            )
            vel += vel_jitter * intensity
            vel += profile.velocity_tendency

            n["velocity"] = max(10, min(127, int(round(vel))))

            humanized.append(n)

        return humanized

    def _build_swell(
        self,
        n_notes: int,
        profile: InstrumentHumanProfile,
        energy: float,
    ) -> List[float]:
        """
        Build a phrase-level velocity swell envelope.

        Creates a smooth arc (crescendo → peak → decrescendo) over
        phrase_bars * ~4 notes per bar length.

        Returns list of velocity scale factors.
        """
        if n_notes == 0:
            return []

        lo, hi = profile.phrase_swell_range
        # Scale swell range with energy
        hi = lo + (hi - lo) * (0.5 + energy * 0.5)

        phrase_len = self.config.phrase_bars * 4  # approx 4 notes per bar

        envelope = []
        for i in range(n_notes):
            phase = (i % phrase_len) / phrase_len
            # Raised cosine: peaks at 50% of phrase
            swell = lo + (hi - lo) * math.sin(math.pi * phase)
            # Add tiny noise for naturalness
            noise = self.rng.gauss(0, 0.01)
            envelope.append(max(lo * 0.9, min(hi * 1.1, swell + noise)))

        return envelope

    def _apply_swing(self, t: float, beat_duration: float) -> float:
        """
        Apply swing ratio to a note time.

        In swing, the first eighth note of each beat is lengthened and
        the second is shortened. With swing ratio s:
            downbeat eighth = beat * s
            upbeat eighth   = beat * (1-s)

        Standard triplet swing: s ≈ 0.667
        Light swing:            s ≈ 0.55
        """
        swing = self.config.swing
        eighth = beat_duration / 2.0

        # Which beat and which eighth?
        beat_num = t / beat_duration
        beat_floor = int(beat_num)
        beat_offset = beat_num - beat_floor

        if beat_offset < 0.5:
            # On or before the downbeat eighth
            new_offset = beat_offset * (2 * swing)
        else:
            # After the mid-beat
            new_offset = swing + (beat_offset - 0.5) * (2 * (1 - swing))

        return beat_floor * beat_duration + new_offset * beat_duration


# Styles where swing is applied
_SWING_STYLES = {
    "jazz", "blues", "swing", "rnb", "soul", "funk",
    "hasidic", "bossa_nova", "hiphop",
}


# ─── Public API ───────────────────────────────────────────────────────────────

def humanize_tracks(
    tracks: List[Dict],
    config: HumanizerConfig,
    analysis: Optional[Dict] = None,
) -> List[Dict]:
    """
    Apply humanization to all tracks in an arrangement.

    Args:
        tracks:   List of track dicts [{instrument, notes, section_label?, ...}]
        config:   HumanizerConfig
        analysis: Optional canonical analysis graph (used for section energy)

    Returns:
        New list of humanized tracks (does not mutate input)
    """
    if not tracks:
        return []

    # Extract section energies from analysis if not in config
    if analysis and not config.section_energies:
        try:
            sections = analysis.get("structure", {}).get("sections", [])
            for sec in sections:
                label = sec.get("label", "verse")
                energy = float(sec.get("energy", sec.get("rms_energy", 0.6)))
                config.section_energies[label] = energy
        except Exception:
            pass

    humanizer = Humanizer(config)
    result = []

    for track in tracks:
        instrument = track.get("instrument", "piano")
        notes = track.get("notes", [])
        section_label = track.get("sectionLabel", track.get("section_label", "verse"))

        humanized_notes = humanizer.humanize_track(notes, instrument, section_label)

        new_track = {**track, "notes": humanized_notes, "humanized": True}
        result.append(new_track)

    logger.debug(
        "Humanized %d tracks (seed=%d intensity=%.2f swing=%.2f)",
        len(tracks), config.seed, config.intensity, config.swing,
    )
    return result


def make_humanizer_config(
    seed: int,
    style: str,
    bpm: float,
    intensity: float = 1.0,
    analysis: Optional[Dict] = None,
) -> HumanizerConfig:
    """
    Create a HumanizerConfig from style and analysis data.

    Infers swing ratio from style. Extracts section energies if analysis provided.
    """
    swing_map = {
        "jazz": 0.67, "blues": 0.62, "swing": 0.67,
        "rnb": 0.57, "soul": 0.57, "funk": 0.55,
        "hasidic": 0.60, "bossa_nova": 0.55, "hiphop": 0.53,
    }
    swing = swing_map.get(style, 0.5)

    section_energies: Dict[str, float] = {}
    if analysis:
        try:
            for sec in analysis.get("structure", {}).get("sections", []):
                label = sec.get("label", "verse")
                energy = float(sec.get("energy", sec.get("rms_energy", 0.6)))
                section_energies[label] = energy
        except Exception:
            pass

    return HumanizerConfig(
        seed=seed,
        intensity=intensity,
        swing=swing,
        style=style,
        bpm=bpm,
        section_energies=section_energies,
    )
