"""
Agent API routes — ConversationAgent + StyleEnricher + StyleDatabase endpoints.
Mounted at /agent/* in main.py
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from agent.conversation_agent import (
    ConversationAgent,
    create_session,
    get_session,
    delete_session,
)
from agent.style_enricher import StyleEnricher
from agent.style_database import get_style_db
from agent.profile_validator import ProfileValidator

logger = logging.getLogger(__name__)
router = APIRouter()

_enricher = StyleEnricher()
_validator = ProfileValidator()
_db = get_style_db()


# ─── Schemas ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    session_id: str
    project_id: Optional[str] = None


class EnrichRequest(BaseModel):
    genre: str
    era: Optional[str] = "contemporary"
    region: Optional[str] = ""
    sub_style: Optional[str] = ""
    analysis_data: Optional[dict] = {}


# ─── POST /agent/chat ────────────────────────────────────────────────────────

@router.post("/chat")
async def agent_chat(req: ChatRequest):
    """
    Send a message to the ConversationAgent.
    Creates a new session if session_id is not provided.
    Returns: { type: 'question'|'ready'|'error', text?, profile?, session_id, phase, collected_params }
    """
    if req.session_id:
        agent = get_session(req.session_id)
        if not agent:
            agent = create_session()
            logger.info(f"Session {req.session_id} not found, created new: {agent.session_id}")
    else:
        agent = create_session()

    analysis = {}
    response = await agent.process_message(req.message, analysis)

    return {
        "type": response.type,
        "text": response.text,
        "profile": response.profile,
        "phase": response.phase,
        "session_id": response.session_id or agent.session_id,
        "collected_params": response.collected_params,
    }


# ─── GET /agent/session/:id ──────────────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_agent_session(session_id: str):
    agent = get_session(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return agent.get_state()


# ─── POST /agent/confirm ─────────────────────────────────────────────────────

@router.post("/confirm")
async def confirm_profile(req: ConfirmRequest):
    agent = get_session(req.session_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")
    if not agent.profile:
        raise HTTPException(status_code=400, detail="Profile not ready yet; continue conversation")

    validation = _validator.validate(agent.profile)
    return {
        "confirmed": True,
        "profile": agent.profile,
        "valid": validation.valid,
        "warnings": validation.warnings,
        "errors": validation.errors,
        "session_id": req.session_id,
        "project_id": req.project_id,
        "message": "Profile confirmed. Send to arrangement pipeline.",
    }


# ─── GET /agent/genres ───────────────────────────────────────────────────────

@router.get("/genres")
async def list_genres():
    genres = _db.get_all()
    return [
        {
            "id": g.get("id"),
            "displayName": g.get("display_name", g.get("id")),
            "era": g.get("era", ""),
            "region": g.get("region", ""),
            "parentGenre": g.get("parent_genre"),
            "scaleType": g.get("harmony", {}).get("scale_type", "minor"),
            "bpmRange": g.get("rhythm", {}).get("bpm_range", [80, 120]),
            "timeSignature": g.get("rhythm", {}).get("time_signature", "4/4"),
            "coreInstruments": g.get("instrumentation", {}).get("core", []),
            "referenceArtists": g.get("reference_artists", []),
        }
        for g in genres
        if not g.get("is_fallback")
    ]


# ─── GET /agent/styles/:id/profile ──────────────────────────────────────────

@router.get("/styles/{genre_id}/profile")
async def get_genre_profile(genre_id: str):
    data = _db.get(genre_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Genre '{genre_id}' not found")
    return data


# ─── POST /agent/enrich ──────────────────────────────────────────────────────

@router.post("/enrich")
async def enrich_style(req: EnrichRequest):
    partial = {
        "genre": req.genre,
        "era": req.era,
        "region": req.region,
        "sub_style": req.sub_style,
    }
    try:
        profile = await _enricher.enrich(partial, req.analysis_data or {})
        validation = _validator.validate(profile)
        return {
            "profile": profile,
            "valid": validation.valid,
            "warnings": validation.warnings,
            "errors": validation.errors,
        }
    except Exception as e:
        logger.error(f"Enrich failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
