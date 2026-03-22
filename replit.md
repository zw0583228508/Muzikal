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
Audio Upload → Ingestion (validate/ffprobe/checksum/normalize)
→ Source Separation (Demucs/HPSS fallback)
→ Rhythm Analysis (madmom) → Key/Mode (Essentia) → Chord Analysis
→ Melody Extraction (pyin) → Vocal Analysis → Structure Detection (MSAF)
→ Arrangement Generation (section-aware, profiles from YAML)
→ Render Audio (preview 22050Hz / HQ 44100Hz) → Export (MIDI/MusicXML/lead-sheet/audio)
```

## Mock Mode (Development)

- `MOCK_MODE=true` (default): Node.js simulates the full pipeline without Python. All mock results are labelled `isMock: true`, visible in the DB, API, and frontend as an amber badge.
- `MOCK_MODE=false` (production): any Python backend failure → job FAILED immediately. No silent simulation.
- `GET /api/projects/mock-mode` → returns current mode + pipeline version.

## Pipeline Versioning (T005)

- `PIPELINE_VERSION=1.1.0` set in api-server
- All analysis results include `pipelineVersion` and `modelVersions` dict (7 models)
- All arrangements include `createdFromAudioHash` and `isMock` fields
- Version shown in TransportBar header (`ENGINE: v1.1.0`)

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

## Session Progress (Current)

### T002 — Feature Extraction Cache ✅
- `packages/audio_core/feature_cache.py` — disk JSON cache keyed by SHA-256 checksum, TTL=7d, sharded dirs
- Integrated into `audio/analyzer.py` — each step (rhythm, key, chords, melody, vocals, structure) checks cache before running ML; writes result on miss
- `cacheEnabled: true` field in analysis response

### T003 — Job Schema Hardening ✅
- DB columns: `started_at`, `finished_at`, `error_code`, `error_message`, `input_payload`
- `startJob()` helper sets `startedAt` atomically; all 3 simulated pipelines call it
- `finishedAt` set on completion of all 3 simulated job types (analysis, arrangement, export)
- `POST /api/jobs/:jobId/retry` and `POST /api/jobs/:jobId/cancel` endpoints
- `inputPayload` stored for arrangement jobs (includes `personaId`)

### T004 — Arranger Personas System ✅
- `artifacts/music-ai-backend/orchestration/arranger_personas.yaml` — 6 personas: hasidic-wedding, cinematic, modern-pop, live-band, jazz-quartet, electronic-producer
- `orchestration/persona_loader.py` — YAML loader (LRU cache), `apply_persona_to_arrangement()` adjusts track volumes by instrumentation weights, embeds persona metadata
- `generate_arrangement()` accepts `persona_id` param; applies persona after generation
- `GET /api/styles/personas` — returns all 6 personas from YAML
- `POST /api/projects/:id/arrangement` accepts `personaId` param; stored in `inputPayload`
- Frontend: Persona picker card grid in Arrange tab (Hebrew name, English name, tags); toggleable; cancel button

### T005 — Regenerate-by-Section and Regenerate-by-Track ✅
- `POST /api/projects/:id/arrangement/section/:label/regenerate` — creates a regen job for one section
- `POST /api/projects/:id/arrangement/track/:trackId/regenerate` — creates a regen job for one track
- Both endpoints: mock simulation path (2 steps, ~1.6s) + real Python backend path
- `inputPayload` stores `sectionLabel`/`trackId` + `styleId` + `personaId`
- Frontend: ↺ regen button per track in TrackLane; `handleRegenSection` / `handleRegenTrack` handlers

### T006 — Analysis Inspector Page ✅
- `artifacts/music-daw/src/components/analysis-inspector.tsx` — full Analysis Inspector component
- Panels: Warnings, Tempo/Beat, Key+Alternatives, Chord Timeline (colour-coded by confidence), Melody Pitch Range, Section Timeline (coloured by label), Stem Separation status, Confidence Bars
- New "Inspect" tab added to right panel (4 tabs total: Analyze, Inspect, Arrange, Export)

### T007 — Celery + Redis Async Workers ✅
- `workers/celery_app.py` — Celery app initialised against `REDIS_URL` (default `redis://localhost:6379/0`); pings Redis on startup, sets `CELERY_AVAILABLE=False` if unreachable; exposes `get_celery_app()` + `revoke_task()`
- `workers/tasks/analysis.py` — Celery task wrapping `run_analysis_pipeline()`; stores `celery_task_id` in job `result_data`
- `workers/tasks/arrangement.py` — Celery task wrapping `run_arrangement_pipeline()` (+ `persona_id` param)
- `workers/tasks/render.py` — Celery export + render tasks; both `dispatch_export()` + `dispatch_render()` helpers
- All 4 pipeline endpoints (`/analyze`, `/arrange`, `/export`, `/render`) try Celery dispatch first; fall back transparently to FastAPI `BackgroundTasks`
- Response adds `"worker": "celery" | "inprocess"` field
- `POST /python-api/jobs/{job_id}/cancel` — revokes Celery task (if `celery_task_id` stored) + marks DB `cancelled`
- **Run workers**: `celery -A workers.celery_app worker --loglevel=info` (requires Redis)

### T008 — Tests + replit.md Update ✅
- **39 Python tests, all passing** (`python -m pytest tests/ -v`)
- `tests/test_feature_cache.py` — 9 tests: miss/hit, TTL expiry, stats, clear, complex JSON
- `tests/test_personas.py` — 9 tests: all 6 personas present, schema validation, `apply_persona_to_arrangement` metadata + volume weights, LRU cache
- `tests/test_jobs.py` — 12 tests: Celery fallback (CELERY_AVAILABLE, dispatch returns None), FastAPI health/styles/cancel/422 validation
- `tests/test_regen_endpoints.py` — 9 integration tests (skip if server down): regen-section, regen-track, inputPayload stored, personas endpoint
- `tests/conftest.py` — autouse fixture isolates cache per test via temp dir
- Run: `cd artifacts/music-ai-backend && python -m pytest tests/ -v`

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
| POST | /api/jobs/:jobId/cancel | Cancel a running job |
| POST | /api/jobs/:jobId/retry | Retry a failed job |
| GET | /api/styles | List arrangement styles |
| GET | /api/styles/personas | List all 6 arranger personas |
| POST | /api/projects/:id/arrangement/section/:label/regenerate | Regenerate one section |
| POST | /api/projects/:id/arrangement/track/:trackId/regenerate | Regenerate one track |

## Development Commands

```bash
# Push DB schema changes
pnpm --filter @workspace/db run push-force

# Regenerate API types from OpenAPI spec
pnpm --filter @workspace/api-spec run codegen
```

## Step 26 Compliance (spec "Fix First" list)

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Remove silent simulated success | ✅ Mock mode only when MOCK_MODE=true |
| 2 | Explicit mock mode label | ✅ All steps prefixed [MOCK], yellow banner in UI |
| 3 | DB/schema mismatches | ✅ Fixed (tracks_data) |
| 4 | Real queue system | ⚠️ PostgreSQL-based jobs + WebSocket |
| 7 | Style single-source-of-truth | ✅ styles.ts in Node.js matches arranger.py |
| 10 | Manual correction tools | ✅ BPM/Key/Mode corrections modal |
| 11 | WebSocket real-time updates | ✅ /api/ws, auto-reconnect, fallback to polling |

## Step 19-20 Features

- **Lock/Unlock system**: Lock icons on Key, Structure, Chords cards — locked fields preserved during re-arrangement
- **Piano Roll**: Full MIDI editor panel at bottom — click any track lane to open; scrollable with pitch grid, note colors, velocity opacity, zoom 20-240px/beat
- **Replit Auth (OIDC/PKCE)**: Login/logout in header, sessions in PostgreSQL, openid-client v6

## Remaining Features (Future)

- FluidSynth/soundfont rendering (higher quality audio)
- Real job queue with Redis + Celery (currently PostgreSQL-based)
- torchcrepe / basic-pitch for more accurate melody extraction
- Transformer-based chord recognition model
- Pipeline versioning for result reproducibility
