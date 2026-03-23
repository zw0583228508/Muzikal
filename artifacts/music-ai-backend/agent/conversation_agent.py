import json
import logging
import uuid
import os
from dataclasses import dataclass, field
from typing import Optional, Any
from .prompts import EXTRACTION_PROMPT, CLARIFICATION_QUESTIONS
from .style_database import StyleDatabase, get_style_db
from .style_enricher import StyleEnricher
from .profile_validator import ProfileValidator

logger = logging.getLogger(__name__)

# In-memory session store: session_id → ConversationAgent
_sessions: dict[str, "ConversationAgent"] = {}


def get_session(session_id: str) -> Optional["ConversationAgent"]:
    return _sessions.get(session_id)


def create_session() -> "ConversationAgent":
    agent = ConversationAgent()
    _sessions[agent.session_id] = agent
    return agent


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


@dataclass
class AgentResponse:
    type: str  # "question" | "ready" | "error"
    text: Optional[str] = None
    profile: Optional[dict] = None
    phase: str = "DISCOVERY"
    session_id: Optional[str] = None
    collected_params: dict = field(default_factory=dict)


REQUIRED_PARAMS = {"genre"}
ENRICHMENT_PARAMS = {"genre", "era"}


def _get_openai_client():
    try:
        from openai import AsyncOpenAI
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
        if not base_url:
            return None
        return AsyncOpenAI(base_url=base_url, api_key=api_key)
    except ImportError:
        return None


class ConversationAgent:
    """
    שלושה שלבים:
    DISCOVERY   — שאלות ממוקדות להבנת הסגנון
    ENRICHMENT  — שליפת מידע מוזיקולוגי מה-LLM
    EXECUTION   — בניית StyleProfile ושליחה לצינור
    """

    def __init__(self, style_db: Optional[StyleDatabase] = None):
        self.session_id: str = str(uuid.uuid4())
        self.history: list[dict] = []
        self.collected_params: dict = {}
        self.phase: str = "DISCOVERY"
        self.profile: Optional[dict] = None
        self._question_index: int = 0
        self._style_db = style_db or get_style_db()
        self._enricher = StyleEnricher(style_db=self._style_db)
        self._validator = ProfileValidator()
        self._client = _get_openai_client()

    async def process_message(
        self, user_msg: str, analysis: dict = {}
    ) -> AgentResponse:
        self.history.append({"role": "user", "content": user_msg})

        extracted = await self._extract_style_params(user_msg)
        self.collected_params.update({k: v for k, v in extracted.items() if v})

        if self._is_profile_complete():
            self.phase = "ENRICHMENT"
            try:
                profile = await self._enrich_and_build_profile(analysis)
                validation = self._validator.validate(profile)
                if not validation.valid:
                    logger.warning(f"Profile invalid: {validation.errors}")

                self.profile = profile
                self.phase = "EXECUTION"

                return AgentResponse(
                    type="ready",
                    profile=profile,
                    phase="EXECUTION",
                    session_id=self.session_id,
                    collected_params=self.collected_params,
                )
            except Exception as e:
                logger.error(f"Enrichment failed: {e}")
                return AgentResponse(
                    type="error",
                    text=f"שגיאה בבניית פרופיל הסגנון: {e}",
                    phase="ENRICHMENT",
                    session_id=self.session_id,
                    collected_params=self.collected_params,
                )

        question = self._next_clarification_question()
        self.history.append({"role": "assistant", "content": question})

        return AgentResponse(
            type="question",
            text=question,
            phase=self.phase,
            session_id=self.session_id,
            collected_params=self.collected_params,
        )

    async def _extract_style_params(self, text: str) -> dict:
        if not self._client:
            return self._extract_params_heuristic(text)

        prompt = EXTRACTION_PROMPT.format(
            text=text,
            known_genres=", ".join(self._style_db.list_genres()),
            current_params=json.dumps(self.collected_params, ensure_ascii=False),
        )
        try:
            response = await self._client.chat.completions.create(
                model="gpt-5-mini",
                max_completion_tokens=512,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract musical style parameters. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text_resp = response.choices[0].message.content or "{}"
            text_resp = text_resp.strip()
            if text_resp.startswith("```"):
                text_resp = text_resp.split("```")[1]
                if text_resp.startswith("json"):
                    text_resp = text_resp[4:]
            return json.loads(text_resp)
        except Exception as e:
            logger.warning(f"LLM extraction failed, using heuristic: {e}")
            return self._extract_params_heuristic(text)

    HEBREW_GENRE_ALIASES: dict[str, str] = {
        "קלזמר": "klezmer",
        "בוסה נובה": "bossa_nova",
        "פלמנקו": "flamenco",
        "חיג'אז": "maqam_hijaz",
        "מקאם": "maqam_hijaz",
        "אפרוביט": "afrobeat",
        "ניגון": "hasidic_nigun",
        "חסידי": "hasidic_nigun",
        "טנגו": "tango",
        "ג'אז": "jazz_bebop",
        "ביבופ": "jazz_bebop",
        "קלטי": "celtic",
        "ספרדי": "sephardic",
        "לדינו": "sephardic",
        "מזרחי": "maqam_hijaz",
    }

    def _extract_params_heuristic(self, text: str) -> dict:
        """Simple keyword-based extraction as fallback."""
        text_lower = text.lower()
        result = {}

        for heb_word, genre_id in self.HEBREW_GENRE_ALIASES.items():
            if heb_word in text:
                result["genre"] = genre_id
                break

        if "genre" not in result:
            known = self._style_db.list_genres()
            for genre in known:
                if genre.replace("_", " ") in text_lower or genre in text_lower:
                    result["genre"] = genre
                    break

        TEMPO_HINTS = {
            "מהיר": "fast", "fast": "fast", "quick": "fast",
            "אט": "slow", "slow": "slow", "רגוע": "slow",
            "בינוני": "medium", "medium": "medium",
        }
        for word, feel in TEMPO_HINTS.items():
            if word in text_lower:
                result["tempo_feel"] = feel
                break

        ERA_HINTS = ["1920", "1930", "1940", "1950", "1960", "1970", "1980", "1990", "2000", "2010"]
        for era in ERA_HINTS:
            if era in text:
                result["era"] = f"{era}s"
                break

        MOODS = {
            "חגיגי": "festive", "עצוב": "sad", "שמח": "joyful",
            "אנרגטי": "energetic", "אינטימי": "intimate",
            "festive": "festive", "sad": "sad", "joyful": "joyful",
        }
        for word, mood in MOODS.items():
            if word in text_lower:
                result["mood"] = mood
                break

        return result

    def _is_profile_complete(self) -> bool:
        return REQUIRED_PARAMS.issubset(self.collected_params.keys())

    def _next_clarification_question(self) -> str:
        idx = self._question_index % len(CLARIFICATION_QUESTIONS)
        self._question_index += 1
        return CLARIFICATION_QUESTIONS[idx]

    async def _enrich_and_build_profile(self, analysis: dict) -> dict:
        return await self._enricher.enrich(self.collected_params, analysis)

    def get_state(self) -> dict:
        return {
            "session_id": self.session_id,
            "phase": self.phase,
            "collected_params": self.collected_params,
            "history_length": len(self.history),
            "profile_ready": self.profile is not None,
        }
