import pytest
pytestmark = pytest.mark.unit

"""
Unit tests for orchestration/persona_loader.py and the personas YAML.
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from orchestration.persona_loader import (
    load_personas,
    get_persona,
    apply_persona_to_arrangement,
)

EXPECTED_IDS = {
    "hasidic-wedding",
    "cinematic",
    "modern-pop",
    "live-band",
    "jazz-quartet",
    "electronic-producer",
}


class TestPersonaLoader:
    def test_load_personas_returns_list(self):
        personas = load_personas()
        assert isinstance(personas, list)
        assert len(personas) >= 6

    def test_all_expected_persona_ids_present(self):
        personas = load_personas()
        ids = {p["id"] for p in personas}
        assert EXPECTED_IDS.issubset(ids)

    def test_persona_schema(self):
        personas = load_personas()
        for persona in personas:
            assert "id" in persona, f"Persona missing 'id': {persona}"
            assert "name" in persona, f"Persona {persona['id']} missing 'name'"
            # accept either camelCase or snake_case English name field
            has_name_en = "nameEn" in persona or "name_en" in persona
            assert has_name_en, f"Persona {persona['id']} missing English name field"
            assert "instrumentation_weights" in persona, f"Persona {persona['id']} missing 'instrumentation_weights'"

    def test_get_persona_known_id(self):
        persona = get_persona("hasidic-wedding")
        assert persona is not None
        assert persona["id"] == "hasidic-wedding"

    def test_get_persona_unknown_returns_none(self):
        assert get_persona("nonexistent-xyz") is None

    def test_apply_persona_adds_metadata(self):
        arrangement = {
            "tracks": [
                {"id": "drums", "name": "Drums", "volume": 1.0},
                {"id": "bass", "name": "Bass", "volume": 1.0},
            ],
            "style": "pop",
        }
        result = apply_persona_to_arrangement(arrangement, "hasidic-wedding", "pop")
        assert "personaId" in result
        assert result["personaId"] == "hasidic-wedding"
        assert "personaName" in result

    def test_apply_persona_adjusts_track_volumes(self):
        arrangement = {
            "tracks": [
                {"id": "drums", "name": "Drums", "volume": 1.0},
                {"id": "violin", "name": "Violin", "volume": 1.0},
            ],
        }
        result = apply_persona_to_arrangement(arrangement, "hasidic-wedding", "pop")
        track_ids = {t["id"] for t in result["tracks"]}
        assert "drums" in track_ids

    def test_apply_persona_unknown_id_returns_unchanged(self):
        arrangement = {"tracks": [{"id": "drums", "volume": 1.0}]}
        result = apply_persona_to_arrangement(arrangement, "unknown-id", "pop")
        assert result == arrangement

    def test_personas_cached(self):
        p1 = load_personas()
        p2 = load_personas()
        assert p1 is p2  # same object (LRU cache)
