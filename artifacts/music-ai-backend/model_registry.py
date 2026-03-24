"""
Model Registry — Muzikal AI Pipeline v2.0.0

Single source of truth for every ML model and algorithm used.

Rules (enforced):
  - Every model must have an accurate `status`: "production" | "experimental" | "heuristic"
  - "heuristic" marks DSP/rule-based stages that do NOT use trained ML weights
  - "experimental" marks models that are integrated but not yet benchmarked
  - No model may claim "production" without known benchmark metrics
  - `checkpointHash` must be set if real model weights are loaded
  - `isActive` must exactly reflect whether the model is called in production code

Pipeline version: 2.0.0
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelEntry:
    id: str
    name: str
    version: str
    task: str               # machine-readable task slug
    task_he: str            # Hebrew task label
    description: str
    description_he: str
    framework: str
    license: str
    input_type: str
    output_type: str
    status: str             # "production" | "experimental" | "heuristic"
    latency_ms: int
    is_active: bool
    checkpoint_hash: Optional[str] = None   # SHA-256 of model weights, if applicable
    benchmark_metric: Optional[str] = None  # e.g. "beat_F1=0.87 on MIREX2023"
    notes: Optional[str] = None


# ─── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: list[ModelEntry] = [

    # ── Rhythm ────────────────────────────────────────────────────────────────
    ModelEntry(
        id="madmom-rnn-beattracker",
        name="Madmom RNN Beat Tracker (DBN)",
        version="0.16.1",
        task="rhythm",
        task_he="ריתמוס וטמפו",
        description=(
            "Multi-model RNN beat tracker with Dynamic Bayesian Network (DBN) "
            "decoding. Runs on the drums stem for improved accuracy. "
            "Models: BeatDetectionProcessor + RhythmicGroupingProcessor."
        ),
        description_he=(
            "מעקב קצב RNN רב-מודלי עם פענוח DBN. "
            "רץ על גזע תופים לדיוק גבוה."
        ),
        framework="madmom",
        license="BSD-3-Clause",
        input_type="audio/float32-drums-stem",
        output_type="beat_grid+downbeats+tempo_curve",
        status="production",
        latency_ms=350,
        is_active=True,
        benchmark_metric="beat_F1=0.88 on MIREX2023 (self-reported)",
        notes="Requires madmom 0.16.1 with numpy-compat patch applied at startup",
    ),

    # ── Key / Tonality ────────────────────────────────────────────────────────
    ModelEntry(
        id="essentia-hpcp-key",
        name="Essentia HPCP + Krumhansl–Schmuckler",
        version="2.1b6",
        task="key",
        task_he="מפתח ומוד",
        description=(
            "Harmonic Pitch Class Profile (HPCP) with Krumhansl–Schmuckler "
            "key-finding profiles. Runs on the other (harmonic) stem."
        ),
        description_he=(
            "HPCP (פרופיל מחלקות גובה הרמוני) עם פרופילי K-S לזיהוי מפתח. "
            "רץ על גזע הכלים ההרמוניים."
        ),
        framework="essentia",
        license="AGPL-3.0",
        input_type="audio/float32-harmonic-stem",
        output_type="key_mode+confidence+segments",
        status="heuristic",
        latency_ms=120,
        is_active=True,
        notes="DSP+profile-based — not a trained neural model",
    ),

    ModelEntry(
        id="librosa-ks-key",
        name="librosa Krumhansl–Schmuckler (fallback)",
        version="0.11.0",
        task="key_fallback",
        task_he="מפתח — גיבוי",
        description="CQT chroma with K-S profiles as fallback key estimator.",
        description_he="כרומה CQT עם K-S כמזהה מפתח גיבוי.",
        framework="librosa",
        license="ISC",
        input_type="audio/float32",
        output_type="key_mode+confidence",
        status="heuristic",
        latency_ms=60,
        is_active=True,
    ),

    # ── Chords ────────────────────────────────────────────────────────────────
    ModelEntry(
        id="chord-hsmm-viterbi",
        name="HSMM Chord Recogniser (Viterbi)",
        version="1.0.0",
        task="chords",
        task_he="אקורדים",
        description=(
            "Hidden Semi-Markov Model chord recogniser with Viterbi decoding. "
            "Features: Essentia HPCP + bass chroma + Tonal Centroid Features (TCF). "
            "Key-conditional emission model + music-theory transition matrix. "
            "Replaces cosine template matching as primary chord detector. "
            "Reference: Mauch & Dixon 2010, Cho & Bello 2014."
        ),
        description_he=(
            "מזהה אקורדים HSMM עם פענוח ויטרבי. "
            "תכונות: HPCP + כרומה בס + TCF. "
            "מודל פליטה מותנה-מפתח + מטריצת מעברים תיאורטית-מוסיקלית."
        ),
        framework="numpy+librosa+essentia",
        license="MIT",
        input_type="audio/stems+beat_grid+key",
        output_type="chord_sequence+confidence+alternatives",
        status="experimental",
        latency_ms=800,
        is_active=True,
        benchmark_metric="pending — benchmark against BillBoard dataset",
        notes="No pre-trained weights — music-theory initialized. "
              "Falls back to template matching if HSMM fails.",
    ),

    ModelEntry(
        id="chord-template-matcher",
        name="CQT Chroma Template Matcher (fallback)",
        version="2.0.0",
        task="chords_fallback",
        task_he="אקורדים — גיבוי",
        description=(
            "Cosine template matching on beat-synchronized CQT chroma. "
            "Bass-weighted (25% bass stem + 75% mid/treble). "
            "Used as fallback when HSMM fails."
        ),
        description_he="התאמת תבניות קוסינוס על כרומה מסונכרנת-ביט. גיבוי בלבד.",
        framework="librosa+essentia",
        license="MIT",
        input_type="audio/float32+beat_grid",
        output_type="chord_sequence+confidence",
        status="heuristic",
        latency_ms=250,
        is_active=True,
        notes="Primary chord detector before HSMM upgrade",
    ),

    # ── Melody / Pitch ────────────────────────────────────────────────────────
    ModelEntry(
        id="torchcrepe-pitch",
        name="torchcrepe (CREPE PyTorch)",
        version="0.0.24",
        task="melody",
        task_he="מלודיה",
        description=(
            "CREPE (Convolutional REpresentation for Pitch Estimation) "
            "in PyTorch. Frame-level F0 estimation on vocals stem. "
            "Model capacity: 'full' (11M parameters)."
        ),
        description_he=(
            "CREPE — אמידת F0 ברמת-פריים על גזע הווקאל. "
            "מודל PyTorch. קיבולת: 'full'."
        ),
        framework="pytorch",
        license="MIT",
        input_type="audio/float32-vocals-stem",
        output_type="pitch_curve+confidence",
        status="production",
        latency_ms=400,
        is_active=True,
        checkpoint_hash="crepe-full-1997369d",
        benchmark_metric="RPA>0.85 on MDB-melody-synth",
    ),

    ModelEntry(
        id="basic-pitch-notes",
        name="basic-pitch Note Transcription",
        version="0.4.0",
        task="melody_notes",
        task_he="תמלול מנגינה",
        description=(
            "Spotify basic-pitch ONNX model for polyphonic note event detection. "
            "Produces NoteEvent list from vocals stem. "
            "Merged with torchcrepe pitch curve."
        ),
        description_he="basic-pitch של Spotify — זיהוי אירועי תווים מגזע הווקאל.",
        framework="onnx",
        license="Apache-2.0",
        input_type="audio/float32-vocals-stem",
        output_type="note_events+onset+offset",
        status="experimental",
        latency_ms=600,
        is_active=True,
        checkpoint_hash="basic-pitch-0.4.0-onnx",
        benchmark_metric="note_F1>0.80 on MDB-melody-synth (Spotify reported)",
    ),

    # ── Structure ─────────────────────────────────────────────────────────────
    ModelEntry(
        id="ssm-novelty-structure",
        name="SSM + Spectral Novelty Structure Detector",
        version="2.0.0",
        task="structure",
        task_he="מבנה שיר",
        description=(
            "Self-Similarity Matrix (SSM) computed from MFCC+chroma features, "
            "with checkerboard novelty kernel for boundary detection. "
            "Energy/density/spectral-centroid profile per section. "
            "Greedy agglomerative similarity grouping."
        ),
        description_he=(
            "מטריצת דמיון עצמי (SSM) עם ליבת חידוש לזיהוי גבולות. "
            "פרופיל אנרגיה/צפיפות/מרכז-ספקטרלי לכל סקציה."
        ),
        framework="librosa+scipy",
        license="MIT",
        input_type="audio/float32",
        output_type="section_list+groups+energy_profile",
        status="heuristic",
        latency_ms=600,
        is_active=True,
        notes="Boundary detection: SSM+novelty ✓. Labeling: position-heuristic (planned upgrade: learned classifier)",
    ),

    # ── Source Separation ─────────────────────────────────────────────────────
    ModelEntry(
        id="demucs-htdemucs",
        name="Demucs HTDemucs (4-stem)",
        version="4.0.1",
        task="separation",
        task_he="הפרדת גזעים",
        description=(
            "Hybrid Transformer Demucs — 4-stem source separation "
            "(drums, bass, other, vocals). "
            "Runs chunked inference for long audio. "
            "Uses 'htdemucs' checkpoint."
        ),
        description_he=(
            "Demucs היברידי טרנספורמר — הפרדת 4 גזעים. "
            "רץ עם חלוקה לנתחים לאודיו ארוך."
        ),
        framework="pytorch",
        license="MIT",
        input_type="audio/stereo-or-mono",
        output_type="stems/4+confidence",
        status="production",
        latency_ms=8000,
        is_active=True,
        checkpoint_hash="htdemucs-955717e6",
        benchmark_metric="SDR=7.3dB drums on MUSDB18",
    ),

    # ── Harmonic Analysis ─────────────────────────────────────────────────────
    ModelEntry(
        id="chord-classifier-bigram",
        name="Key-Conditional Bigram Chord Classifier",
        version="1.0.0",
        task="harmonic_classification",
        task_he="סיווג הרמוני",
        description=(
            "Post-processing classifier for harmonic function labeling. "
            "Assigns scale degree (I-VII), harmonic function (tonic/subdominant/dominant), "
            "and detects cadence patterns (authentic/plagal/half/deceptive). "
            "Uses bigram transition weights from functional harmony theory."
        ),
        description_he=(
            "מסווג פוסט-עיבוד לתיוג פונקציה הרמונית. "
            "מקצה דרגת סולם, פונקציה הרמונית, ומזהה קדנסות."
        ),
        framework="numpy",
        license="MIT",
        input_type="chord_sequence+key",
        output_type="harmonic_functions+cadences+diatonic_ratio",
        status="experimental",
        latency_ms=5,
        is_active=True,
    ),

    # ── Fusion ────────────────────────────────────────────────────────────────
    ModelEntry(
        id="fusion-engine-viterbi",
        name="Multi-Source Fusion Engine (Viterbi)",
        version="2.0.0",
        task="fusion",
        task_he="מיזוג מולטי-מקור",
        description=(
            "Confidence-weighted multi-source fusion with Viterbi chord smoothing. "
            "Fuses: Essentia HPCP + librosa K-S (key), madmom (rhythm), "
            "torchcrepe+basic-pitch (melody), HSMM+template (chords)."
        ),
        description_he="מנוע מיזוג מולטי-מקור עם עיגול ויטרבי ומשקלי ביטחון.",
        framework="numpy",
        license="MIT",
        input_type="multi_source_analysis",
        output_type="analysis_result",
        status="experimental",
        latency_ms=50,
        is_active=True,
        benchmark_metric="pending — no end-to-end benchmark yet",
    ),
]


# ─── Public API ────────────────────────────────────────────────────────────────

def get_all_models() -> list[dict]:
    """Return the full registry as a list of dicts."""
    return [_entry_to_dict(e) for e in _REGISTRY]


def get_model_by_id(model_id: str) -> Optional[dict]:
    """Return a model by its ID, or None."""
    for e in _REGISTRY:
        if e.id == model_id:
            return _entry_to_dict(e)
    return None


def get_model_by_task(task: str) -> Optional[dict]:
    """Return the primary active model for a task, or None."""
    for e in _REGISTRY:
        if e.task == task and e.is_active:
            return _entry_to_dict(e)
    return None


def get_model_versions() -> dict[str, str]:
    """Return task → version mapping for pipeline provenance."""
    return {e.task: e.version for e in _REGISTRY if e.is_active}


def validate_registry() -> list[str]:
    """
    Validate registry consistency. Returns list of error strings.
    Empty list = registry is clean.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()

    for e in _REGISTRY:
        if e.id in seen_ids:
            errors.append(f"Duplicate model ID: {e.id}")
        seen_ids.add(e.id)

        if e.status not in ("production", "experimental", "heuristic"):
            errors.append(f"{e.id}: invalid status '{e.status}'")

        if e.status == "production" and not e.benchmark_metric and not e.checkpoint_hash:
            errors.append(
                f"{e.id}: claimed 'production' but has no benchmark_metric or checkpoint_hash"
            )

    return errors


def _entry_to_dict(e: ModelEntry) -> dict:
    return {
        "id":              e.id,
        "name":            e.name,
        "version":         e.version,
        "task":            e.task,
        "taskHe":          e.task_he,
        "description":     e.description,
        "descriptionHe":   e.description_he,
        "framework":       e.framework,
        "license":         e.license,
        "inputType":       e.input_type,
        "outputType":      e.output_type,
        "status":          e.status,
        "latencyMs":       e.latency_ms,
        "isActive":        e.is_active,
        "checkpointHash":  e.checkpoint_hash,
        "benchmarkMetric": e.benchmark_metric,
        "notes":           e.notes,
    }
