"""
Model Registry — Muzikal AI Pipeline.
Centralised list of every ML model used in the analysis and arrangement pipeline.
Returned verbatim by GET /python-api/models.
"""

from __future__ import annotations

MODEL_REGISTRY: list[dict] = [
    {
        "id": "madmom-beat-tracker",
        "name": "Madmom Beat Tracker",
        "version": "0.16.1",
        "task": "rhythm",
        "taskHe": "ריתמוס וטמפו",
        "description": "RNN-based beat and downbeat tracking using multi-model fusion.",
        "descriptionHe": "מעקב אחר קצב ודאון-ביט מבוסס RNN עם מיזוג מודלים מרובים.",
        "framework": "madmom",
        "license": "BSD-3-Clause",
        "inputType": "audio/float32",
        "outputType": "beat_grid",
        "latencyMs": 300,
        "isActive": True,
    },
    {
        "id": "essentia-tonal",
        "name": "Essentia Tonal Analyser",
        "version": "2.1b6",
        "task": "key",
        "taskHe": "מפתח ומוד",
        "description": "Krumhansl–Schmuckler key-finding algorithm with HPCP chroma.",
        "descriptionHe": "אלגוריתם קרומהנסל-שמוקלר לזיהוי מפתח עם HPCP כרומה.",
        "framework": "essentia",
        "license": "AGPL-3.0",
        "inputType": "audio/float32",
        "outputType": "key_mode",
        "latencyMs": 120,
        "isActive": True,
    },
    {
        "id": "chord-cnn",
        "name": "Chord CNN",
        "version": "0.4.0",
        "task": "chords",
        "taskHe": "אקורדים",
        "description": "Deep convolutional network for chord recognition with 170-class vocabulary.",
        "descriptionHe": "רשת קונבולוציה עמוקה לזיהוי אקורדים עם אוצר מילים של 170 מחלקות.",
        "framework": "pytorch",
        "license": "MIT",
        "inputType": "chroma/12",
        "outputType": "chord_sequence",
        "latencyMs": 450,
        "isActive": True,
    },
    {
        "id": "pyin-melody",
        "name": "pYIN Melody Extractor",
        "version": "0.1.1",
        "task": "melody",
        "taskHe": "מלודיה",
        "description": "Probabilistic YIN algorithm for monophonic pitch tracking.",
        "descriptionHe": "אלגוריתם YIN הסתברותי למעקב גובה צליל מונופוני.",
        "framework": "librosa",
        "license": "ISC",
        "inputType": "audio/float32",
        "outputType": "note_sequence",
        "latencyMs": 200,
        "isActive": True,
    },
    {
        "id": "msaf-structure",
        "name": "MSAF Structure Detector",
        "version": "0.5.0",
        "task": "structure",
        "taskHe": "מבנה שיר",
        "description": "Music Structure Analysis Framework — segment boundary detection.",
        "descriptionHe": "מסגרת לניתוח מבנה מוזיקלי — זיהוי גבולות סגמנטים.",
        "framework": "msaf",
        "license": "MIT",
        "inputType": "audio/float32",
        "outputType": "section_list",
        "latencyMs": 500,
        "isActive": True,
    },
    {
        "id": "demucs-htdemucs",
        "name": "Demucs HTDemucs",
        "version": "htdemucs-4.0",
        "task": "separation",
        "taskHe": "הפרדת גזעים",
        "description": "Hybrid Transformer Demucs — 4-stem (drums, bass, other, vocals) source separation.",
        "descriptionHe": "HTDemucs — הפרדת 4 גזעים (תופים, בס, אחר, ווקאלים) בשיטה היברידית.",
        "framework": "pytorch",
        "license": "MIT",
        "inputType": "audio/stereo",
        "outputType": "stems/4",
        "latencyMs": 8000,
        "isActive": True,
    },
    {
        "id": "crepe-vocal",
        "name": "CREPE Vocal Pitch",
        "version": "0.0.13",
        "task": "vocals",
        "taskHe": "אנליזת ווקאל",
        "description": "Convolutional pitch estimation for vocal analysis — 360-cent resolution.",
        "descriptionHe": "הערכת גובה קונבולוציונית לניתוח ווקאל — רזולוציה של 360 סנט.",
        "framework": "tensorflow",
        "license": "MIT",
        "inputType": "audio/mono",
        "outputType": "pitch_track",
        "latencyMs": 600,
        "isActive": True,
    },
]


def get_all_models() -> list[dict]:
    """Return the full registry."""
    return MODEL_REGISTRY


def get_model_by_task(task: str) -> dict | None:
    """Return the active model for a given task slug, or None."""
    for m in MODEL_REGISTRY:
        if m["task"] == task and m.get("isActive"):
            return m
    return None


def get_model_versions() -> dict[str, str]:
    """Return a mapping of task → version string (used by Node API layer)."""
    return {m["task"]: m["version"] for m in MODEL_REGISTRY if m.get("isActive")}
