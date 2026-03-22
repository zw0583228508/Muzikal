"""
Rhythm Engine: BPM, beat grid, downbeats, time signature detection.
Uses librosa's advanced beat tracking + onset detection.
"""

import logging
import numpy as np
import librosa
from typing import Dict, Any

logger = logging.getLogger(__name__)


def analyze_rhythm(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Full rhythm analysis using librosa.
    Returns BPM, beat grid, downbeats, time signature.
    """
    logger.info("Running rhythm analysis...")

    # Compute onset strength
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)

    # BPM and beat tracking with dynamic programming
    tempo, beats = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        units="time",
        tightness=100,
    )

    # librosa >= 0.10 may return a 0-d or 1-d array; squeeze to scalar safely
    tempo_arr = np.atleast_1d(np.squeeze(tempo))
    bpm_bt = float(tempo_arr[0]) if tempo_arr.size > 0 else 0.0

    # Also try plp (predominant local pulse) for robust tempo
    # librosa 0.10+ moved this to librosa.feature.rhythm.tempo
    pulse = librosa.beat.plp(onset_envelope=onset_env, sr=sr)
    try:
        tempo_plp_arr = librosa.feature.rhythm.tempo(onset_envelope=pulse, sr=sr, aggregate=None)
    except AttributeError:
        try:
            tempo_plp_arr = librosa.beat.tempo(onset_envelope=pulse, sr=sr, aggregate=None)
        except Exception:
            tempo_plp_arr = np.array([bpm_bt])
    tempo_plp = float(np.atleast_1d(tempo_plp_arr).mean())

    # Use the more confident tempo estimate
    bpm = bpm_bt if bpm_bt > 0 else tempo_plp
    bpm = round(bpm, 2)

    beat_grid = [float(b) for b in beats]

    # Detect downbeats using autocorrelation of onset strength
    # Group beats into measures (estimate time signature)
    time_sig_num, time_sig_den = estimate_time_signature(onset_env, sr, beats, bpm)

    # Build downbeats from beats and time signature
    downbeats = [beat_grid[i] for i in range(0, len(beat_grid), time_sig_num)]

    logger.info(f"Rhythm: {bpm} BPM, {time_sig_num}/{time_sig_den}, {len(beat_grid)} beats")

    return {
        "bpm": bpm,
        "timeSignatureNumerator": time_sig_num,
        "timeSignatureDenominator": time_sig_den,
        "beatGrid": beat_grid,
        "downbeats": downbeats,
    }


def estimate_time_signature(onset_env: np.ndarray, sr: int, beats: np.ndarray, bpm: float):
    """
    Estimate time signature from beat grid and onset strength.
    Returns (numerator, denominator) — most common: 4/4, 3/4, 6/8.
    """
    # Convert beats to frames
    hop_length = 512
    beat_frames = librosa.time_to_frames(beats, sr=sr, hop_length=hop_length)

    # Measure onset strength at beat positions
    beat_strengths = []
    for bf in beat_frames:
        if 0 <= bf < len(onset_env):
            beat_strengths.append(float(onset_env[bf]))
        else:
            beat_strengths.append(0.0)

    if len(beat_strengths) < 4:
        return 4, 4

    # Compute autocorrelation of beat strengths to find periodicity
    beat_arr = np.array(beat_strengths)
    # Normalize
    beat_arr = (beat_arr - beat_arr.mean()) / (beat_arr.std() + 1e-8)

    # Correlate for periods 2, 3, 4, 6, 8
    candidates = {3: 0.0, 4: 0.0, 6: 0.0}
    for period in [3, 4, 6]:
        corr = 0.0
        count = 0
        for i in range(len(beat_arr) - period):
            corr += beat_arr[i] * beat_arr[i + period]
            count += 1
        candidates[period] = corr / max(count, 1)

    best_period = max(candidates, key=candidates.get)

    if best_period == 3:
        return 3, 4
    elif best_period == 6:
        return 6, 8
    else:
        return 4, 4
