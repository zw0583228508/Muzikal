"""
Audio Ingestion Module — STEP 6.
Validates, probes, normalizes, and prepares audio files for the analysis pipeline.

Every operation returns either a result dict or raises with a clear message.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

import librosa
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".aiff"}
MAX_FILE_SIZE_BYTES = 300 * 1024 * 1024  # 300 MB
TARGET_SR = 22050
TARGET_CHANNELS = 1  # Mono


# ── 1. File validation ────────────────────────────────────────────────────────

def validate_file(file_path: str) -> None:
    """Raise ValueError with a clear message if file is unusable."""
    if not os.path.exists(file_path):
        raise ValueError(f"File not found: {file_path}")

    stat = os.stat(file_path)
    if stat.st_size == 0:
        raise ValueError("File is empty (0 bytes)")

    if stat.st_size > MAX_FILE_SIZE_BYTES:
        mb = stat.st_size / 1024 / 1024
        raise ValueError(f"File too large: {mb:.1f} MB (max {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB)")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}")


# ── 2. ffprobe metadata ───────────────────────────────────────────────────────

def probe_metadata(file_path: str) -> dict:
    """
    Extract audio metadata via ffprobe.
    Falls back to soundfile/librosa if ffprobe is unavailable.
    """
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        probe = json.loads(result.stdout)
        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
        stream = audio_streams[0] if audio_streams else {}
        fmt = probe.get("format", {})

        duration = float(stream.get("duration") or fmt.get("duration") or 0)
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 1)
        codec = stream.get("codec_name", "unknown")
        bit_rate = int(fmt.get("bit_rate") or 0)
        file_size = int(fmt.get("size") or os.path.getsize(file_path))

        logger.info(f"ffprobe: {duration:.1f}s, {sample_rate}Hz, {channels}ch, {codec}")
        return {
            "duration": duration,
            "sampleRate": sample_rate,
            "channels": channels,
            "codec": codec,
            "bitRate": bit_rate,
            "fileSize": file_size,
            "probeMethod": "ffprobe",
        }

    except (FileNotFoundError, Exception) as e:
        logger.warning(f"ffprobe unavailable ({e}), using soundfile fallback")
        return _probe_with_soundfile(file_path)


def _probe_with_soundfile(file_path: str) -> dict:
    """Fallback metadata extraction using soundfile."""
    try:
        info = sf.info(file_path)
        return {
            "duration": info.duration,
            "sampleRate": info.samplerate,
            "channels": info.channels,
            "codec": info.subtype,
            "bitRate": None,
            "fileSize": os.path.getsize(file_path),
            "probeMethod": "soundfile",
        }
    except Exception as e:
        # Last resort: use librosa
        y, sr = librosa.load(file_path, sr=None, mono=False)
        channels = 1 if y.ndim == 1 else y.shape[0]
        duration = y.shape[-1] / sr
        return {
            "duration": duration,
            "sampleRate": sr,
            "channels": channels,
            "codec": "unknown",
            "bitRate": None,
            "fileSize": os.path.getsize(file_path),
            "probeMethod": "librosa",
        }


# ── 3. Checksum ───────────────────────────────────────────────────────────────

def compute_checksum(file_path: str, algorithm: str = "sha256") -> str:
    """Compute SHA-256 hash of the file for deduplication / versioning."""
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    logger.info(f"Checksum ({algorithm}): {digest[:16]}...")
    return digest


# ── 4. Load & Normalize ───────────────────────────────────────────────────────

def load_and_normalize(
    file_path: str,
    target_sr: int = TARGET_SR,
    mono: bool = True,
) -> tuple:
    """
    Load audio, resample, convert to mono, and peak-normalize.
    Returns (y: np.ndarray, sr: int).
    """
    logger.info(f"Loading audio: {file_path} → sr={target_sr}, mono={mono}")
    y, sr = librosa.load(file_path, sr=target_sr, mono=mono)

    # Peak normalize to -1.0 … +1.0
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak

    logger.info(f"Loaded: {len(y) / sr:.2f}s, peak={peak:.4f}")
    return y, sr


# ── 5. Silence trimming ───────────────────────────────────────────────────────

def trim_silence(
    y: np.ndarray,
    sr: int,
    top_db: float = 40.0,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> tuple:
    """
    Trim leading and trailing silence.
    Returns (y_trimmed, trim_info_dict).
    """
    original_duration = len(y) / sr
    y_trimmed, index = librosa.effects.trim(
        y, top_db=top_db, frame_length=frame_length, hop_length=hop_length
    )
    trimmed_duration = len(y_trimmed) / sr
    removed_s = original_duration - trimmed_duration

    info = {
        "originalDuration": round(original_duration, 3),
        "trimmedDuration": round(trimmed_duration, 3),
        "removedSeconds": round(removed_s, 3),
        "startSample": int(index[0]),
        "endSample": int(index[1]),
    }
    if removed_s > 0.5:
        logger.info(f"Trimmed {removed_s:.1f}s of silence")
    return y_trimmed, info


# ── 6. Waveform generation ────────────────────────────────────────────────────

def generate_waveform(y: np.ndarray, num_points: int = 1000) -> list:
    """Downsample audio to a fixed number of RMS points for display."""
    chunk_size = max(1, len(y) // num_points)
    waveform = []
    for i in range(num_points):
        start = i * chunk_size
        end = min(start + chunk_size, len(y))
        if start < len(y):
            chunk = y[start:end]
            waveform.append(round(float(np.max(np.abs(chunk))), 4))
        else:
            waveform.append(0.0)
    return waveform


# ── 7. Spectrogram ────────────────────────────────────────────────────────────

def generate_spectrogram_thumbnail(
    y: np.ndarray,
    sr: int,
    n_mels: int = 64,
    num_time_frames: int = 200,
) -> list:
    """Generate a compact mel spectrogram for UI display (num_time_frames × n_mels)."""
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=n_mels)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    # Downsample time axis
    step = max(1, mel_db.shape[1] // num_time_frames)
    thumbnail = mel_db[:, ::step][:, :num_time_frames]
    # Normalize to 0–1
    thumbnail = (thumbnail - thumbnail.min()) / (thumbnail.max() - thumbnail.min() + 1e-8)
    return thumbnail.T.tolist()  # shape: [time, freq]


# ── 8. Full ingestion pipeline ────────────────────────────────────────────────

def ingest_audio(
    file_path: str,
    generate_spectrogram: bool = False,
) -> dict:
    """
    Full ingestion pipeline:
      1. Validate
      2. Probe metadata (ffprobe → soundfile → librosa)
      3. Compute checksum
      4. Load & normalize
      5. Trim silence
      6. Generate waveform
      7. (Optional) Generate spectrogram thumbnail

    Returns a dict with all results and the processed audio array.
    """
    logger.info(f"Ingesting: {file_path}")

    # 1. Validate
    validate_file(file_path)

    # 2. Probe
    metadata = probe_metadata(file_path)

    # 3. Checksum
    file_hash = compute_checksum(file_path)

    # 4. Load & normalize
    y, sr = load_and_normalize(file_path, target_sr=TARGET_SR, mono=True)

    # 5. Trim silence
    y_trimmed, trim_info = trim_silence(y, sr)

    # 6. Waveform
    waveform = generate_waveform(y_trimmed)

    # 7. Optional spectrogram
    spectrogram = None
    if generate_spectrogram:
        spectrogram = generate_spectrogram_thumbnail(y_trimmed, sr)

    result = {
        "filePath": file_path,
        "fileHash": file_hash,
        "metadata": metadata,
        "trimInfo": trim_info,
        "duration": trim_info["trimmedDuration"],
        "sampleRate": sr,
        "channels": 1,
        "waveform": waveform,
        "spectrogram": spectrogram,
        "audio": y_trimmed,  # numpy array — consumed by analysis, not stored in DB
        "warnings": [],
    }

    if trim_info["removedSeconds"] > 2.0:
        result["warnings"].append(f"Trimmed {trim_info['removedSeconds']:.1f}s of silence from file edges")

    if metadata.get("duration", 0) < 5.0:
        result["warnings"].append("Audio is very short (< 5 seconds) — analysis quality may be limited")

    if metadata.get("sampleRate", 0) < 16000:
        result["warnings"].append(f"Original sample rate {metadata.get('sampleRate')}Hz is low — analysis quality may be limited")

    logger.info(f"Ingestion complete: {result['duration']:.1f}s, hash={file_hash[:8]}, warnings={result['warnings']}")
    return result
