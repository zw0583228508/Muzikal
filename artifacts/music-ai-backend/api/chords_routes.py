"""Chord analysis and substitution endpoints."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chords/{chord_name}/substitutions")
async def chord_substitutions(chord_name: str, style: str = "pop"):
    """Return harmonic substitution suggestions for a given chord."""
    from audio.chords import get_chord_substitutions
    subs = get_chord_substitutions(chord_name, style=style)
    return {"chord": chord_name, "style": style, "substitutions": subs}
