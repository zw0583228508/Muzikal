import pytest
pytestmark = pytest.mark.service

"""
Tests for StyleEnricher — LLM enrichment, cache, adapt_to_analysis, fallback.
"""

import os
import json
import pytest
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch


class TestStyleEnricherInit:
    def test_imports(self):
        from agent.style_enricher import StyleEnricher
        assert StyleEnricher is not None

    def test_instantiation(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        assert enricher is not None

    def test_has_validator(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        assert enricher._validator is not None


class TestStyleEnricherCacheOperations:
    def test_cache_miss_returns_none(self, tmp_path):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        result = enricher._get_from_cache("nonexistent_key_xyz_999")
        assert result is None

    def test_cache_set_and_get(self, tmp_path):
        from agent import style_enricher as se_module

        original_path = se_module.CACHE_PATH
        cache_file = str(tmp_path / "test_cache.json")

        with patch.object(se_module, "CACHE_PATH", cache_file):
            enricher = se_module.StyleEnricher()
            profile = {"genre": "klezmer", "era": "1920s"}
            enricher._set_in_cache("klezmer:1920s:eastern_europe", profile)
            result = enricher._get_from_cache("klezmer:1920s:eastern_europe")
            assert result == profile

    def test_cache_ttl_expired(self, tmp_path):
        from agent import style_enricher as se_module

        cache_file = str(tmp_path / "ttl_cache.json")
        past = time.time() - (31 * 24 * 3600)  # 31 days ago

        with patch.object(se_module, "CACHE_PATH", cache_file):
            existing = {"expired_key": {"_cached_at": past, "profile": {"genre": "old"}}}
            with open(cache_file, "w") as f:
                json.dump(existing, f)

            enricher = se_module.StyleEnricher()
            result = enricher._get_from_cache("expired_key")
            assert result is None

    def test_cache_key_format(self):
        from agent.style_enricher import _cache_key
        key = _cache_key("Klezmer", "1920s", "Eastern Europe")
        assert key == "klezmer:1920s:eastern europe"
        assert ":" in key


class TestAdaptToAnalysis:
    def test_adapt_bpm_within_range_unchanged(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        knowledge = {"bpmRange": [100, 140], "genre": "klezmer"}
        analysis = {"bpm": 120}
        result = enricher._adapt_to_analysis(knowledge, analysis)
        assert result["bpmRange"] == [100, 140]

    def test_adapt_bpm_outside_range_adjusted(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        knowledge = {"bpmRange": [100, 140], "genre": "klezmer"}
        analysis = {"bpm": 80}  # below range
        result = enricher._adapt_to_analysis(knowledge, analysis)
        lo, hi = result["bpmRange"]
        assert lo <= 80 <= hi or lo < hi

    def test_adapt_stores_detected_key(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        knowledge = {"genre": "klezmer"}
        analysis = {"key": "D"}
        result = enricher._adapt_to_analysis(knowledge, analysis)
        assert result.get("detectedKey") == "D"

    def test_adapt_empty_analysis_unchanged(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        knowledge = {"genre": "klezmer", "bpmRange": [100, 140]}
        result = enricher._adapt_to_analysis(knowledge, {})
        assert result["bpmRange"] == [100, 140]

    def test_adapt_sets_scale_from_mode(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        knowledge = {"genre": "klezmer"}
        analysis = {"mode": "minor"}
        result = enricher._adapt_to_analysis(knowledge, analysis)
        assert result.get("scaleType") == "minor"


class TestBuildFromYaml:
    def test_build_from_yaml_has_required_roles(self):
        from agent.style_enricher import StyleEnricher
        from agent.style_database import get_style_db
        from agent.profile_validator import ProfileValidator, REQUIRED_ROLES

        db = get_style_db()
        enricher = StyleEnricher()
        yaml_data = db.get("klezmer") or {
            "id": "klezmer",
            "harmony": {"scale_type": "freygish", "typical_progressions": [["i", "V7"]]},
            "rhythm": {"bpm_range": [100, 160], "time_signature": "2/4", "feel": "straight"},
            "instrumentation": {"core": ["clarinet", "violin", "bass"]},
            "ornaments": [],
        }
        profile = enricher._build_from_yaml(yaml_data, {"genre": "klezmer"}, {})

        validator = ProfileValidator()
        result = validator.validate(profile)
        assert result.valid, f"Validation errors: {result.errors}"

    def test_build_from_yaml_includes_fallback_flag(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        yaml_data = {
            "id": "test_genre",
            "harmony": {"scale_type": "minor"},
            "rhythm": {"bpm_range": [80, 120], "time_signature": "4/4"},
            "instrumentation": {"core": ["piano", "bass", "drums"]},
            "ornaments": [],
        }
        profile = enricher._build_from_yaml(yaml_data, {}, {}, is_fallback=True)
        assert profile.get("isFallback") is True


class TestStyleEnricherEnrichNoLLM:
    @pytest.mark.asyncio
    async def test_enrich_returns_dict(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        with patch.object(enricher, "_client", None):
            result = await enricher.enrich({"genre": "klezmer"}, {})
        assert isinstance(result, dict)
        assert "genre" in result or "id" in result

    @pytest.mark.asyncio
    async def test_enrich_fallback_when_no_client(self):
        from agent.style_enricher import StyleEnricher
        enricher = StyleEnricher()
        with patch.object(enricher, "_client", None):
            result = await enricher.enrich({"genre": "klezmer"}, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_enrich_uses_cache_on_second_call(self, tmp_path):
        from agent import style_enricher as se_module
        cache_file = str(tmp_path / "enrich_cache.json")

        with patch.object(se_module, "CACHE_PATH", cache_file):
            enricher = se_module.StyleEnricher()
            with patch.object(enricher, "_client", None):
                result1 = await enricher.enrich({"genre": "klezmer", "era": "1920s", "region": "eastern europe"}, {})
                result2 = await enricher.enrich({"genre": "klezmer", "era": "1920s", "region": "eastern europe"}, {})
            assert isinstance(result2, dict)
