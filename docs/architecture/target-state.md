# Target State — Muzikal Production Platform

## Target Architecture

```
Browser (React/TS)
    │  HTTPS + WSS
    ▼
API Gateway / Nginx
    │
    ├─ Node.js API Server — project management, auth, billing
    │       (Express 5 + Drizzle ORM + PostgreSQL)
    │
    └─ Python ML Service — FastAPI — /infer/*, /jobs/*, /models, /health
            │
            ├── Redis (broker + job state cache)
            │
            ├── Worker: cpu-analysis-worker
            │     rhythm, key, chords, melody, structure, vocals
            │
            ├── Worker: gpu-separation-worker
            │     demucs stem separation
            │
            ├── Worker: gpu-generation-worker
            │     MusicGen style embeddings, phrase suggestions
            │
            └── Worker: render-worker
                  MIDI → audio render, loudness normalization
```

## Target Service Matrix

| Service | Tech | Hosting |
|---------|------|---------|
| Frontend | React 19 + Vite | CDN / Vercel |
| API Server | Node.js + Express + Drizzle | Cloud Run / Railway |
| ML Service | FastAPI + Celery | GPU VM (A100/L4) |
| Database | PostgreSQL | Cloud SQL / Neon |
| Redis | Redis Cloud | Redis Cloud |
| Object Storage | S3-compatible | R2 / S3 |
| Model Registry | MLflow / custom | same GPU VM |

## Target Database Schema

```
users          — id, email, plan, createdAt
projects       — id, userId, name, status, audioAssetId, ...
source_assets  — id, projectId, storageUrl, checksum, format, ...
analysis_runs  — id, projectId, version, status, featureCache, ...
arrangement_versions — id, projectId, version, styleId, personaId, tracksData, ...
render_versions — id, projectId, arrangementId, quality, storageUrl, ...
exports        — id, projectId, format, storageUrl, expiresAt, ...
jobs           — id, jobId, type, status, startedAt, finishedAt, errorCode, ...
model_registry — id, name, version, task, checkpoint, checksum, device, ...
```

## Target Analysis Pipeline

```
Audio In
    ↓
Ingestion: validate → ffprobe → normalize → checksum
    ↓
Feature Extraction (cached by checksum):
    onset envelope, beat positions, tempo curve,
    chroma/HPCP, spectral contrast, RMS/energy,
    section novelty, vocal activity, melody contour
    ↓
Parallel Analysis Workers:
    rhythm/meter → beat grid, bar grid, time sig, confidence
    key/mode     → global key, modulation events, top-k candidates
    chords       → timeline, roman numerals, ambiguity
    melody       → note events, pitch range, phrases
    structure    → section labels, confidence, boundaries
    vocals       → notes, vibrato, range, voiced ratio
    ↓
Stem Separation (demucs, provider abstraction):
    vocals | drums | bass | other
    ↓
All results cached to object storage + DB
```

## Target Arrangement Engine

```
Layer 1: Musical Analysis (from pipeline above)
    ↓
Layer 2: Style Profile (15+ styles in YAML)
    + Arranger Persona (6 personas: hasidic-wedding, cinematic, ...)
    ↓
Layer 3: Arrangement Planner
    - section instrument assignments
    - density curve per section
    - transition vocabulary
    - doubling / counterline decisions
    ↓
Layer 4: Track Generators (per instrument)
    drums → patterns, fills, humanization
    bass  → root/fifth, passing tones, lock-to-kick
    piano → voice-leading, inversions, comping
    strings → legato pads, ostinato, chorus lifts
    brass → punches, call-response, swells
    guitar → strumming, arpeggio, chuck
    ↓
Layer 5: Renderer
    MIDI export → preview render → high-quality render
```

## Regenerate Operations

- Regenerate-by-section: re-run Layer 4 for a single section only
- Regenerate-by-track: re-run a single track generator across all sections
- Interaction: "Make drums simpler", "More brass in chorus", etc.

## Target Job States

```
queued → preprocessing → analyzing → separating → arranging → rendering → completed
                                                                         ↘ failed
```

## Target Frontend Pages

1. Upload / New Project — file upload, style + persona selection
2. Project Overview — waveform, sections summary, job states
3. Studio View — track list, piano roll, chord/section lanes, mute/solo, regenerate
4. Analysis Inspector — tempo graph, key candidates, chord confidence, melody range
5. Export Center — MIDI, stems, preview mix, full mix, notation, archive bundle
