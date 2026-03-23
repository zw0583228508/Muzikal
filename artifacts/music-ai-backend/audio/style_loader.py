"""
Style loader — reads from the canonical YAML config.
Both Python and Node.js must load styles from this single source of truth.
"""

import os
import logging
from functools import lru_cache
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Locate the YAML file relative to workspace root
_WORKSPACE_ROOT = os.environ.get(
    "WORKSPACE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)
_STYLES_YAML = os.path.join(_WORKSPACE_ROOT, "configs", "styles", "genres.yaml")


@lru_cache(maxsize=1)
def load_styles() -> List[Dict[str, Any]]:
    """Load style definitions from configs/styles/genres.yaml.

    Results are cached — restart the process to pick up YAML changes.
    Falls back to a hardcoded minimal list if the YAML cannot be read.
    """
    try:
        import yaml  # pyyaml

        with open(_STYLES_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        styles = data.get("styles", [])
        logger.info(f"Loaded {len(styles)} styles from {_STYLES_YAML}")
        return styles
    except Exception as exc:
        logger.warning(f"Could not load styles YAML ({exc}); using minimal fallback")
        return _FALLBACK_STYLES


def get_styles_dict() -> Dict[str, Dict[str, Any]]:
    """Return styles keyed by id for quick lookup."""
    return {s["id"]: s for s in load_styles()}


def get_style(style_id: str) -> Dict[str, Any]:
    """Return a single style by id, or the 'pop' default if not found."""
    return get_styles_dict().get(style_id, get_styles_dict().get("pop", {}))


# Minimal fallback in case the YAML file is unavailable at runtime
_FALLBACK_STYLES = [
    {"id": "pop", "name": "Pop", "genre": "Pop", "density_default": 0.75,
     "instrumentation": ["piano", "strings", "bass", "drums"]},
    {"id": "jazz", "name": "Jazz", "genre": "Jazz", "density_default": 0.65,
     "instrumentation": ["piano", "double_bass", "drums", "trumpet"]},
    {"id": "hasidic", "name": "חסידי / Hasidic", "genre": "Hasidic", "density_default": 0.70,
     "instrumentation": ["violin", "clarinet", "accordion", "double_bass"]},
    {"id": "middle_eastern", "name": "מזרחי / Middle Eastern", "genre": "Middle Eastern", "density_default": 0.68,
     "instrumentation": ["oud", "darbuka", "violin", "qanun"]},
]
