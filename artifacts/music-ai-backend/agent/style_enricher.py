import json
import os
import time
import logging
from typing import Optional
from .prompts import ENRICHMENT_PROMPT
from .profile_validator import ProfileValidator, ValidationError
from .style_database import StyleDatabase, get_style_db

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "configs", "ai_knowledge_cache.json"
)
CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _cache_key(genre: str, era: str, region: str) -> str:
    return f"{genre.lower()}:{era.lower()}:{region.lower()}"


def _load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save AI cache: {e}")


def _get_openai_client():
    """Returns an OpenAI client pointed at Replit AI Integrations proxy."""
    try:
        from openai import AsyncOpenAI
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
        if not base_url:
            return None
        return AsyncOpenAI(base_url=base_url, api_key=api_key)
    except ImportError:
        return None


class StyleEnricher:
    """
    Pulls musicological knowledge from the LLM and converts it to a
    complete StyleProfile dict.  Results are cached for 30 days.
    """

    def __init__(self, style_db: Optional[StyleDatabase] = None):
        self._db = style_db or get_style_db()
        self._validator = ProfileValidator()
        self._client = _get_openai_client()

    async def enrich(self, partial: dict, analysis: dict = {}) -> dict:
        """
        Input:  partial params from conversation + audio analysis
        Output: complete StyleProfile dict (validated)
        """
        genre = partial.get("genre", "")
        era = partial.get("era", "contemporary")
        region = partial.get("region", "")

        cache_key = _cache_key(genre, era, region)
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"AI cache hit: {cache_key}")
            adapted = self._adapt_to_analysis(cached, analysis)
            return adapted

        base_yaml = self._db.get(genre) or self._db.get_fallback()

        raw = await self._query_llm(partial, base_yaml, analysis)

        if raw:
            self._set_in_cache(cache_key, raw)
            adapted = self._adapt_to_analysis(raw, analysis)
            return adapted

        logger.warning(f"LLM returned no data for {genre}; using YAML fallback")
        return self._build_from_yaml(base_yaml, partial, analysis, is_fallback=True)

    async def _query_llm(self, partial: dict, base_yaml: dict, analysis: dict) -> Optional[dict]:
        if not self._client:
            logger.warning("OpenAI client not configured — skipping LLM call")
            return None
        prompt = ENRICHMENT_PROMPT.format(
            genre=partial.get("genre", "unknown"),
            sub_style=partial.get("sub_style", ""),
            era=partial.get("era", ""),
            region=partial.get("region", ""),
            base_yaml=json.dumps(base_yaml, ensure_ascii=False),
            user_prefs=json.dumps(partial, ensure_ascii=False),
            analysis_data=json.dumps(analysis, ensure_ascii=False),
        )
        try:
            response = await self._client.chat.completions.create(
                model="gpt-5-mini",
                max_completion_tokens=2048,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert musicologist. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}")
            return None

    def _adapt_to_analysis(self, knowledge: dict, analysis: dict) -> dict:
        """
        Adapts BPM, key, and harmonic syntax to the actual song's analysis data.
        e.g. If song is in D minor and AI proposed Freygish,
        we transpose chord labels to key of D.
        """
        result = dict(knowledge)

        if analysis:
            detected_bpm = analysis.get("bpm")
            if detected_bpm and "bpmRange" in result:
                lo, hi = result["bpmRange"]
                if not (lo <= detected_bpm <= hi):
                    margin = (hi - lo) / 2
                    result["bpmRange"] = [
                        max(40, detected_bpm - margin),
                        min(280, detected_bpm + margin),
                    ]

            detected_key = analysis.get("key")
            if detected_key:
                result["detectedKey"] = detected_key

            detected_mode = analysis.get("mode")
            if detected_mode and not result.get("scaleType"):
                result["scaleType"] = detected_mode

        return result

    def _validate_against_db(self, profile: dict) -> dict:
        result = self._validator.validate(profile)
        if not result.valid:
            logger.warning(f"Profile validation warnings: {result.errors}")
        return profile

    def _build_from_yaml(
        self, yaml_data: dict, partial: dict, analysis: dict, is_fallback: bool = False
    ) -> dict:
        """Build a StyleProfile from YAML data as fallback when LLM fails."""
        harmony = yaml_data.get("harmony", {})
        rhythm = yaml_data.get("rhythm", {})
        instrumentation = yaml_data.get("instrumentation", {})

        bpm_range = rhythm.get("bpm_range", [80, 120])

        instruments = []
        core_names = (instrumentation.get("core") or [])[:3]
        weights = [0.8, 0.6, 0.5]
        for idx, core_name in enumerate(core_names):
            instruments.append({
                "name": core_name,
                "role": "MELODY_LEAD",
                "midiProgram": 0,
                "volumeWeight": weights[idx],
                "panPosition": 0.0,
                "playingStyle": "legato",
                "patternRef": "default",
            })
        if not any(i["role"] == "BASS" for i in instruments):
            instruments.append({
                "name": "bass",
                "role": "BASS",
                "midiProgram": 32,
                "volumeWeight": 0.7,
                "panPosition": 0.0,
                "playingStyle": "legato",
                "patternRef": "bass_default",
            })
        if not any(i["role"] == "RHYTHM_KICK" for i in instruments):
            instruments.append({
                "name": "kick",
                "role": "RHYTHM_KICK",
                "midiProgram": 0,
                "volumeWeight": 0.7,
                "panPosition": 0.0,
                "playingStyle": "staccato",
                "patternRef": "kick_default",
            })
        if instruments:
            instruments[0]["role"] = "MELODY_LEAD"

        profile = {
            "genre": yaml_data.get("id", partial.get("genre", "generic")),
            "era": yaml_data.get("era", partial.get("era", "contemporary")),
            "subStyle": partial.get("sub_style", ""),
            "region": yaml_data.get("region", partial.get("region", "")),
            "scaleType": harmony.get("scale_type", "minor"),
            "chordVocabulary": (harmony.get("typical_progressions") or [["i", "iv", "V7"]])[0],
            "progressionPatterns": harmony.get("typical_progressions", [["i", "iv", "V7", "i"]]),
            "modulationTendency": "rare",
            "timeSignature": rhythm.get("time_signature", "4/4"),
            "bpmRange": bpm_range,
            "rhythmPattern": rhythm.get("feel", "straight"),
            "swingFactor": 0.0,
            "grooveTemplate": "on_top",
            "instruments": instruments,
            "voicingStyle": "open",
            "textureType": "layered",
            "sectionLabels": ["Intro", "Verse", "Chorus", "Outro"],
            "formTemplate": "AABA",
            "repeatStyle": "with_variation",
            "ornamentStyle": (yaml_data.get("ornaments") or [{}])[0].get("type", "none"),
            "dynamicsProfile": "mp_to_f",
            "reverbRoom": "chamber",
            "humanizationLevel": 0.7,
            "isFallback": is_fallback,
        }
        return self._adapt_to_analysis(profile, analysis)

    def _get_from_cache(self, key: str) -> Optional[dict]:
        cache = _load_cache()
        entry = cache.get(key)
        if not entry:
            return None
        ts = entry.get("_cached_at", 0)
        if time.time() - ts > CACHE_TTL_SECONDS:
            return None
        return entry.get("profile")

    def _set_in_cache(self, key: str, profile: dict) -> None:
        cache = _load_cache()
        cache[key] = {"_cached_at": time.time(), "profile": profile}
        _save_cache(cache)
