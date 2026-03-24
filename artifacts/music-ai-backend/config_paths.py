"""
Canonical config paths for the Python audio backend.

Single source of truth — all loaders import from here.
Never compute config paths independently in other modules.
"""

import os

# Backend root = directory containing api/, audio/, orchestration/, agent/, etc.
# This file lives at the backend root, so __file__ gives us the location directly.
BACKEND_ROOT: str = os.path.abspath(os.path.dirname(__file__))

# ── configs/styles/ ────────────────────────────────────────────────────────────
CONFIGS_DIR: str = os.path.join(BACKEND_ROOT, "configs", "styles")
GENRES_YAML: str = os.path.join(CONFIGS_DIR, "genres.yaml")
ARRANGER_PROFILES_YAML: str = os.path.join(CONFIGS_DIR, "arranger_profiles.yaml")
GENRES_DIR: str = os.path.join(CONFIGS_DIR, "genres")

# ── orchestration/ ─────────────────────────────────────────────────────────────
PERSONAS_YAML: str = os.path.join(BACKEND_ROOT, "orchestration", "arranger_personas.yaml")
