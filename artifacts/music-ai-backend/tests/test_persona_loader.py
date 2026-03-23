import pytest
pytestmark = pytest.mark.unit

"""
Tests for orchestration/persona_loader.py — YAML loading, validation, and lookup.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchestration.persona_loader import load_personas, get_persona


EXPECTED_PERSONA_IDS = [
    "hasidic-wedding",
    "cinematic",
    "modern-pop",
    "live-band",
    "jazz-quartet",
    "electronic-producer",
]


class TestLoadPersonas:
    def test_returns_list(self):
        personas = load_personas()
        assert isinstance(personas, list)

    def test_at_least_one_persona(self):
        personas = load_personas()
        assert len(personas) >= 1

    def test_all_six_personas_present(self):
        personas = load_personas()
        ids = [p["id"] for p in personas]
        for pid in EXPECTED_PERSONA_IDS:
            assert pid in ids, f"Missing persona: {pid}"

    def test_each_persona_has_id(self):
        for p in load_personas():
            assert "id" in p

    def test_each_persona_has_name(self):
        for p in load_personas():
            assert "name" in p or "label" in p

    def test_each_persona_has_description(self):
        for p in load_personas():
            assert "description" in p or "desc" in p or "name" in p

    def test_persona_ids_are_strings(self):
        for p in load_personas():
            assert isinstance(p["id"], str)

    def test_persona_ids_unique(self):
        personas = load_personas()
        ids = [p["id"] for p in personas]
        assert len(ids) == len(set(ids))

    def test_hasidic_wedding_present(self):
        personas = load_personas()
        ids = [p["id"] for p in personas]
        assert "hasidic-wedding" in ids

    def test_cinematic_present(self):
        personas = load_personas()
        ids = [p["id"] for p in personas]
        assert "cinematic" in ids


class TestGetPersona:
    def test_get_valid_persona(self):
        persona = get_persona("hasidic-wedding")
        assert persona is not None
        assert persona["id"] == "hasidic-wedding"

    def test_get_cinematic_persona(self):
        persona = get_persona("cinematic")
        assert persona["id"] == "cinematic"

    def test_get_nonexistent_returns_none(self):
        result = get_persona("nonexistent-persona-xyz")
        assert result is None

    def test_get_all_six_without_error(self):
        for pid in EXPECTED_PERSONA_IDS:
            persona = get_persona(pid)
            assert persona["id"] == pid

    def test_returned_persona_is_dict(self):
        persona = get_persona("modern-pop")
        assert isinstance(persona, dict)

    def test_persona_instruments_if_present(self):
        persona = get_persona("hasidic-wedding")
        if "instruments" in persona:
            assert isinstance(persona["instruments"], list)

    def test_persona_style_params_if_present(self):
        persona = get_persona("jazz-quartet")
        if "styleParams" in persona or "params" in persona:
            params = persona.get("styleParams", persona.get("params", {}))
            assert isinstance(params, dict)
