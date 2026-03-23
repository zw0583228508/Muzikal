import os
import yaml
import glob
from typing import Optional
from functools import lru_cache

GENRES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "configs", "styles", "genres"
)

GENERIC_FALLBACK_ID = "generic_world_music"


class StyleDatabase:
    """Loads and indexes YAML genre files from configs/styles/genres/."""

    def __init__(self, genres_dir: str = GENRES_DIR):
        self._dir = genres_dir
        self._cache: dict = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        pattern = os.path.join(self._dir, "*.yaml")
        for path in glob.glob(pattern):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and "id" in data:
                    self._cache[data["id"]] = data
            except Exception:
                pass
        self._loaded = True

    def list_genres(self) -> list[str]:
        self._ensure_loaded()
        return list(self._cache.keys())

    def get(self, genre_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self._cache.get(genre_id)

    def get_all(self) -> list[dict]:
        self._ensure_loaded()
        return list(self._cache.values())

    def get_fallback(self) -> dict:
        self._ensure_loaded()
        return self._cache.get(GENERIC_FALLBACK_ID, {
            "id": GENERIC_FALLBACK_ID,
            "display_name": "World Music",
            "era": "Contemporary",
            "region": "Global",
            "isFallback": True,
        })

    def find_by_parent(self, parent_genre: str) -> list[dict]:
        self._ensure_loaded()
        return [
            g for g in self._cache.values()
            if g.get("parent_genre") == parent_genre
        ]

    def search(self, query: str) -> list[dict]:
        """Fuzzy search by display_name, id, region, parent_genre."""
        self._ensure_loaded()
        q = query.lower()
        results = []
        for genre in self._cache.values():
            fields = [
                genre.get("id") or "",
                genre.get("display_name") or "",
                genre.get("region") or "",
                genre.get("parent_genre") or "",
            ]
            if any(q in f.lower() for f in fields if f):
                results.append(genre)
        return results


@lru_cache(maxsize=1)
def get_style_db() -> StyleDatabase:
    return StyleDatabase()
