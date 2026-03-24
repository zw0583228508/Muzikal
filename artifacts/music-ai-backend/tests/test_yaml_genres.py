"""
Tests for YAML genre files in configs/styles/genres/.
Validates structure, required fields, and data integrity.
"""

import pytest
pytestmark = pytest.mark.service

import os
import glob
import yaml

from config_paths import GENRES_DIR


def load_all_genres():
    pattern = os.path.join(GENRES_DIR, "*.yaml")
    genres = []
    for path in glob.glob(pattern):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        genres.append((os.path.basename(path), data))
    return genres


ALL_GENRES = load_all_genres()
GENRE_IDS = [g[1]["id"] for g in ALL_GENRES if "id" in g[1]]

EXPECTED_GENRES = [
    "klezmer",
    "bossa_nova",
    "flamenco",
    "maqam_hijaz",
    "afrobeat",
    "hasidic_nigun",
    "tango",
    "jazz_bebop",
    "celtic",
    "sephardic",
    "generic_world_music",
]


class TestYamlGenresExist:
    def test_genres_dir_exists(self):
        assert os.path.isdir(GENRES_DIR), f"genres dir missing: {GENRES_DIR}"

    def test_at_least_5_genre_files(self):
        assert len(ALL_GENRES) >= 5, f"Expected >= 5 genre files, found {len(ALL_GENRES)}"

    @pytest.mark.parametrize("genre_id", EXPECTED_GENRES)
    def test_expected_genre_present(self, genre_id):
        assert genre_id in GENRE_IDS, f"Genre '{genre_id}' not found in genres dir"


class TestYamlGenreStructure:
    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_id(self, filename, data):
        assert "id" in data, f"{filename}: missing 'id' field"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_display_name(self, filename, data):
        assert "display_name" in data, f"{filename}: missing 'display_name'"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_region(self, filename, data):
        assert "region" in data, f"{filename}: missing 'region'"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_harmony(self, filename, data):
        if data.get("is_fallback"):
            pytest.skip("fallback genres relax harmony requirement")
        assert "harmony" in data, f"{filename}: missing 'harmony' section"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_rhythm(self, filename, data):
        assert "rhythm" in data, f"{filename}: missing 'rhythm' section"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_bpm_range_is_valid(self, filename, data):
        rhythm = data.get("rhythm", {})
        bpm = rhythm.get("bpm_range")
        if bpm is None:
            return
        assert isinstance(bpm, list) and len(bpm) == 2, f"{filename}: bpm_range must be [min, max]"
        assert bpm[0] < bpm[1], f"{filename}: bpm_range[0] must be < bpm_range[1]"
        assert bpm[0] >= 20, f"{filename}: bpm_range[0] unrealistically low"
        assert bpm[1] <= 400, f"{filename}: bpm_range[1] unrealistically high"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_instrumentation(self, filename, data):
        assert "instrumentation" in data, f"{filename}: missing 'instrumentation'"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_instrumentation_has_core(self, filename, data):
        inst = data.get("instrumentation", {})
        assert "core" in inst, f"{filename}: instrumentation must have 'core' list"
        assert isinstance(inst["core"], list) and len(inst["core"]) > 0, \
            f"{filename}: core instruments list must be non-empty"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_id_matches_filename(self, filename, data):
        stem = filename.replace(".yaml", "")
        genre_id = data.get("id", "")
        assert genre_id == stem, f"{filename}: id '{genre_id}' doesn't match filename stem '{stem}'"

    @pytest.mark.parametrize("filename,data", ALL_GENRES)
    def test_has_reference_artists(self, filename, data):
        if data.get("is_fallback"):
            pytest.skip("fallback genres skip reference artists")
        artists = data.get("reference_artists", [])
        assert isinstance(artists, list), f"{filename}: reference_artists must be a list"


class TestGenreHarmony:
    def _get_genre(self, genre_id: str):
        for _, data in ALL_GENRES:
            if data.get("id") == genre_id:
                return data
        return None

    def test_klezmer_scale_type(self):
        g = self._get_genre("klezmer")
        if not g:
            pytest.skip("klezmer not loaded")
        assert g["harmony"]["scale_type"] == "freygish"

    def test_bossa_nova_has_extended_harmony(self):
        g = self._get_genre("bossa_nova")
        if not g:
            pytest.skip("bossa_nova not loaded")
        assert g["harmony"].get("extended_harmony") is True

    def test_maqam_hijaz_has_microtones(self):
        g = self._get_genre("maqam_hijaz")
        if not g:
            pytest.skip("maqam_hijaz not loaded")
        assert g["harmony"].get("microtones") is True

    def test_jazz_bebop_high_bpm(self):
        g = self._get_genre("jazz_bebop")
        if not g:
            pytest.skip("jazz_bebop not loaded")
        bpm = g["rhythm"]["bpm_range"]
        assert bpm[0] >= 150, "Bebop BPM minimum should be >= 150"


class TestStyleDatabase:
    def test_style_db_loads_all_genres(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        genres = db.list_genres()
        assert len(genres) >= 5

    def test_style_db_get_existing(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        g = db.get("klezmer")
        assert g is not None
        assert g["id"] == "klezmer"

    def test_style_db_get_nonexistent_returns_none(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        assert db.get("nonexistent_xyz_123") is None

    def test_style_db_fallback(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        fb = db.get_fallback()
        assert fb is not None
        assert "id" in fb

    def test_style_db_search(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        results = db.search("klezmer")
        assert len(results) > 0
        assert any(r["id"] == "klezmer" for r in results)

    def test_style_db_get_all_returns_list(self):
        from agent.style_database import StyleDatabase
        db = StyleDatabase(GENRES_DIR)
        all_genres = db.get_all()
        assert isinstance(all_genres, list)
        assert len(all_genres) >= 5
