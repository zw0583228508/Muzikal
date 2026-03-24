"""Analysis pipeline endpoints — v2 (high-accuracy multi-stage pipeline).

Job stage lifecycle per spec:
  queued → running (stage tracking) → completed | failed | partial

Every stage update includes:
  - status
  - progress (0-100)
  - currentStep (human-readable)
  - currentStage (machine-readable)
  - modelUsed (which model is active)
  - qualityFlags (propagated from pipeline)
  - failureReason (on failure, machine-readable)
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks

from api.database import update_job, update_project_status, save_analysis_result, get_active_job_for_project, increment_job_retry
from api.schemas import AnalyzeRequest

logger = logging.getLogger(__name__)

router = APIRouter()

PIPELINE_VERSION = "2.0.0"

MODEL_VERSIONS = {
    "demucs":     "4.0.1-htdemucs",
    "madmom":     "0.16.1",
    "essentia":   "2.1b6",
    "torchcrepe": "0.0.24",
    "basicPitch": "0.4.0",
    "librosa":    "0.11.0",
}

# ─── Stage definitions ────────────────────────────────────────────────────────
# (progress_pct, stage_id, human_label, model_used)
STAGE_PREPROCESS   = (3,  "preprocess",     "Preprocessing audio",              "librosa")
STAGE_SEPARATE     = (10, "stem_separation","Separating stems (Demucs htdemucs)","demucs-4.0.1")
STAGE_BEATS        = (28, "beat_tracking",  "Tracking beats (madmom RNN+DBN)",   "madmom-0.16.1")
STAGE_KEY          = (38, "key_detection",  "Detecting key (Essentia HPCP)",     "essentia-2.1b6")
STAGE_CHORDS       = (52, "chord_detection","Detecting chords (CQT + bass)",     "essentia+librosa")
STAGE_MELODY       = (66, "melody",         "Extracting melody (crepe+basicpitch)","torchcrepe+basicpitch")
STAGE_STRUCTURE    = (75, "structure",      "Detecting structure (SSM)",         "librosa-ssm")
STAGE_SMOOTHING    = (82, "smoothing",      "Applying smoothing filters",        "internal")
STAGE_THEORY       = (87, "theory_correction","Applying theory corrections",     "internal")
STAGE_FUSION       = (91, "fusion",         "Fusing multi-source results",       "fusion-engine")
STAGE_GUARD        = (95, "theory_guard",   "Validating harmonic correctness",   "theory-guard")
STAGE_CONFIDENCE   = (97, "confidence",     "Scoring confidence",                "internal")
STAGE_CANONICAL    = (99, "canonical",      "Building canonical score",          "chord-classifier+canonical")


# ── Stage timing registry (in-process, per job_id) ────────────────────────────
_stage_timings: dict = {}  # {job_id: {stage_id: {"start": t, "end": t, "model": m}}}


def _stage_update(job_id: str, stage_tuple: tuple, extra_msg: str = "") -> None:
    """Emit a per-stage job update and record timing."""
    pct, stage_id, label, model = stage_tuple
    msg = f"{label}" + (f" — {extra_msg}" if extra_msg else "")
    now = time.time()

    # Record timing
    if job_id not in _stage_timings:
        _stage_timings[job_id] = {}
    timings = _stage_timings[job_id]

    # Close out previous stage if still open
    for prev_id, prev_t in timings.items():
        if "end" not in prev_t:
            prev_t["end"] = now
            prev_t["durationMs"] = round((now - prev_t["start"]) * 1000)

    timings[stage_id] = {"start": now, "model": model}

    try:
        update_job(
            job_id, "running", pct, msg,
            result_data={
                "currentStage":    stage_id,
                "modelUsed":       model,
                "pipelineVersion": PIPELINE_VERSION,
                "stageTimings":    dict(timings),
            },
            processing_metadata={
                "stageTimings": dict(timings),
            },
        )
    except Exception as e:
        logger.warning("Failed to update job stage %s: %s", stage_id, e)


def _finalize_stage_timings(job_id: str) -> dict:
    """Close last open stage and return full timing dict."""
    now = time.time()
    timings = _stage_timings.pop(job_id, {})
    for t in timings.values():
        if "end" not in t:
            t["end"] = now
            t["durationMs"] = round((now - t["start"]) * 1000)
    return timings


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/canonical")
async def get_canonical_score(project_id: int):
    """
    Return the Canonical Score for a project.

    The canonical score is a measure-by-measure symbolic representation
    (chord symbols, melody notes, section labels, harmonic functions)
    produced by Stage 12 of the analysis pipeline.

    Returns 404 if the project has not been analysed yet.
    Returns 202 if analysis is in progress (no canonical yet).
    """
    from fastapi import HTTPException
    from api.database import get_analysis_result

    data = get_analysis_result(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No analysis result found for this project")

    canonical = data.get("canonical")
    if canonical is None:
        raise HTTPException(
            status_code=202,
            detail="Analysis exists but canonical score not yet generated (re-analyse with pipeline v2.0.0+)",
        )

    return {
        "projectId":     project_id,
        "pipelineVersion": data.get("pipelineVersion"),
        "qualityFlags":  data.get("qualityFlags", []),
        "harmonicRhythm": data.get("harmonicRhythm"),
        "diatonicRatio": data.get("diatonicRatio"),
        "cadences":      data.get("cadences", []),
        "canonical":     canonical,
    }


@router.post("/analyze")
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start audio analysis pipeline in background (Celery if available, else in-process).

    Idempotency: if an analysis job is already running for this project,
    return that job instead of starting a new one.
    """
    from workers.tasks.analysis import dispatch_analysis

    # ── Idempotency guard ───────────────────────────────────────────────────
    active = get_active_job_for_project(request.project_id, "analysis")
    if active:
        logger.info(
            "Idempotency: analysis job %s already active for project %s — returning existing",
            active["jobId"], request.project_id,
        )
        return {
            "jobId": active["jobId"],
            "status": active["status"],
            "worker": "existing",
            "mode": request.mode,
            "pipelineVersion": PIPELINE_VERSION,
            "idempotent": True,
        }

    celery_task_id = dispatch_analysis(request.job_id, request.project_id, request.audio_file_path)
    if celery_task_id is None:
        background_tasks.add_task(
            run_analysis_pipeline,
            request.job_id,
            request.project_id,
            request.audio_file_path,
            request.mode,
        )
    return {
        "jobId": request.job_id,
        "status": "queued",
        "worker": "celery" if celery_task_id else "inprocess",
        "mode": request.mode,
        "pipelineVersion": PIPELINE_VERSION,
    }


def _compute_audio_fingerprint(audio_file_path: str) -> Optional[str]:
    """Compute SHA-256 fingerprint of audio file for cache keying.

    Returns hex string or None if file is unreadable.
    """
    try:
        h = hashlib.sha256()
        with open(audio_file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        logger.warning("Could not compute audio fingerprint: %s", exc)
        return None


def _check_analysis_cache(fingerprint: str) -> Optional[dict]:
    """Look up a prior analysis result by audio fingerprint.

    Returns the processing_metadata dict if found (so we can extract result info),
    or None if no cache hit.
    """
    try:
        from api.database import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT processing_metadata, pipeline_version
                       FROM analysis_results
                       WHERE processing_metadata->>'audioFingerprint' = %s
                       ORDER BY updated_at DESC
                       LIMIT 1""",
                    (fingerprint,),
                )
                row = cur.fetchone()
            if row is None:
                return None
            meta = row["processing_metadata"] or {}
            return {
                "found": True,
                "fingerprint": fingerprint,
                "pipelineVersion": row["pipeline_version"],
                "meta": meta if isinstance(meta, dict) else json.loads(meta),
            }
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Audio cache lookup failed (non-fatal): %s", exc)
        return None


def run_analysis_pipeline(
    job_id: str,
    project_id: int,
    audio_file_path: str,
    mode: str = "balanced",
) -> None:
    """
    Run the full analysis pipeline synchronously in a background thread.
    Emits per-stage status updates; never swallows exceptions silently.
    Falls back to the legacy audio.analyzer only if the primary pipeline fails,
    and marks the result clearly as a fallback.

    Audio hash cache: if the same audio file was previously analyzed (matched by
    SHA-256 fingerprint), re-uses the stored analysis and skips re-processing.
    """
    t_start = time.time()

    try:
        _stage_update(job_id, STAGE_PREPROCESS)
        update_project_status(project_id, "analyzing")

        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(
                f"Audio file not found: {audio_file_path}. "
                "Ensure the file was uploaded successfully before starting analysis."
            )

        # ── Audio fingerprint + cache check ────────────────────────────────
        fingerprint = _compute_audio_fingerprint(audio_file_path)
        if fingerprint:
            cache_hit = _check_analysis_cache(fingerprint)
            if cache_hit:
                elapsed = round(time.time() - t_start, 2)
                logger.info(
                    "[job=%s] Cache HIT — fingerprint=%s…%s — skipping re-analysis (%.1fs)",
                    job_id, fingerprint[:8], fingerprint[-4:], elapsed,
                )
                update_job(
                    job_id, "completed", 100,
                    "Analysis served from cache (same audio file detected)",
                    result_data={
                        "pipelineVersion": cache_hit["pipelineVersion"],
                        "fromCache": True,
                        "audioFingerprint": fingerprint,
                        "elapsedSeconds": elapsed,
                    },
                )
                update_project_status(project_id, "analyzed")
                return

        # ── Run new pipeline with stage callbacks ──────────────────────────
        result = _run_new_pipeline_staged(
            audio_file_path=audio_file_path,
            mode=mode,
            job_id=job_id,
        )

        # ── Save results ───────────────────────────────────────────────────
        audio_meta_raw = result.get("audioMeta", result.get("audio_meta", {}))
        from api.database import update_project_audio_metadata
        update_project_audio_metadata(project_id, {
            "duration_seconds": audio_meta_raw.get("duration"),
            "sample_rate":      audio_meta_raw.get("sample_rate"),
            "channels":         audio_meta_raw.get("channels", 1),
            "codec":            None,
        })

        # Embed fingerprint in processingMetadata so cache lookup works next time
        if fingerprint:
            pm = result.setdefault("processingMetadata", {})
            if isinstance(pm, dict):
                pm["audioFingerprint"] = fingerprint
            else:
                result["processingMetadata"] = {"audioFingerprint": fingerprint}

        save_analysis_result(project_id, result, pipeline_version=PIPELINE_VERSION)
        update_project_status(project_id, "analyzed")

        quality_flags = result.get("qualityFlags", [])
        elapsed = round(time.time() - t_start, 1)
        stage_timings = _finalize_stage_timings(job_id)

        update_job(
            job_id, "completed", 100,
            f"Analysis complete in {elapsed}s — confidence={result.get('globalConfidence', 0):.2f}",
            result_data={
                "pipelineVersion":   PIPELINE_VERSION,
                "mode":              mode,
                "duration":          audio_meta_raw.get("duration"),
                "globalConfidence":  result.get("globalConfidence", 0),
                "qualityFlags":      quality_flags,
                "modelVersions":     MODEL_VERSIONS,
                "elapsedSeconds":    elapsed,
                "stageTimings":      stage_timings,
            },
            processing_metadata={
                "stageTimings":  stage_timings,
                "elapsedSeconds": elapsed,
                "pipelineVersion": PIPELINE_VERSION,
            },
        )
        logger.info(
            "Analysis complete: project=%s mode=%s elapsed=%.1fs conf=%.2f flags=%s",
            project_id, mode, elapsed, result.get("globalConfidence", 0), quality_flags,
        )

    except Exception as e:
        elapsed = round(time.time() - t_start, 1)
        logger.exception(
            "Primary analysis pipeline failed for job=%s project=%s after %.1fs: %s",
            job_id, project_id, elapsed, e,
        )

        # ── Fallback to legacy pipeline ────────────────────────────────────
        try:
            retry_count = increment_job_retry(job_id)
            _finalize_stage_timings(job_id)  # clear stale timings
            logger.warning("[job=%s] Falling back to legacy pipeline (retry #%d)", job_id, retry_count)
            update_job(
                job_id, "running", 5,
                f"Primary pipeline failed — retrying with legacy fallback (retry #{retry_count})",
                error_message=f"{type(e).__name__}: {e}",
                result_data={
                    "currentStage": "legacy_fallback",
                    "failureReason": f"primary_pipeline_error: {type(e).__name__}",
                    "retryCount": retry_count,
                },
                processing_metadata={"retryCount": retry_count, "fallback": True},
            )
            _run_legacy_pipeline(job_id, project_id, audio_file_path)

        except Exception as legacy_err:
            logger.exception(
                "[job=%s] Legacy pipeline also failed: %s", job_id, legacy_err
            )
            update_job(
                job_id, "failed", 0,
                "Analysis failed (primary + fallback both failed)",
                error_message=f"{type(e).__name__}: {e}",
            )
            update_project_status(project_id, "error")


def _run_new_pipeline_staged(
    audio_file_path: str,
    mode: str,
    job_id: str,
) -> dict:
    """
    Run the new analysis.pipeline with per-stage job updates.
    Monkey-patches a progress callback into the pipeline logger.
    """
    from analysis import pipeline as pipe_module

    # Register a simple stage observer via logging
    class _StageObserver(logging.Handler):
        """Translate pipeline log messages to job updates."""
        STAGE_MAP = {
            "Stage 2":  STAGE_SEPARATE,
            "Stage 3":  STAGE_BEATS,
            "Stage 4a": STAGE_KEY,
            "Stage 4b": STAGE_KEY,
            "Stage 5":  STAGE_CHORDS,
            "Stage 6":  STAGE_MELODY,
            "Stage 7":  STAGE_STRUCTURE,
            "Stage 8":  STAGE_SMOOTHING,
            "Stage 9":  STAGE_THEORY,
            "Stage 10": STAGE_FUSION,
            "Stage 11": STAGE_GUARD,
            "Stage 12": STAGE_CANONICAL,
        }

        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            for key, stage in self.STAGE_MAP.items():
                if f"[pipeline] Stage {key[6:]}" in msg or key in msg:
                    _stage_update(job_id, stage)
                    break

    observer = _StageObserver()
    pipe_logger = logging.getLogger("analysis.pipeline")
    pipe_logger.addHandler(observer)

    try:
        from analysis.pipeline import analyze_to_dict
        result = analyze_to_dict(audio_file_path, mode=mode)
    finally:
        pipe_logger.removeHandler(observer)

    _stage_update(job_id, STAGE_CONFIDENCE)
    _stage_update(job_id, STAGE_CANONICAL)
    return result


def _run_legacy_pipeline(job_id: str, project_id: int, audio_file_path: str) -> None:
    """Fallback to the original audio.analyzer pipeline. Clearly marked as legacy."""
    from audio.analyzer import run_full_analysis
    from api.database import update_project_audio_metadata

    def _progress(step: str, pct: float):
        update_job(
            job_id, "running", pct,
            f"[Legacy] {step}",
            result_data={"currentStage": "legacy", "pipelineVersion": "1.0.0-legacy"},
        )

    result = run_full_analysis(audio_file_path, project_id, _progress)
    result["isMock"] = False
    result["pipelineVersion"] = "1.0.0-legacy"
    result["qualityFlags"] = ["legacy_pipeline_used"]

    update_project_audio_metadata(project_id, {
        "duration_seconds": result.get("duration"),
        "sample_rate":      result.get("sampleRate"),
        "channels":         1,
        "codec":            None,
    })

    save_analysis_result(project_id, result, pipeline_version="1.0.0-legacy")
    update_project_status(project_id, "analyzed")
    update_job(
        job_id, "completed", 100,
        "Analysis complete (legacy fallback — reduced accuracy)",
        result_data={
            "pipelineVersion": "1.0.0-legacy",
            "qualityFlags": ["legacy_pipeline_used"],
        },
    )
    logger.info("[job=%s] Legacy analysis complete for project %s", job_id, project_id)
