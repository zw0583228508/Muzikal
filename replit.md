# MusicAI Studio

## Overview

Production-grade AI-powered music intelligence and generation system.
Full-stack web application with Python audio processing backend and React DAW frontend.

## Stack

### Frontend
- **Framework**: React + Vite (TypeScript)
- **UI**: Tailwind CSS, shadcn/ui, Framer Motion, Lucide Icons
- **State**: React Query for server state, polling for async jobs
- **i18n**: react-i18next, English + Hebrew (RTL), Noto Sans Hebrew
- **Preview path**: `/` (root)

### Node.js API Server
- **Framework**: Express 5
- **Port**: 8080 (exposed at `/api`)
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (generated from OpenAPI spec)
- **File uploads**: multer (200MB limit)

### Python Audio Processing Backend
- **Framework**: FastAPI + Uvicorn
- **Port**: 8001 (internal, not exposed to proxy)
- **Called by**: Node.js api-server at `http://localhost:8001`

### Database
- **PostgreSQL** via Drizzle ORM
- **Tables**: projects, jobs, analysis_results, arrangements, project_files

## Architecture

```
Browser → [Proxy :80]
  ├── /         → music-daw frontend (React, :19270)
  └── /api      → api-server (Express, :8080)
                    └── localhost:8001 → Python audio backend (FastAPI)
```

## Services / Workflows

| Workflow | Port | Description |
|----------|------|-------------|
| `artifacts/music-daw: web` | 19270 | React DAW frontend |
| `artifacts/api-server: API Server` | 8080 | Node.js REST API |
| `Python Audio Backend` | 8001 | FastAPI audio processing |
| `artifacts/mockup-sandbox: Component Preview Server` | 8081 | Design sandbox |

## Processing Pipeline

```
Audio Upload → Ingestion → Source Separation → Rhythm Analysis
→ Key/Mode Detection → Chord Analysis → Melody Extraction
→ Structure Detection → Arrangement Generation → Render Audio → Export
```

## Module Structure

```
artifacts/
  music-daw/          # React frontend DAW
    src/
      components/
        audio-player.tsx    # HTML5 Audio player (play/pause/seek/volume)
        language-toggle.tsx # EN/HE language switcher
      i18n/en.ts he.ts      # Translation files
      pages/project-studio.tsx  # Main studio page
  api-server/         # Node.js Express backend
    src/routes/
      projects.ts     # CRUD + upload + analyze + arrange + export + render + files + audio
      jobs.ts         # Job status polling
      styles.ts       # Musical style list
  music-ai-backend/   # Python FastAPI audio backend
    audio/
      analyzer.py        # Main pipeline orchestrator (9 steps)
      rhythm.py          # BPM, beat grid, time signature (librosa)
      key_mode.py        # Key, mode, modulations (HPCP/chroma)
      chords.py          # Chord detection (template matching)
      melody.py          # Melody extraction (pyin F0)
      structure.py       # Section detection (SSM + novelty)
      separator.py       # Source separation (Demucs + HPSS fallback)
      vocal_analysis.py  # Vocal F0, vibrato, phrasing, range
      rendering.py       # Wavetable synthesis with ADSR envelopes
      mixing.py          # Per-track EQ/compression + master bus (-14 LUFS)
      render_pipeline.py # WAV/FLAC/MP3/Stems render pipeline
      export_engine.py   # MIDI/MusicXML/Lead Sheet export
    orchestration/
      arranger.py     # Arrangement & MIDI generation (8 styles)
    api/
      routes.py       # FastAPI routes (analyze, arrange, export, render)
      database.py     # DB connection helpers
      schemas.py      # Pydantic schemas

lib/
  api-spec/           # OpenAPI 3.1 spec (source of truth)
  api-client-react/   # Generated React Query hooks
  api-zod/            # Generated Zod schemas (includes JobType.render)
  db/
    schema/projects.ts  # Drizzle schema: projects, jobs, analysis_results, arrangements, project_files
```

## Key Features Implemented

### Audio Analysis (MIR)
- Rhythm: BPM, beat grid, downbeats, time signature (madmom + librosa)
- Key: Global key + modulations (HPCP chroma + Krumhansl-Schmuckler profiles)
- Chords: Extended chord vocabulary, template matching, Roman numerals
- Melody: F0 extraction (pyin), note segmentation, harmony inference
- Structure: Self-similarity matrix + novelty detection, section labels
- Source Separation: Demucs (ML-based) + HPSS fallback → vocals/drums/bass/other
- Vocal Analysis: F0 contour, vibrato, phrasing, pitch range

### Arrangement Engine
- 8 musical styles: Pop, Jazz, R&B, Orchestral, Electronic, Rock, Bossa Nova, Ambient
- Multi-track MIDI: drums, bass, piano, guitar, strings, pad, brass, lead
- Performance humanization: timing jitter, velocity shaping
- Karplus-Strong synthesis for guitar plucks

### Audio Rendering
- Wavetable synthesis with ADSR envelopes for 9 instrument families
- Mixing: per-track HP filter + peak EQ + RMS compression presets
- Mastering: shelf EQ, mid-side widening, glue compression, peak limiter, -14 LUFS normalization
- Export: WAV (PCM_24), FLAC, MP3 (320kbps), Stems (per-instrument)

### Export / Download
- MIDI (multi-track .mid via mido)
- MusicXML score (.musicxml via music21)
- Lead Sheet PDF (text layout)
- WAV / FLAC / MP3 audio render
- Separated audio stems
- `project_files` table stores all generated file metadata
- `/api/projects/:id/files` — list files
- `/api/projects/:id/files/:filename/download` — stream file with Content-Disposition

### Audio Playback
- `/api/projects/:id/audio` — HTTP range-request streaming of original audio
- `AudioPlayer` component: play/pause/seek/volume, disabled state, keyboard (space)
- Integrated into TransportBar (2-row layout: metadata + player)

### Web Interface (DAW)
- Projects dashboard with status badges
- Audio upload with drag & drop (200MB limit)
- Analysis progress with step-by-step indicators
- Timeline with waveform, chord labels, section markers
- Track lanes with MIDI note display
- Style selector for arrangement generation
- Export panel: Score & MIDI section + Audio Render section
- Mixer with volume/pan per track
- Hebrew (RTL) + English UI, language toggle
- Job progress polling (2s interval) with step labels

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/projects | List projects |
| POST | /api/projects | Create project |
| GET | /api/projects/:id | Get project |
| DELETE | /api/projects/:id | Delete project |
| POST | /api/projects/:id/upload | Upload audio |
| POST | /api/projects/:id/analyze | Start MIR analysis |
| GET | /api/projects/:id/analysis | Get analysis results |
| POST | /api/projects/:id/arrange | Generate arrangement |
| GET | /api/projects/:id/arrangement | Get arrangement |
| POST | /api/projects/:id/export | Export MIDI/MusicXML/PDF |
| POST | /api/projects/:id/render | Render WAV/FLAC/MP3/Stems |
| GET | /api/projects/:id/audio | Stream original audio |
| GET | /api/projects/:id/files | List generated files |
| GET | /api/projects/:id/files/:filename/download | Download file |
| GET | /api/jobs/:jobId | Get job status |
| GET | /api/styles | List arrangement styles |

## Development Commands

```bash
# Push DB schema changes
pnpm --filter @workspace/db run push-force

# Regenerate API types from OpenAPI spec
pnpm --filter @workspace/api-spec run codegen
```

## Remaining Features (Future)

- WebSocket real-time job progress (replace polling)
- Replit Auth (user accounts, project ownership)
- FluidSynth/soundfont rendering (higher quality audio)
- Piano roll MIDI editor
- torchcrepe / basic-pitch for more accurate melody extraction
- Transformer-based chord recognition model
