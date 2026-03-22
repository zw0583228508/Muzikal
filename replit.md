# MusicAI Studio

## Overview

Production-grade AI-powered music intelligence and generation system.
Full-stack web application with Python audio processing backend and React DAW frontend.

## Stack

### Frontend
- **Framework**: React + Vite (TypeScript)
- **UI**: Tailwind CSS, shadcn/ui, Framer Motion, Lucide Icons
- **State**: React Query for server state, polling for async jobs
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
- **Tables**: projects, jobs, analysis_results, arrangements

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
→ Structure Detection → Arrangement Generation → Export
```

## Module Structure

```
artifacts/
  music-daw/          # React frontend DAW
  api-server/         # Node.js Express backend
    src/routes/
      projects.ts     # CRUD + upload + analyze + arrange + export
      jobs.ts         # Job status polling
      styles.ts       # Musical style list
  music-ai-backend/   # Python FastAPI audio backend
    audio/
      analyzer.py     # Main pipeline orchestrator
      rhythm.py       # BPM, beat grid, time signature (librosa)
      key_mode.py     # Key, mode, modulations (HPCP/chroma)
      chords.py       # Chord detection (template matching)
      melody.py       # Melody extraction (pyin F0)
      structure.py    # Section detection (SSM + novelty)
    orchestration/
      arranger.py     # Arrangement & MIDI generation
    api/
      routes.py       # FastAPI routes (analyze, arrange)
      database.py     # DB connection helpers
      schemas.py      # Pydantic schemas

lib/
  api-spec/           # OpenAPI 3.1 spec (source of truth)
  api-client-react/   # Generated React Query hooks
  api-zod/            # Generated Zod schemas
  db/
    schema/projects.ts  # Drizzle schema: projects, jobs, analysis_results, arrangements
```

## Key Features Implemented

### Audio Analysis
- Rhythm: BPM, beat grid, downbeats, time signature (madmom + librosa)
- Key: Global key + modulations (HPCP chroma + Krumhansl-Schmuckler profiles)
- Chords: Extended chord vocabulary, template matching, Roman numerals
- Melody: F0 extraction (pyin), note segmentation, harmony inference
- Structure: Self-similarity matrix + novelty detection, section labels

### Arrangement Engine
- 8 musical styles: Pop, Jazz, R&B, Orchestral, Electronic, Rock, Bossa Nova, Ambient
- Multi-track MIDI: drums, bass, piano, guitar, strings, pad, brass, lead
- Performance humanization: timing jitter, velocity shaping

### Web Interface (DAW)
- Projects dashboard with status badges
- Audio upload with drag & drop
- Analysis progress with step-by-step indicators
- Timeline with waveform, chord labels, section markers
- Track lanes with MIDI note display
- Style selector for arrangement generation
- Export panel: MIDI, MusicXML, PDF, WAV, FLAC, MP3, Stems
- Mixer with volume/pan per track

## Development Commands

```bash
# Start all services
# Done automatically via workflows

# Push DB schema changes
pnpm --filter @workspace/db run push-force

# Regenerate API types from OpenAPI spec
pnpm --filter @workspace/api-spec run codegen

# Install Python packages
# Use code_execution with installLanguagePackages
```

## Future Enhancements

- Demucs source separation (vocal, drums, bass, other stems)
- torchcrepe / basic-pitch for more accurate melody extraction
- Transformer-based chord recognition model
- NVIDIA Triton for GPU-accelerated inference
- Real MIDI/MusicXML/PDF export
- Audio rendering with sample libraries
- WebSocket real-time updates
- User authentication (Replit Auth)
