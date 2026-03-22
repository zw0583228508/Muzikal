"""
Arranger Persona Loader — loads persona definitions from YAML.
Personas are abstract production personalities that overlay style profiles
to shape density, instrumentation weights, humanization, and transitions.
"""

import os
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = os.environ.get(
    "WORKSPACE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
)
_PERSONAS_YAML = os.path.join(
    os.path.dirname(__file__), "arranger_personas.yaml"
)


@lru_cache(maxsize=1)
def load_personas() -> List[Dict[str, Any]]:
    """Load all persona definitions from YAML. Results are LRU-cached."""
    try:
        import yaml
        with open(_PERSONAS_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        personas = data.get("personas", [])
        logger.info(f"Loaded {len(personas)} arranger personas")
        return personas
    except Exception as exc:
        logger.warning(f"Could not load personas YAML ({exc}); using minimal fallback")
        return _FALLBACK_PERSONAS


def get_personas_dict() -> Dict[str, Dict[str, Any]]:
    return {p["id"]: p for p in load_personas()}


def get_persona(persona_id: str) -> Optional[Dict[str, Any]]:
    """Return a persona by id, or None if not found."""
    return get_personas_dict().get(persona_id)


def apply_persona_to_arrangement(
    arrangement: Dict[str, Any],
    persona_id: Optional[str],
    style_id: str,
) -> Dict[str, Any]:
    """
    Apply persona adjustments to a finished arrangement dict.
    Modifies track volumes/densities and adds persona metadata.
    Returns the modified arrangement dict.
    """
    if not persona_id:
        return arrangement

    persona = get_persona(persona_id)
    if not persona:
        logger.warning(f"Unknown persona '{persona_id}' — skipping persona application")
        return arrangement

    weights = persona.get("instrumentation_weights", {})
    density_curve = persona.get("density_curve", {})

    # Scale track volumes by persona instrumentation weights
    for track in arrangement.get("tracks", []):
        inst = track.get("id", track.get("instrument", "")).lower()
        weight = weights.get(inst, 1.0)
        original_volume = track.get("volume", 0.7)
        track["volume"] = round(min(1.0, original_volume * weight), 3)

    # Add persona metadata to the arrangement
    arrangement["personaId"] = persona_id
    arrangement["personaName"] = persona.get("name_en", persona_id)
    arrangement["personaMetadata"] = {
        "humanization": persona.get("humanization", 0.5),
        "swing": persona.get("swing", 0.0),
        "articulation_bias": persona.get("articulation_bias", "natural"),
        "dynamics_shape": persona.get("dynamics_shape", "linear"),
        "transition_vocabulary": persona.get("transition_vocabulary", []),
        "tags": persona.get("tags", []),
    }

    logger.info(f"Applied persona '{persona_id}' to arrangement (style={style_id})")
    return arrangement


# Minimal fallback personas if YAML is unavailable
_FALLBACK_PERSONAS = [
    {
        "id": "modern-pop",
        "name": "פופ מודרני",
        "name_en": "Modern Pop Producer",
        "preferred_styles": ["pop"],
        "instrumentation_weights": {"drums": 1.2, "bass": 1.1, "piano": 1.0},
        "density_curve": {"intro": 0.4, "verse": 0.55, "chorus": 0.95, "outro": 0.3},
        "humanization": 0.4, "swing": 0.0,
        "transition_vocabulary": ["build", "drop"],
        "tags": ["polished", "commercial"],
    },
    {
        "id": "hasidic-wedding",
        "name": "חתונה חסידית",
        "name_en": "Hasidic Wedding",
        "preferred_styles": ["hasidic", "wedding"],
        "instrumentation_weights": {"violin": 1.4, "accordion": 1.3, "brass": 1.1},
        "density_curve": {"intro": 0.5, "verse": 0.75, "chorus": 1.0, "outro": 0.4},
        "humanization": 0.85, "swing": 0.0,
        "transition_vocabulary": ["build", "punch", "stop"],
        "tags": ["energetic", "celebratory", "ethnic"],
    },
]
