"""
Full Render Pipeline: MIDI → Audio → Mix → Master → File.
Orchestrates rendering.py + mixing.py + export to WAV/FLAC/MP3.
"""

import os
import logging
import numpy as np
import soundfile as sf
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

SR = 44100


def render_to_wav(tracks: List[dict], total_duration: float,
                  output_path: str, progress_callback=None) -> str:
    """
    Full pipeline: synthesize → mix → master → write WAV.
    """
    from audio.rendering import render_arrangement, detect_instrument_type
    from audio.mixing import mix_tracks, apply_master_bus

    if progress_callback:
        progress_callback("Synthesizing instruments", 10)

    # Render each track individually for per-track processing
    rendered = []
    inst_types = []
    active_tracks = [t for t in tracks if not t.get("muted", False)]

    for i, track in enumerate(active_tracks):
        if progress_callback:
            pct = int(10 + (i / max(len(active_tracks), 1)) * 50)
            progress_callback(f"Rendering {track.get('name', 'Track')}", pct)
        try:
            from audio.rendering import render_track
            audio = render_track(track, total_duration, SR)
            rendered.append(audio)
            inst_types.append(detect_instrument_type(track))
        except Exception as e:
            logger.warning(f"Skipping track {track.get('name', '?')}: {e}")

    if not rendered:
        logger.error("No tracks to render")
        # Write silence
        silence = np.zeros((int(SR * total_duration), 2), dtype=np.float32)
        sf.write(output_path, silence, SR)
        return output_path

    if progress_callback:
        progress_callback("Mixing tracks", 65)

    # Mix with per-track EQ and compression
    mix = mix_tracks(rendered, inst_types, SR, progress_callback)

    if progress_callback:
        progress_callback("Mastering", 85)

    # Master bus processing (EQ, compression, limiting)
    master = apply_master_bus(mix, SR, target_lufs=-14.0)

    # ITU-R BS.1770-4 compliant loudness normalization (streaming preset: −14 LUFS, −1 dBTP)
    try:
        from audio.loudness_normalizer import normalize_audio
        master, norm_result = normalize_audio(
            master, SR,
            target_lufs=-14.0,
            max_true_peak_dbtp=-1.0,
            allow_boost=True,
        )
        logger.info(
            "Loudness normalization: %.1f → %.1f LUFS (gain %.1f dB)",
            norm_result.before.lufs, norm_result.after.lufs, norm_result.gain_applied_db,
        )
    except Exception as ln_exc:
        logger.warning("Loudness normalizer failed (non-fatal): %s", ln_exc)

    if progress_callback:
        progress_callback("Writing audio file", 95)

    # Write WAV (24-bit for quality)
    sf.write(output_path, master, SR, subtype='PCM_24')
    logger.info(f"WAV rendered: {output_path} ({master.shape[0] / SR:.1f}s, {os.path.getsize(output_path) // 1024}KB)")
    return output_path


def render_to_flac(tracks: List[dict], total_duration: float,
                   output_path: str, progress_callback=None) -> str:
    """Render to FLAC (lossless)."""
    wav_path = output_path.replace(".flac", "_tmp.wav")
    render_to_wav(tracks, total_duration, wav_path, progress_callback)

    try:
        import subprocess
        cmd = ["ffmpeg", "-i", wav_path, "-c:a", "flac", "-compression_level", "8",
               "-y", output_path]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            os.remove(wav_path)
            logger.info(f"FLAC rendered: {output_path}")
            return output_path
        else:
            logger.warning(f"ffmpeg FLAC failed, keeping WAV: {result.stderr.decode()[:200]}")
            os.rename(wav_path, output_path.replace(".flac", ".wav"))
            return output_path.replace(".flac", ".wav")
    except Exception as e:
        logger.warning(f"FLAC conversion failed: {e}")
        if os.path.exists(wav_path):
            os.rename(wav_path, output_path.replace(".flac", ".wav"))
        return output_path.replace(".flac", ".wav")


def render_to_mp3(tracks: List[dict], total_duration: float,
                  output_path: str, bitrate: str = "320k",
                  progress_callback=None) -> str:
    """Render to MP3 (streaming-quality 320kbps)."""
    wav_path = output_path.replace(".mp3", "_tmp.wav")
    render_to_wav(tracks, total_duration, wav_path, progress_callback)

    try:
        import subprocess
        cmd = ["ffmpeg", "-i", wav_path, "-c:a", "libmp3lame",
               "-b:a", bitrate, "-id3v2_version", "3",
               "-metadata", "encoder=MusicAI Studio",
               "-y", output_path]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            os.remove(wav_path)
            logger.info(f"MP3 rendered: {output_path} ({bitrate})")
            return output_path
        else:
            logger.warning(f"MP3 encoding failed: {result.stderr.decode()[:200]}")
            os.rename(wav_path, output_path.replace(".mp3", ".wav"))
            return output_path.replace(".mp3", ".wav")
    except Exception as e:
        logger.warning(f"MP3 conversion failed: {e}")
        if os.path.exists(wav_path):
            os.rename(wav_path, output_path.replace(".mp3", ".wav"))
        return output_path.replace(".mp3", ".wav")


def render_stems(tracks: List[dict], total_duration: float,
                 stems_dir: str, progress_callback=None) -> Dict[str, str]:
    """
    Render each track as an individual stem WAV file.
    Returns dict of track_name → file_path.
    """
    os.makedirs(stems_dir, exist_ok=True)
    stem_files = {}

    for i, track in enumerate(tracks):
        if track.get("muted", False):
            continue
        if progress_callback:
            pct = int(10 + (i / max(len(tracks), 1)) * 80)
            progress_callback(f"Rendering stem: {track.get('name', 'Track')}", pct)

        track_name = track.get("name", f"track_{i}").replace("/", "_").replace(" ", "_")
        stem_path = os.path.join(stems_dir, f"{track_name}.wav")

        try:
            from audio.rendering import render_track, detect_instrument_type
            from audio.mixing import process_track, apply_master_bus
            audio = render_track(track, total_duration, SR)
            inst_type = detect_instrument_type(track)
            # Apply per-track processing
            processed = process_track(audio, inst_type, SR)
            # Light master for stem
            final = apply_master_bus(processed, SR, target_lufs=-18.0)
            sf.write(stem_path, final, SR, subtype='PCM_24')
            stem_files[track_name] = stem_path
            logger.info(f"Stem rendered: {stem_path}")
        except Exception as e:
            logger.warning(f"Stem render failed for {track_name}: {e}")

    return stem_files


def run_audio_render(project_id: int, tracks: List[dict], total_duration: float,
                     formats: List[str], output_dir: str,
                     progress_callback=None) -> Dict[str, str]:
    """
    Main entry point for audio rendering.
    Handles wav, flac, mp3, stems formats.
    Returns dict of format → file path.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    if not tracks:
        logger.error("No tracks to render")
        return results

    base = os.path.join(output_dir, f"project_{project_id}")

    if "wav" in formats:
        wav_path = f"{base}.wav"
        try:
            render_to_wav(tracks, total_duration, wav_path, progress_callback)
            results["wav"] = wav_path
        except Exception as e:
            logger.error(f"WAV render failed: {e}")

    if "flac" in formats:
        flac_path = f"{base}.flac"
        try:
            render_to_flac(tracks, total_duration, flac_path, progress_callback)
            results["flac"] = flac_path
        except Exception as e:
            logger.error(f"FLAC render failed: {e}")

    if "mp3" in formats:
        mp3_path = f"{base}.mp3"
        try:
            render_to_mp3(tracks, total_duration, mp3_path, progress_callback=progress_callback)
            results["mp3"] = mp3_path
        except Exception as e:
            logger.error(f"MP3 render failed: {e}")

    if "stems" in formats:
        stems_dir = os.path.join(output_dir, f"project_{project_id}_stems")
        try:
            stem_files = render_stems(tracks, total_duration, stems_dir, progress_callback)
            results["stems"] = stems_dir
            results["stems_files"] = stem_files
        except Exception as e:
            logger.error(f"Stems render failed: {e}")

    return results
