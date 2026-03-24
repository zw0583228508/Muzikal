"""
Multi-stage music analysis pipeline.

Entry point: analysis.pipeline.analyze(audio_path, mode='balanced')

Modes:
  'fast'          – single-pass librosa only, no stem separation
  'balanced'      – Demucs + madmom + Essentia + torchcrepe (default)
  'high_accuracy' – full ensemble, stronger smoothing, re-analysis fallbacks
"""

__version__ = "2.0.0"
