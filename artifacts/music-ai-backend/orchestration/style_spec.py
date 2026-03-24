"""
Style Conditioning Specification — Phase 4.

Defines a formal StyleConditioningSpec Pydantic model that encodes
all musical parameters needed to condition the arrangement planner
and track generators.

Architecture:
  StyleConditioningSpec
    └─ GenreProfile     — groove, harmonic density, instrumentation palette
    └─ ArrangerProfile  — high-level musical traits (no copyrighted specifics)
    └─ ProductionProfile — sonic aesthetic (warm, wide, punchy, intimate, etc.)

These are mapped to ArrangementBlueprint parameters by the planner.

Usage:
    from orchestration.style_spec import StyleConditioningSpec, load_style_spec

    spec = load_style_spec("jazz")
    blueprint_inputs = spec.to_planner_inputs()
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False
    from dataclasses import dataclass as BaseModel, field as Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class GrooveType(str, Enum):
    STRAIGHT    = "straight"
    SWING       = "swing"
    SHUFFLE     = "shuffle"
    HALF_TIME   = "half_time"
    DOUBLE_TIME = "double_time"
    LATIN       = "latin"
    MIDDLE_EASTERN = "middle_eastern"
    BAROQUE     = "baroque"


class HarmonicDensity(str, Enum):
    SPARSE       = "sparse"       # 1–2 chord tones per beat
    MODERATE     = "moderate"     # 3–4 tones, some extensions
    DENSE        = "dense"        # 4–5 tones, extensions + alterations
    FULL         = "full"         # all voices, thick chords


class VoicingStyle(str, Enum):
    BLOCK          = "block"          # all chord tones simultaneously
    ARPEGGIATED    = "arpeggiated"    # broken chord patterns
    SPREAD         = "spread"         # open voicing (root-5th-3rd-7th)
    CLOSE          = "close"          # tight voicing (all within one octave)
    MIXED          = "mixed"          # context-dependent


class ProductionAesthetic(str, Enum):
    WARM       = "warm"        # analog warmth, soft transients
    WIDE       = "wide"        # heavy stereo field
    PUNCHY     = "punchy"      # strong attack, compressed
    INTIMATE   = "intimate"    # small room, dry
    LIVE       = "live"        # room ambience, natural dynamics
    POLISHED   = "polished"    # studio-clean, mastered feel
    CINEMATIC  = "cinematic"   # large hall, dramatic dynamics
    LO_FI      = "lo_fi"       # degraded, vintage character


class ClimaxBehavior(str, Enum):
    GRADUAL      = "gradual"      # slow build throughout
    SUDDEN       = "sudden"       # quick energy spike
    REPEATED     = "repeated"     # multiple climax points
    FINAL_ONLY   = "final_only"   # climax only at end
    NONE         = "none"         # no explicit climax


class TransitionStyle(str, Enum):
    SMOOTH    = "smooth"    # gradual velocity/density transitions
    CUT       = "cut"       # hard cuts between sections
    FILL      = "fill"      # drum/melodic fills
    RISER     = "riser"     # rising synth/effect
    SWELL     = "swell"     # volume swell
    BREAKDOWN = "breakdown" # sudden drop before re-entry


# ─── Sub-models ───────────────────────────────────────────────────────────────

if _PYDANTIC_AVAILABLE:

    class GenreProfile(BaseModel):
        """Genre-level musical characteristics."""

        name: str
        groove: GrooveType = GrooveType.STRAIGHT
        swing_ratio: float = Field(0.5, ge=0.5, le=0.75,
            description="Swing ratio (0.5=straight, 0.67=full triplet swing)")

        harmonic_density: HarmonicDensity = HarmonicDensity.MODERATE
        harmonic_tendencies: List[str] = Field(
            default_factory=list,
            description="Preferred scale/mode tendencies e.g. ['minor', 'phrygian']"
        )

        instrumentation_palette: List[str] = Field(
            default_factory=list,
            description="Preferred instruments for this genre"
        )

        rhythm_complexity: float = Field(0.5, ge=0.0, le=1.0,
            description="Rhythmic complexity (0=simple, 1=complex polyrhythm)")
        ornament_density: float = Field(0.3, ge=0.0, le=1.0,
            description="Ornament frequency (trills, grace notes, fills)")

        bass_role: str = Field("root_fifth",
            description="Bass behavior: root_only, root_fifth, walking, syncopated")
        drum_intensity: float = Field(0.6, ge=0.0, le=1.0)

        # Register preferences
        prefer_high_register: bool = False
        prefer_low_register: bool = False

        # Tempo-related
        typical_bpm_range: Optional[List[float]] = None   # [min, max]


    class ArrangerProfile(BaseModel):
        """
        High-level arranger musical traits.

        These are MUSICAL TRAITS only — not imitation of specific copyrighted works.
        Examples: "dense contrapuntal texture", "call-and-response brass",
                  "lush string pads with descending bass lines".
        """

        name: str
        description: str = ""

        # Musical trait flags
        contrapuntal: bool = False          # uses counterpoint/counterlines
        call_and_response: bool = False     # antiphonal textures
        countermelody_density: float = Field(0.0, ge=0.0, le=1.0)
        voicing_style: VoicingStyle = VoicingStyle.MIXED

        # Density curve description
        build_through_song: bool = True     # generally increases density
        strip_down_intros: bool = True      # intros start sparse
        climax_behavior: ClimaxBehavior = ClimaxBehavior.GRADUAL

        # Transition style
        transition_style: TransitionStyle = TransitionStyle.FILL

        # Doubling policy
        melody_doubling_instruments: List[str] = Field(default_factory=list)
        bass_doubling_instruments: List[str] = Field(default_factory=list)

        # Special flags
        use_pedal_tones: bool = False
        use_ostinatos: bool = False
        add_intros_outros: bool = True      # write intentional intros/outros
        bridge_contrast: bool = True        # bridge should contrast other sections


    class ProductionProfile(BaseModel):
        """Sonic/production aesthetic parameters."""

        aesthetic: ProductionAesthetic = ProductionAesthetic.POLISHED

        # Loudness target (LUFS)
        target_lufs: float = Field(-14.0,
            description="Integrated loudness target in LUFS (EBU R128)")
        true_peak_limit: float = Field(-1.0,
            description="True peak ceiling in dBTP")

        # Reverb
        reverb_send: float = Field(0.3, ge=0.0, le=1.0)
        reverb_time_sec: float = Field(1.5, ge=0.1, le=8.0)

        # Stereo
        stereo_width: float = Field(0.7, ge=0.0, le=1.0)
        mono_compatible: bool = True

        # Compression
        bus_compression: bool = True
        transient_shaping: bool = False

        # EQ tendencies
        high_pass_hz: int = 60              # HPF for main bus
        air_band_boost_db: float = 0.0     # extra air (12–16kHz)

        # Mix notes
        notes: str = ""


    class StyleConditioningSpec(BaseModel):
        """
        Complete style conditioning specification for arrangement generation.

        Maps into ArrangementBlueprint parameters via to_planner_inputs().
        """

        style_id: str
        display_name: str
        genre: GenreProfile
        arranger: ArrangerProfile
        production: ProductionProfile

        # Version for provenance tracking
        spec_version: str = "1.0"
        notes: str = ""

        def to_planner_inputs(self) -> Dict[str, Any]:
            """
            Convert to a flat dict for consumption by arrangement_planner.py.

            Returns values that map directly into ArrangementBlueprint fields.
            """
            return {
                "style_id":             self.style_id,
                "groove":               self.genre.groove.value,
                "swing_ratio":          self.genre.swing_ratio,
                "harmonic_density":     self.genre.harmonic_density.value,
                "harmonic_tendencies":  self.genre.harmonic_tendencies,
                "instruments":          self.genre.instrumentation_palette,
                "rhythm_complexity":    self.genre.rhythm_complexity,
                "ornament_density":     self.genre.ornament_density,
                "bass_role":            self.genre.bass_role,
                "drum_intensity":       self.genre.drum_intensity,
                "contrapuntal":         self.arranger.contrapuntal,
                "call_and_response":    self.arranger.call_and_response,
                "countermelody":        self.arranger.countermelody_density,
                "voicing_style":        self.arranger.voicing_style.value,
                "build_through_song":   self.arranger.build_through_song,
                "strip_down_intros":    self.arranger.strip_down_intros,
                "climax_behavior":      self.arranger.climax_behavior.value,
                "transition_style":     self.arranger.transition_style.value,
                "use_pedal_tones":      self.arranger.use_pedal_tones,
                "use_ostinatos":        self.arranger.use_ostinatos,
                "bridge_contrast":      self.arranger.bridge_contrast,
                "target_lufs":          self.production.target_lufs,
                "reverb_send":          self.production.reverb_send,
                "stereo_width":         self.production.stereo_width,
                "spec_version":         self.spec_version,
            }

        def to_humanizer_config_kwargs(self) -> Dict[str, Any]:
            """Return kwargs suitable for make_humanizer_config()."""
            return {
                "style": self.style_id,
                "intensity": min(1.0, 0.5 + self.genre.rhythm_complexity * 0.5),
            }

else:
    # Dataclass fallback if Pydantic not available
    from dataclasses import dataclass, field as dc_field

    @dataclass
    class GenreProfile:  # type: ignore
        name: str
        groove: str = "straight"
        swing_ratio: float = 0.5
        harmonic_density: str = "moderate"
        harmonic_tendencies: list = dc_field(default_factory=list)
        instrumentation_palette: list = dc_field(default_factory=list)
        rhythm_complexity: float = 0.5
        ornament_density: float = 0.3
        bass_role: str = "root_fifth"
        drum_intensity: float = 0.6
        prefer_high_register: bool = False
        prefer_low_register: bool = False
        typical_bpm_range: object = None

    @dataclass
    class ArrangerProfile:  # type: ignore
        name: str
        description: str = ""
        contrapuntal: bool = False
        call_and_response: bool = False
        countermelody_density: float = 0.0
        voicing_style: str = "mixed"
        build_through_song: bool = True
        strip_down_intros: bool = True
        climax_behavior: str = "gradual"
        transition_style: str = "fill"
        melody_doubling_instruments: list = dc_field(default_factory=list)
        bass_doubling_instruments: list = dc_field(default_factory=list)
        use_pedal_tones: bool = False
        use_ostinatos: bool = False
        add_intros_outros: bool = True
        bridge_contrast: bool = True

    @dataclass
    class ProductionProfile:  # type: ignore
        aesthetic: str = "polished"
        target_lufs: float = -14.0
        true_peak_limit: float = -1.0
        reverb_send: float = 0.3
        reverb_time_sec: float = 1.5
        stereo_width: float = 0.7
        mono_compatible: bool = True
        bus_compression: bool = True
        transient_shaping: bool = False
        high_pass_hz: int = 60
        air_band_boost_db: float = 0.0
        notes: str = ""

    @dataclass
    class StyleConditioningSpec:  # type: ignore
        style_id: str
        display_name: str
        genre: GenreProfile = dc_field(default_factory=lambda: GenreProfile(name="default"))
        arranger: ArrangerProfile = dc_field(default_factory=lambda: ArrangerProfile(name="default"))
        production: ProductionProfile = dc_field(default_factory=ProductionProfile)
        spec_version: str = "1.0"
        notes: str = ""

        def to_planner_inputs(self) -> Dict[str, Any]:
            return {
                "style_id": self.style_id,
                "groove": getattr(self.genre, "groove", "straight"),
                "swing_ratio": getattr(self.genre, "swing_ratio", 0.5),
                "instruments": getattr(self.genre, "instrumentation_palette", []),
                "drum_intensity": getattr(self.genre, "drum_intensity", 0.6),
            }

        def to_humanizer_config_kwargs(self) -> Dict[str, Any]:
            return {"style": self.style_id, "intensity": 1.0}


# ─── Built-in style library ───────────────────────────────────────────────────

_BUILTIN_STYLES: Dict[str, Dict[str, Any]] = {}

if _PYDANTIC_AVAILABLE:
    def _make_spec(style_id: str, display_name: str, genre_kw: dict,
                   arranger_kw: dict, prod_kw: dict, notes: str = "") -> StyleConditioningSpec:
        return StyleConditioningSpec(
            style_id=style_id,
            display_name=display_name,
            genre=GenreProfile(name=style_id, **genre_kw),
            arranger=ArrangerProfile(name=style_id, **arranger_kw),
            production=ProductionProfile(**prod_kw),
            notes=notes,
        )

    _BUILTIN_SPEC_MAP: Dict[str, StyleConditioningSpec] = {

        "pop": _make_spec(
            "pop", "Pop",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.MODERATE,
                instrumentation_palette=["drums", "bass", "piano", "guitar", "strings", "pad"],
                rhythm_complexity=0.55, ornament_density=0.2, bass_role="root_fifth",
                drum_intensity=0.7, typical_bpm_range=[90, 140]),
            arranger_kw=dict(build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.GRADUAL,
                transition_style=TransitionStyle.FILL,
                voicing_style=VoicingStyle.MIXED),
            prod_kw=dict(aesthetic=ProductionAesthetic.POLISHED, target_lufs=-14.0,
                reverb_send=0.25, stereo_width=0.75),
        ),

        "jazz": _make_spec(
            "jazz", "Jazz",
            genre_kw=dict(groove=GrooveType.SWING, swing_ratio=0.67,
                harmonic_density=HarmonicDensity.DENSE,
                instrumentation_palette=["drums", "bass", "piano", "guitar", "brass", "saxophone"],
                rhythm_complexity=0.75, ornament_density=0.5, bass_role="walking",
                drum_intensity=0.55, typical_bpm_range=[80, 250]),
            arranger_kw=dict(contrapuntal=True, call_and_response=True,
                voicing_style=VoicingStyle.SPREAD,
                build_through_song=False, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.REPEATED,
                transition_style=TransitionStyle.SMOOTH,
                use_pedal_tones=True, bridge_contrast=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.WARM, target_lufs=-16.0,
                reverb_send=0.4, reverb_time_sec=2.0, stereo_width=0.65),
        ),

        "bossa_nova": _make_spec(
            "bossa_nova", "Bossa Nova",
            genre_kw=dict(groove=GrooveType.LATIN, swing_ratio=0.55,
                harmonic_density=HarmonicDensity.DENSE,
                harmonic_tendencies=["major7", "minor7", "dominant9"],
                instrumentation_palette=["drums", "bass", "guitar", "piano"],
                rhythm_complexity=0.60, ornament_density=0.35, bass_role="syncopated",
                drum_intensity=0.40, typical_bpm_range=[100, 140]),
            arranger_kw=dict(voicing_style=VoicingStyle.SPREAD,
                build_through_song=False, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.NONE,
                transition_style=TransitionStyle.SMOOTH),
            prod_kw=dict(aesthetic=ProductionAesthetic.INTIMATE, target_lufs=-15.0,
                reverb_send=0.2, stereo_width=0.55),
        ),

        "classical": _make_spec(
            "classical", "Classical",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.FULL,
                instrumentation_palette=["strings", "brass", "piano"],
                rhythm_complexity=0.8, ornament_density=0.7, bass_role="root_fifth",
                drum_intensity=0.0, typical_bpm_range=[50, 200]),
            arranger_kw=dict(contrapuntal=True, call_and_response=True,
                voicing_style=VoicingStyle.SPREAD,
                build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.GRADUAL,
                transition_style=TransitionStyle.SMOOTH,
                melody_doubling_instruments=["violin", "strings"],
                bridge_contrast=True, add_intros_outros=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.CINEMATIC, target_lufs=-18.0,
                reverb_send=0.55, reverb_time_sec=3.0, stereo_width=0.85,
                bus_compression=False),
        ),

        "hasidic": _make_spec(
            "hasidic", "Hasidic / Klezmer",
            genre_kw=dict(groove=GrooveType.SWING, swing_ratio=0.60,
                harmonic_density=HarmonicDensity.MODERATE,
                harmonic_tendencies=["minor", "phrygian", "dorian", "freygish"],
                instrumentation_palette=["drums", "bass", "violin", "accordion",
                                         "strings", "brass", "tsimbl"],
                rhythm_complexity=0.65, ornament_density=0.60, bass_role="root_fifth",
                drum_intensity=0.70, typical_bpm_range=[120, 200]),
            arranger_kw=dict(call_and_response=True,
                voicing_style=VoicingStyle.BLOCK,
                build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.FINAL_ONLY,
                transition_style=TransitionStyle.FILL,
                melody_doubling_instruments=["violin", "accordion"],
                bridge_contrast=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.LIVE, target_lufs=-13.0,
                reverb_send=0.35, stereo_width=0.70),
            notes="Freygish (altered Phrygian) is the characteristic Hasidic scale.",
        ),

        "middle_eastern": _make_spec(
            "middle_eastern", "Middle Eastern",
            genre_kw=dict(groove=GrooveType.MIDDLE_EASTERN, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.MODERATE,
                harmonic_tendencies=["phrygian_dominant", "double_harmonic", "hijaz", "nahawand"],
                instrumentation_palette=["darbuka", "bass", "oud", "strings", "pad", "nay", "qanun"],
                rhythm_complexity=0.70, ornament_density=0.65, bass_role="root_fifth",
                drum_intensity=0.65, typical_bpm_range=[90, 160]),
            arranger_kw=dict(call_and_response=True,
                voicing_style=VoicingStyle.ARPEGGIATED,
                build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.FINAL_ONLY,
                transition_style=TransitionStyle.BREAKDOWN,
                use_pedal_tones=True, use_ostinatos=True,
                bridge_contrast=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.WARM, target_lufs=-14.0,
                reverb_send=0.30, stereo_width=0.65),
            notes="Maqam-based scales. Microtonal intonation possible in real performance.",
        ),

        "cinematic": _make_spec(
            "cinematic", "Cinematic",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.FULL,
                instrumentation_palette=["strings", "brass", "piano", "pad", "drums", "choir"],
                rhythm_complexity=0.70, ornament_density=0.25, bass_role="root_fifth",
                drum_intensity=0.55),
            arranger_kw=dict(build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.GRADUAL,
                transition_style=TransitionStyle.SWELL,
                use_pedal_tones=True, melody_doubling_instruments=["strings", "brass"],
                bridge_contrast=True, add_intros_outros=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.CINEMATIC, target_lufs=-16.0,
                reverb_send=0.60, reverb_time_sec=3.5, stereo_width=0.90),
        ),

        "ballad": _make_spec(
            "ballad", "Ballad",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.MODERATE,
                instrumentation_palette=["piano", "strings", "pad", "bass"],
                rhythm_complexity=0.35, ornament_density=0.20, bass_role="root_fifth",
                drum_intensity=0.30, typical_bpm_range=[50, 90]),
            arranger_kw=dict(build_through_song=True, strip_down_intros=True,
                climax_behavior=ClimaxBehavior.FINAL_ONLY,
                transition_style=TransitionStyle.SWELL,
                voicing_style=VoicingStyle.SPREAD, bridge_contrast=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.INTIMATE, target_lufs=-15.0,
                reverb_send=0.45, reverb_time_sec=2.5, stereo_width=0.55),
        ),

        "electronic": _make_spec(
            "electronic", "Electronic",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.52,
                harmonic_density=HarmonicDensity.SPARSE,
                instrumentation_palette=["drums", "bass", "pad", "lead_synth", "synth_pad"],
                rhythm_complexity=0.80, ornament_density=0.15, bass_role="syncopated",
                drum_intensity=0.90, typical_bpm_range=[120, 170]),
            arranger_kw=dict(build_through_song=True, strip_down_intros=False,
                climax_behavior=ClimaxBehavior.REPEATED,
                transition_style=TransitionStyle.RISER,
                use_pedal_tones=True, use_ostinatos=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.PUNCHY, target_lufs=-9.0,
                reverb_send=0.15, stereo_width=0.95, bus_compression=True,
                transient_shaping=True),
        ),

        "rock": _make_spec(
            "rock", "Rock",
            genre_kw=dict(groove=GrooveType.STRAIGHT, swing_ratio=0.5,
                harmonic_density=HarmonicDensity.MODERATE,
                instrumentation_palette=["drums", "bass", "guitar", "piano"],
                rhythm_complexity=0.65, ornament_density=0.20, bass_role="root_fifth",
                drum_intensity=0.85, typical_bpm_range=[100, 160]),
            arranger_kw=dict(build_through_song=True, strip_down_intros=False,
                climax_behavior=ClimaxBehavior.GRADUAL,
                transition_style=TransitionStyle.FILL,
                bridge_contrast=True),
            prod_kw=dict(aesthetic=ProductionAesthetic.PUNCHY, target_lufs=-11.0,
                reverb_send=0.20, stereo_width=0.75, bus_compression=True),
        ),
    }
else:
    _BUILTIN_SPEC_MAP: Dict[str, Any] = {}


def load_style_spec(style_id: str) -> Optional["StyleConditioningSpec"]:
    """
    Load a StyleConditioningSpec by style ID.

    Returns the built-in spec if available, else None.
    """
    return _BUILTIN_SPEC_MAP.get(style_id)


def list_style_ids() -> List[str]:
    """Return all available built-in style IDs."""
    return list(_BUILTIN_SPEC_MAP.keys())


def get_planner_inputs(style_id: str) -> Dict[str, Any]:
    """
    Convenience function: load style spec and return planner inputs dict.

    Falls back to empty dict if style not found.
    """
    spec = load_style_spec(style_id)
    if spec is None:
        return {"style_id": style_id}
    return spec.to_planner_inputs()
