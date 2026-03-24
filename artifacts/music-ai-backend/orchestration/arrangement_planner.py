"""
Two-Stage Arrangement Planner v1.0

Replaces the flat, heuristic arranger with a two-stage architecture:

  Stage 1 — Structural Planner (plan_arrangement)
    Input:  Canonical analysis graph (sections, chords, key, rhythm, energy)
    Output: ArrangementBlueprint — per-section instrument selection, density,
            dynamics, fills, transitions, and harmonic voicing guidance.

    Data sources:
      - Section energy/density from structure detector (real audio energy)
      - Harmonic rhythm from chord analysis (diatonic_ratio, harmonic_rhythm)
      - Tempo and time signature from beat tracker
      - Style profile from YAML style database
      - Group IDs for repeated sections (same group → same arrangement)

  Stage 2 — Symbolic Generator (render_blueprint)
    Input:  ArrangementBlueprint + chord timeline + beat grid
    Output: List of track dicts (instrument, notes, channel, volume)

    Calls specialized generators from arranger.py for each instrument family.
    The blueprint controls:
      - Which instruments are active per section
      - Base velocity (dynamics) per section
      - Whether to add fills at section boundaries
      - Voicing density (sparse/dense)

Key improvements over flat arranger:
  - Energy-driven dynamics: chorus energy → higher velocity, more instruments
  - Group-aware: repeated sections are templated from first occurrence
  - Harmonic rhythm awareness: dense chords → piano holds, sparse → arpeggiate
  - Fill injection at section boundaries
  - Transition signals (risers, falls) between sections

Reference:
  Bitteur (2010): "JJazzLab — Open-Source Backing Track Generator"
  Simon et al. (2008): "MySong — Automatic Accompaniment Generation"
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SectionPlan:
    """Arrangement plan for a single section."""
    section_label: str          # "intro", "verse", "chorus", "bridge", "outro"
    group_id: Optional[int]     # from structure_detector grouping
    start: float
    end:   float
    duration: float

    # Dynamics
    base_velocity: int          # 0–127
    velocity_spread: int        # ±spread for humanization
    energy_level: float         # 0.0–1.0 (from audio energy profile)

    # Instrument selection
    active_instruments: List[str]
    instrument_volumes: Dict[str, float]    # instrument → relative volume [0,1]

    # Rhythmic character
    density: float              # 0.0–1.0 (controls note density)
    swing_factor: float         # 0.0 = straight, 1.0 = full swing

    # Harmonic guidance
    voicing_style: str          # "block", "arpeggiated", "sustained", "sparse"
    chord_voicing_octave: int   # preferred octave for chord voicings

    # Structural elements
    add_fill: bool              # drum/melodic fill before next section
    add_buildup: bool           # gradual increase in energy
    add_breakdown: bool         # gradual decrease before verse

    # Transition
    transition_to_next: str     # "cut", "fill", "fade", "riser", "none"


@dataclass
class ArrangementBlueprint:
    """Complete arrangement plan for the entire song."""
    style_id: str
    key: str
    mode: str
    bpm: float
    time_sig: Tuple[int, int]
    total_duration: float

    section_plans: List[SectionPlan]
    global_instruments: List[str]   # instruments active in ≥1 section

    harmonic_density: float         # average harmonic_rhythm value
    diatonic_ratio: float           # fraction of diatonic chords
    energy_range: Tuple[float, float]   # (min_energy, max_energy) across sections

    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Stage 1: Structural Planner ─────────────────────────────────────────────

# Instrument sets per section type
_SECTION_INSTRUMENTS: Dict[str, List[str]] = {
    "intro":         ["drums", "piano", "strings"],
    "verse":         ["drums", "bass", "piano", "guitar"],
    "pre-chorus":    ["drums", "bass", "piano", "guitar", "strings"],
    "chorus":        ["drums", "bass", "piano", "guitar", "strings", "synth_lead"],
    "bridge":        ["drums", "bass", "piano", "strings"],
    "instrumental":  ["drums", "bass", "guitar", "synth_lead", "strings"],
    "outro":         ["drums", "bass", "piano", "strings"],
    "break":         ["drums"],
    "buildup":       ["drums", "bass", "synth_lead"],
    "drop":          ["drums", "bass", "synth_lead", "guitar"],
}

# Base velocity per section type (0–127)
_SECTION_VELOCITY: Dict[str, int] = {
    "intro":         64,
    "verse":         80,
    "pre-chorus":    90,
    "chorus":        110,
    "bridge":        85,
    "instrumental":  100,
    "outro":         70,
    "break":         60,
    "buildup":       95,
    "drop":          115,
}

# Density per section type (0.0–1.0)
_SECTION_DENSITY: Dict[str, float] = {
    "intro":         0.40,
    "verse":         0.60,
    "pre-chorus":    0.75,
    "chorus":        0.90,
    "bridge":        0.65,
    "instrumental":  0.80,
    "outro":         0.45,
    "break":         0.25,
    "buildup":       0.70,
    "drop":          0.95,
}

# Voicing style per section type
_SECTION_VOICING: Dict[str, str] = {
    "intro":         "sparse",
    "verse":         "arpeggiated",
    "pre-chorus":    "arpeggiated",
    "chorus":        "block",
    "bridge":        "sustained",
    "instrumental":  "arpeggiated",
    "outro":         "sparse",
    "break":         "sparse",
    "buildup":       "sustained",
    "drop":          "block",
}

# Transition types between sections
_TRANSITION_MAP: Dict[Tuple[str, str], str] = {
    ("verse",   "pre-chorus"): "fill",
    ("pre-chorus", "chorus"):  "riser",
    ("chorus",  "verse"):      "fill",
    ("chorus",  "bridge"):     "fill",
    ("bridge",  "chorus"):     "riser",
    ("buildup", "drop"):       "riser",
    ("drop",    "break"):      "fade",
    ("verse",   "chorus"):     "fill",
    ("intro",   "verse"):      "cut",
    ("chorus",  "outro"):      "fade",
}


def _get_style_profile(style_id: str) -> Dict[str, Any]:
    """Load style profile from YAML, or return defaults."""
    try:
        from orchestration.arranger import _load_arranger_profiles
        profiles = _load_arranger_profiles()
        return profiles.get(style_id, {})
    except Exception as e:
        logger.debug("Style profile load failed for %s: %s", style_id, e)
        return {}


def _energy_to_velocity(energy: float, section_type: str) -> int:
    """
    Combine audio energy profile with section-type velocity to get actual velocity.
    energy: 0.0–1.0 from structure_detector RMS measurement
    """
    base = _SECTION_VELOCITY.get(section_type, 80)
    # Energy modulates: ±15 velocity from base
    energy_adj = int((energy - 0.5) * 30)
    return max(40, min(120, base + energy_adj))


def _energy_to_density(energy: float, section_type: str) -> float:
    """Combine audio energy with section density."""
    base = _SECTION_DENSITY.get(section_type, 0.6)
    adj = (energy - 0.5) * 0.2
    return max(0.2, min(1.0, base + adj))


def _get_transition(from_label: str, to_label: str) -> str:
    """Get transition type between two section labels."""
    key = (from_label.lower(), to_label.lower())
    return _TRANSITION_MAP.get(key, "cut")


def plan_arrangement(
    analysis: Dict[str, Any],
    style_id: str = "pop",
    override_instruments: Optional[Dict[str, List[str]]] = None,
    override_density: Optional[float] = None,
) -> ArrangementBlueprint:
    """
    Stage 1: Produce an ArrangementBlueprint from the canonical analysis graph.

    Args:
        analysis: Full analysis result dict (from pipeline)
        style_id: Style profile ID (matches YAML profiles)
        override_instruments: Optional per-section instrument override
        override_density: Optional global density override

    Returns:
        ArrangementBlueprint
    """
    rhythm    = analysis.get("rhythm", {})
    key_data  = analysis.get("key",    {})
    struct    = analysis.get("structure", {})
    chords_d  = analysis.get("chords",   {})

    bpm       = float(rhythm.get("bpm", 120.0))
    key       = str(key_data.get("globalKey", "C"))
    mode      = str(key_data.get("mode",  "major"))
    time_sig  = (
        int(rhythm.get("timeSignatureNumerator", 4)),
        int(rhythm.get("timeSignatureDenominator", 4)),
    )
    sections  = struct.get("sections", [])
    total_dur = float(rhythm.get("duration", sum(
        float(s.get("duration", 0)) for s in sections
    )))
    if total_dur <= 0:
        total_dur = 120.0

    # Harmonic density analysis
    harmonic_rhythm = float(chords_d.get("harmonicRhythm", 2.0))
    diatonic_ratio  = float(chords_d.get("diatonicRatio",  0.75))

    # Load style profile for adjustments
    style_profile = _get_style_profile(style_id)

    # Compute energy range across sections
    energies = [float(s.get("energy", 0.5)) for s in sections if "energy" in s]
    if not energies:
        energies = [0.5]
    energy_range = (min(energies), max(energies))

    # Build per-section plans
    section_plans: List[SectionPlan] = []
    group_template_cache: Dict[int, SectionPlan] = {}

    for i, sec in enumerate(sections):
        label    = str(sec.get("label", "verse")).lower()
        gid      = sec.get("group_id")
        start    = float(sec.get("start", 0))
        end      = float(sec.get("end", start + 8))
        duration = float(sec.get("duration", end - start))
        energy   = float(sec.get("energy", 0.5))

        # If this section is a repeated group, template from first occurrence
        if gid is not None and gid in group_template_cache:
            template = group_template_cache[gid]
            plan = SectionPlan(
                section_label=label,
                group_id=gid,
                start=start,
                end=end,
                duration=duration,
                base_velocity=template.base_velocity,
                velocity_spread=template.velocity_spread,
                energy_level=energy,
                active_instruments=list(template.active_instruments),
                instrument_volumes=dict(template.instrument_volumes),
                density=template.density,
                swing_factor=template.swing_factor,
                voicing_style=template.voicing_style,
                chord_voicing_octave=template.chord_voicing_octave,
                add_fill=(i < len(sections) - 1),
                add_buildup=template.add_buildup,
                add_breakdown=template.add_breakdown,
                transition_to_next=_get_transition(
                    label,
                    sections[i + 1].get("label", "verse") if i + 1 < len(sections) else "outro",
                ),
            )
            section_plans.append(plan)
            continue

        # Compute instruments
        default_insts = _SECTION_INSTRUMENTS.get(label, ["drums", "bass", "piano"])
        if override_instruments and label in override_instruments:
            instruments = override_instruments[label]
        else:
            # Style profile may specify per-section instruments
            sp_insts = style_profile.get("section_instruments", {}).get(label)
            instruments = sp_insts if sp_insts else list(default_insts)

        # Instrument volumes (default: all at 1.0)
        inst_volumes = {inst: 1.0 for inst in instruments}
        # Reduce rhythm section slightly in intro/outro
        if label in ("intro", "outro"):
            inst_volumes["drums"] = 0.75

        # Dynamics
        velocity = _energy_to_velocity(energy, label)
        density = override_density or _energy_to_density(energy, label)
        # Harmonic density modulates piano density
        if harmonic_rhythm > 4.0:
            density *= 1.1   # fast chord changes → busier arrangement
        elif harmonic_rhythm < 1.5:
            density *= 0.9   # slow chords → sparser
        density = min(1.0, density)

        # Voicing style
        voicing = _SECTION_VOICING.get(label, "arpeggiated")
        # Fast harmonic rhythm → block chords; slow → arpeggiated
        if harmonic_rhythm > 4.0:
            voicing = "block"
        elif harmonic_rhythm < 1.0 and voicing == "arpeggiated":
            voicing = "sustained"

        # Swing (style-driven)
        swing = float(style_profile.get("swing", 0.0))

        # Transition
        next_label = sections[i + 1].get("label", "outro") if i + 1 < len(sections) else "outro"
        transition = _get_transition(label, next_label)

        # Buildup/breakdown
        add_buildup    = (label == "pre-chorus" or transition == "riser")
        add_breakdown  = (label == "outro" or next_label in ("verse", "break"))

        plan = SectionPlan(
            section_label=label,
            group_id=gid,
            start=start,
            end=end,
            duration=duration,
            base_velocity=velocity,
            velocity_spread=12,
            energy_level=energy,
            active_instruments=instruments,
            instrument_volumes=inst_volumes,
            density=density,
            swing_factor=swing,
            voicing_style=voicing,
            chord_voicing_octave=4,
            add_fill=(transition in ("fill", "riser") and i < len(sections) - 1),
            add_buildup=add_buildup,
            add_breakdown=add_breakdown,
            transition_to_next=transition,
        )
        section_plans.append(plan)

        if gid is not None:
            group_template_cache[gid] = plan

    # Collect global instrument set
    all_instruments: List[str] = []
    for p in section_plans:
        for inst in p.active_instruments:
            if inst not in all_instruments:
                all_instruments.append(inst)

    blueprint = ArrangementBlueprint(
        style_id=style_id,
        key=key,
        mode=mode,
        bpm=bpm,
        time_sig=time_sig,
        total_duration=total_dur,
        section_plans=section_plans,
        global_instruments=all_instruments,
        harmonic_density=harmonic_rhythm,
        diatonic_ratio=diatonic_ratio,
        energy_range=energy_range,
        metadata={
            "n_sections": len(section_plans),
            "style_profile_loaded": bool(style_profile),
            "planner_version": "two_stage_v1",
        },
    )

    logger.info(
        "[planner] Blueprint: style=%s, %d sections, instruments=%s",
        style_id, len(section_plans), all_instruments,
    )
    return blueprint


# ─── Stage 2: Symbolic Generator ─────────────────────────────────────────────

def render_blueprint(
    blueprint: ArrangementBlueprint,
    chord_timeline: List[Dict],
    beat_grid:      List[float],
    analysis:       Dict[str, Any],
) -> Dict[str, Any]:
    """
    Stage 2: Generate MIDI track data from the ArrangementBlueprint.

    Calls specialized generators from arranger.py for each instrument,
    driven by the per-section plan from Stage 1.

    Returns:
        dict compatible with the arrangement response schema:
        {"tracks": [...], "totalDurationSeconds": float, "source": "two_stage_planner_v1"}
    """
    from orchestration.arranger import (
        generate_drum_pattern,
        generate_bass_line,
        generate_piano_voicings,
        generate_string_pad,
        generate_guitar_strum,
        generate_melody_line,
        humanize,
        _beats_in_range,
        _chords_in_range,
    )

    bpm        = blueprint.bpm
    style_id   = blueprint.style_id
    total_dur  = blueprint.total_duration
    time_sig   = blueprint.time_sig

    tracks: List[Dict] = []
    processed_groups: Dict[int, Dict[str, List]] = {}

    # Process each section plan
    for i, plan in enumerate(blueprint.section_plans):
        seg_start = plan.start
        seg_end   = plan.end
        label     = plan.section_label
        density   = plan.density
        velocity  = plan.base_velocity

        # Chords and beats in this section
        section_chords = _chords_in_range(chord_timeline, seg_start, seg_end)
        section_beats  = _beats_in_range(beat_grid, seg_start, seg_end)

        section_analysis = {
            **analysis,
            "section_label":   label,
            "density_override": density,
            "velocity_override": velocity,
            "swing_factor":    plan.swing_factor,
        }

        # If repeated group with template, retrieve from cache and offset times
        if plan.group_id is not None and plan.group_id in processed_groups:
            cached = processed_groups[plan.group_id]
            # Offset the cached notes by time delta
            time_delta = seg_start - cached["template_start"]
            for inst, notes in cached["notes"].items():
                offset_notes = []
                for n in notes:
                    if seg_start <= float(n.get("startTime", 0)) + time_delta < seg_end:
                        nn = dict(n)
                        nn["startTime"] = round(float(n["startTime"]) + time_delta, 4)
                        offset_notes.append(nn)
                if offset_notes:
                    _add_notes_to_tracks(tracks, inst, offset_notes, plan, i)
            continue

        section_notes: Dict[str, List] = {}

        # ── Drums ─────────────────────────────────────────────────────────────
        if "drums" in plan.active_instruments:
            try:
                time_sig_num = time_sig[0] if isinstance(time_sig, (tuple, list)) else int(time_sig)
                drum_notes = generate_drum_pattern(
                    section_beats, time_sig_num, style=style_id,
                    density=density, analysis=section_analysis,
                )
                if plan.add_fill and drum_notes and i + 1 < len(blueprint.section_plans):
                    fill_start = seg_end - min(2.0, plan.duration * 0.15)
                    fill_beats = _beats_in_range(beat_grid, fill_start, seg_end)
                    fill_notes = generate_drum_pattern(
                        fill_beats, time_sig_num, style=style_id,
                        density=min(1.0, density + 0.3), analysis=section_analysis,
                    )
                    drum_notes = drum_notes + fill_notes
                drum_notes = humanize(drum_notes, velocity_jitter=plan.velocity_spread // 2)
                section_notes["drums"] = drum_notes
            except Exception as e:
                logger.warning("[planner] Drum gen failed (section=%s): %s", label, e)

        # ── Bass ──────────────────────────────────────────────────────────────
        if "bass" in plan.active_instruments:
            try:
                bass_notes = generate_bass_line(
                    section_chords, section_beats, style=style_id,
                    analysis=section_analysis,
                )
                bass_notes = humanize(bass_notes, velocity_jitter=8)
                section_notes["bass"] = bass_notes
            except Exception as e:
                logger.warning("[planner] Bass gen failed (section=%s): %s", label, e)

        # ── Piano / Keys ──────────────────────────────────────────────────────
        if "piano" in plan.active_instruments:
            try:
                piano_notes = generate_piano_voicings(
                    section_chords, style=style_id,
                    density=density, analysis=section_analysis,
                )
                piano_notes = humanize(piano_notes, timing_jitter=0.012)
                section_notes["piano"] = piano_notes
            except Exception as e:
                logger.warning("[planner] Piano gen failed (section=%s): %s", label, e)

        # ── Strings ───────────────────────────────────────────────────────────
        if "strings" in plan.active_instruments:
            try:
                string_notes = generate_string_pad(
                    section_chords, style=style_id, analysis=section_analysis,
                )
                section_notes["strings"] = string_notes
            except Exception as e:
                logger.warning("[planner] Strings gen failed (section=%s): %s", label, e)

        # ── Guitar ────────────────────────────────────────────────────────────
        if "guitar" in plan.active_instruments:
            try:
                guitar_notes = generate_guitar_strum(
                    section_chords, style=style_id,
                    beat_grid=section_beats, analysis=section_analysis,
                )
                guitar_notes = humanize(guitar_notes, timing_jitter=0.015)
                section_notes["guitar"] = guitar_notes
            except Exception as e:
                logger.warning("[planner] Guitar gen failed (section=%s): %s", label, e)

        # ── Synth lead / other ────────────────────────────────────────────────
        if "synth_lead" in plan.active_instruments:
            try:
                lead_notes = generate_melody_line(
                    section_chords, style=style_id,
                    beat_grid=section_beats, analysis=section_analysis,
                )
                section_notes["synth_lead"] = lead_notes
            except Exception as e:
                logger.warning("[planner] Synth lead gen failed (section=%s): %s", label, e)

        # Add to tracks
        for inst, notes in section_notes.items():
            _add_notes_to_tracks(tracks, inst, notes, plan, i)

        # Cache first occurrence of each group
        if plan.group_id is not None and plan.group_id not in processed_groups:
            processed_groups[plan.group_id] = {
                "template_start": seg_start,
                "notes": section_notes,
            }

    logger.info(
        "[planner] Rendered: %d tracks, %.1fs",
        len(tracks), total_dur,
    )

    return {
        "tracks":               tracks,
        "totalDurationSeconds": total_dur,
        "source":               "two_stage_planner_v1",
        "plannerMetadata": {
            "style":           blueprint.style_id,
            "sections":        len(blueprint.section_plans),
            "globalInstruments": blueprint.global_instruments,
            "energyRange":     list(blueprint.energy_range),
        },
    }


def _add_notes_to_tracks(
    tracks: List[Dict],
    instrument: str,
    notes: List[Dict],
    plan: SectionPlan,
    section_idx: int,
) -> None:
    """Add a note list to the tracks, merging into existing instrument track or creating new."""
    if not notes:
        return

    # Find existing track for this instrument
    for track in tracks:
        if track.get("instrument") == instrument:
            track.setdefault("notes", []).extend(notes)
            return

    # Create new track
    _CHANNEL_MAP = {
        "drums":     9,
        "bass":      1,
        "piano":     0,
        "keys":      0,
        "guitar":    2,
        "strings":   3,
        "synth_lead": 4,
        "brass":     5,
        "pads":      6,
    }
    vol = float(plan.instrument_volumes.get(instrument, 1.0))

    tracks.append({
        "instrument": instrument,
        "channel":    _CHANNEL_MAP.get(instrument, section_idx % 15),
        "notes":      list(notes),
        "volume":     vol,
        "sectionLabel": plan.section_label,
    })


# ─── Convenience: full two-stage pipeline ─────────────────────────────────────

def generate_arrangement_two_stage(
    analysis: Dict[str, Any],
    style_id: str = "pop",
    override_instruments: Optional[Dict[str, List[str]]] = None,
    override_density: Optional[float] = None,
    # Legacy / route-compat params — accepted but may be superseded by style_spec
    instruments: Optional[List[str]] = None,
    density: Optional[float] = None,
    do_humanize: bool = True,
    tempo_factor: float = 1.0,
    persona_id: Optional[str] = None,
    style_profile: Optional[Dict] = None,
    humanize_seed: int = 42,
    evaluate: bool = True,
) -> Dict[str, Any]:
    """
    Run the complete two-stage arrangement pipeline.

    Stage 1: plan_arrangement  → ArrangementBlueprint
    Stage 2: render_blueprint  → track data
    Stage 3: humanize_tracks   → musical feel (deterministic, seed-based)
    Stage 4: evaluate          → arrangement quality report

    Returns:
        Arrangement dict with tracks, metadata, planner blueprint summary,
        and evaluation report.
    """
    chord_data  = analysis.get("chords", {})
    rhythm_data = analysis.get("rhythm", {})

    # Normalize chord key names: analysis uses "start"/"end", arranger uses "startTime"/"endTime"
    raw_chords = list(chord_data.get("chords", []))
    chord_timeline = []
    for c in raw_chords:
        nc = dict(c)
        if "start" in nc and "startTime" not in nc:
            nc["startTime"] = nc["start"]
        if "end" in nc and "endTime" not in nc:
            nc["endTime"] = nc["end"]
        chord_timeline.append(nc)

    beat_grid = list(rhythm_data.get("beats", []))
    bpm = float(rhythm_data.get("bpm", 120.0))

    # Merge density / instruments params
    effective_density = override_density or density
    effective_instruments = override_instruments

    # ── Stage 1: Structural planner ──────────────────────────────────────────

    # Enrich with formal style spec if available
    try:
        from orchestration.style_spec import get_planner_inputs
        spec_inputs = get_planner_inputs(style_id)
        # Override instruments from spec if not explicitly provided
        if not instruments and not override_instruments:
            spec_instrs = spec_inputs.get("instruments", [])
            if spec_instrs:
                effective_instruments = None  # let planner use spec defaults
        # Override density from spec if not set
        if effective_density is None:
            pass  # planner derives from energy
    except Exception as spec_err:
        logger.debug("style_spec lookup skipped: %s", spec_err)

    blueprint = plan_arrangement(
        analysis=analysis,
        style_id=style_id,
        override_instruments=effective_instruments,
        override_density=effective_density,
    )

    # ── Stage 2: Symbolic generator ──────────────────────────────────────────
    result = render_blueprint(
        blueprint=blueprint,
        chord_timeline=chord_timeline,
        beat_grid=beat_grid,
        analysis=analysis,
    )

    tracks = result.get("tracks", [])

    # ── Stage 3: Deterministic humanization ──────────────────────────────────
    if do_humanize and tracks:
        try:
            from orchestration.humanizer import humanize_tracks, make_humanizer_config
            h_config = make_humanizer_config(
                seed=humanize_seed,
                style=style_id,
                bpm=bpm,
                analysis=analysis,
            )
            tracks = humanize_tracks(tracks, h_config, analysis)
            result["tracks"] = tracks
            result["humanized"] = True
            result["humanizerSeed"] = humanize_seed
        except Exception as hz_err:
            logger.warning("Humanizer failed (non-fatal): %s", hz_err)

    # ── Stage 4: Arrangement quality evaluation ───────────────────────────────
    eval_report_dict: Dict[str, Any] = {}
    if evaluate and tracks:
        try:
            from orchestration.arrangement_evaluator import evaluate_arrangement
            eval_report = evaluate_arrangement(tracks, analysis, {
                "density": effective_density or blueprint.harmonic_density,
            })
            eval_report_dict = {
                "overallScore": eval_report.overall_score,
                "grade": eval_report.grade,
                "metrics": [
                    {"name": m.name, "score": m.score, "details": m.details}
                    for m in eval_report.metrics
                ],
                "issueCount": len(eval_report.issues),
                "warnings": eval_report.warnings,
            }
            logger.info(
                "Arrangement evaluation: score=%.3f grade=%s",
                eval_report.overall_score, eval_report.grade,
            )
        except Exception as ev_err:
            logger.warning("Arrangement evaluator failed (non-fatal): %s", ev_err)

    # ── Build final result ────────────────────────────────────────────────────
    result["blueprintSummary"] = {
        "styleId":            blueprint.style_id,
        "globalInstruments":  blueprint.global_instruments,
        "harmonicDensity":    blueprint.harmonic_density,
        "diatonicRatio":      blueprint.diatonic_ratio,
        "sectionCount":       len(blueprint.section_plans),
        "plannerVersion":     "two_stage_v2",
        "humanized":          do_humanize,
        "humanizerSeed":      humanize_seed if do_humanize else None,
        "evaluationScore":    eval_report_dict.get("overallScore"),
        "evaluationGrade":    eval_report_dict.get("grade"),
    }

    if eval_report_dict:
        result["evaluationReport"] = eval_report_dict

    return result
