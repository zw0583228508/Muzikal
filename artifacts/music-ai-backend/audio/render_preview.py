"""
Preview Render Engine — STEP 13.
Produces fast, lower-quality previews for UI playback.
Explicitly labelled as PREVIEW in all outputs.
"""

import logging
import os
import numpy as np
import soundfile as sf
from typing import List, Optional

logger = logging.getLogger(__name__)

PREVIEW_SR = 22050        # Lower sample rate for speed
PREVIEW_BIT_DEPTH = 16
PREVIEW_MAX_DURATION = 60  # Cap at 60 seconds for previews


def render_preview(
    tracks: List[dict],
    total_duration: float,
    output_path: str,
    progress_callback=None,
) -> dict:
    """
    Render a fast stereo preview WAV at 22050Hz.
    All outputs are labelled as PREVIEW quality.

    Returns:
        {
            "filePath": str,
            "quality": "preview",
            "sampleRate": int,
            "durationSeconds": float,
            "warnings": list[str],
        }
    """
    warnings = []
    preview_duration = min(total_duration, PREVIEW_MAX_DURATION)

    if total_duration > PREVIEW_MAX_DURATION:
        warnings.append(f"Preview capped at {PREVIEW_MAX_DURATION}s (full duration: {total_duration:.1f}s)")
        logger.info(f"[PREVIEW] Capping to {PREVIEW_MAX_DURATION}s")

    try:
        from audio.render_pipeline import render_to_wav
        if progress_callback:
            progress_callback("Rendering preview", 10)

        # Render with capped duration
        render_to_wav(
            tracks,
            preview_duration,
            output_path,
            progress_callback=lambda step, pct: progress_callback(f"[PREVIEW] {step}", pct) if progress_callback else None,
        )

        stat = os.stat(output_path)
        logger.info(f"[PREVIEW] Written: {output_path} ({stat.st_size // 1024}KB)")

        return {
            "filePath": output_path,
            "quality": "preview",
            "sampleRate": PREVIEW_SR,
            "durationSeconds": preview_duration,
            "fileSizeBytes": stat.st_size,
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"[PREVIEW] Render failed: {e}")
        # Write silence so the player doesn't crash
        silence = np.zeros((int(PREVIEW_SR * preview_duration), 2), dtype=np.float32)
        sf.write(output_path, silence, PREVIEW_SR)
        warnings.append(f"Render failed ({e}) — silence written instead")
        stat = os.stat(output_path)
        return {
            "filePath": output_path,
            "quality": "preview",
            "sampleRate": PREVIEW_SR,
            "durationSeconds": preview_duration,
            "fileSizeBytes": stat.st_size,
            "warnings": warnings,
        }
