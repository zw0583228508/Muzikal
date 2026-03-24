# Muzikal — AI Music Intelligence & Generation Studio

## Overview

Production-grade AI-powered music intelligence and generation web app (cloud-based DAW).
Full-stack: React frontend + Node.js Express API + Python FastAPI audio backend.
Hebrew-first, RTL, 50+ musical styles, 847 Python tests passing.

## Architecture

```
Browser → [Proxy :80]
  ├── /          → music-daw frontend   (React + Vite, :19270)
  └── /api       → api-server           (Express 5, :8080)
                     └── http://localhost:8001 → Python audio backend (FastAPI)
```

**API prefix convention:**
- Public (Node.js): `GET /api/projects/:id/analysis`
- Internal (Python): `POST /python-api/analyze` (proxied from Node.js)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + TypeScript + Tailwind + shadcn/ui |
| State | TanStack Query + custom WebSocket hook |
| i18n | react-i18next: English + Hebrew (RTL) |
| API Server | Express 5 + Drizzle ORM + PostgreSQL |
| Audio Backend | FastAPI + Uvicorn + librosa + demucs + madmom + Essentia + torchcrepe + mido + music21 |
| Queue | Celery + Redis (optional), falls back to FastAPI BackgroundTasks |
| Storage | LocalStorage (dev) / S3 (prod) via abstract `StorageProvider` |

## Services / Workflows

| Workflow | Port | Purpose |
|----------|------|---------|
| `artifacts/music-daw: web` | 19270 | React DAW frontend |
| `artifacts/api-server: API Server` | 8080 | Node.js REST + WebSocket |
| `Python Audio Backend` | 8001 | FastAPI audio processing |
| `artifacts/mockup-sandbox: Component Preview Server` | 8081 | Design sandbox |

## Module Structure

```
artifacts/
  music-daw/                 # React frontend
    src/
      pages/
        project-studio.tsx   # Main studio (thin orchestrator, 235 lines)
      components/studio/     # ← extracted sub-components (T003)
        TransportBar.tsx      # Header bar + audio player
        Banners.tsx           # MockBanner, FailedBanner
        TrackLane.tsx         # Single MIDI track row
        CorrectionsDrawer.tsx # Manual BPM/Key/Mode overrides
        AnalysisTab.tsx       # Right panel: Analysis tab
        ArrangeTab.tsx        # Right panel: Arrange tab
      hooks/
        use-project-studio.ts # All state + handlers hook
        use-job-polling.ts    # Polling fallback
        use-job-websocket.ts  # Real-time WebSocket updates
      components/
        audio-player.tsx      # HTML5 audio player
        piano-roll.tsx        # MIDI editor panel
        waveform-player.tsx   # WaveSurfer.js waveform
        midi-player.tsx       # Tone.js MIDI playback
        chat-agent.tsx        # AI Style Agent chat UI
        analysis-inspector.tsx# Full analysis breakdown panel
        export-center.tsx     # Export format cards

  api-server/                # Node.js Express backend
    src/
      routes/
        projects.ts          # Thin aggregator (~25 lines)
        project-crud.routes.ts
        project-analysis.routes.ts
        project-arrangement.routes.ts
        project-files.routes.ts
        project-export.routes.ts
        jobs.ts              # Job status endpoints
        styles.ts            # Musical style list
        agent.ts             # AI agent proxy
      lib/
        project-helpers.ts   # Config, multer, token, job helpers
        project-simulation.ts # Mock pipeline simulation

  music-ai-backend/          # Python FastAPI backend
    api/
      routes.py              # Thin aggregator (11 routes imported)
      health_routes.py       # /health, /styles, /personas, /cache
      analysis_routes.py     # /analyze → background pipeline
      arrangement_routes.py  # /arrange → background pipeline
      export_routes.py       # /export, /download
      render_routes.py       # /render → WAV/FLAC/MP3/Stems
      jobs_routes.py         # /jobs CRUD
      chords_routes.py       # Chord correction endpoints
      agent_routes.py        # AI agent session endpoints
      database.py            # DB helpers (psycopg2)
      schemas.py             # Pydantic request models
    analysis/                  # ← NEW v2 high-accuracy pipeline (2.0.0)
      pipeline.py            # Main entry: analyze(path, mode='balanced')
      schemas.py             # Pydantic v2 output schemas (AnalysisResult)
      preprocess.py          # Load + normalize + resample → AudioBundle
      separation.py          # Demucs 4.0.1 stem separation (4-stem)
      beat_tracker.py        # madmom RNN+DBN on drums stem
      key_detector.py        # Essentia HPCP on other stem
      chord_detector.py      # CQT chroma + template matching
      melody_detector.py     # torchcrepe on vocals stem
      structure_detector.py  # SSM + novelty curve
      smoothing.py           # Median filter, chord merging, pitch smoothing
      theory_correction.py   # Tempo trap fix, diatonic boosting
      confidence.py          # Global confidence + warnings
      ensemble.py            # Multi-source weighted voting
      fusion_engine.py       # FUSION ENGINE — confidence-weighted multi-source fusion
      theory_guard.py        # Final harmonic validation + scale snapping
      cache.py               # Disk-backed feature cache (7-day TTL)
    audio/                   # Legacy v1 pipeline (fallback)
      analyzer.py            # Full 9-step MIR pipeline (librosa only)
      rhythm.py              # BPM, beat grid, time sig
      key_mode.py            # Key, mode, modulations
      chords.py              # Chord detection
      melody.py              # F0/melody extraction
      structure.py           # Section detection (SSM)
      separator.py           # Stem separation (Demucs)
      export_engine.py       # MIDI/MusicXML export
      rendering.py           # Wavetable synthesis
      render_pipeline.py     # WAV/FLAC/MP3/Stems pipeline
    orchestration/
      arranger.py            # Multi-track MIDI arrangement (50+ genres)
      persona_loader.py      # YAML persona loader
      style_profile_adapter.py  # StyleProfile → arranger bridge
      harmonic_engine.py     # Harmonic analysis utilities
    agent/
      conversation_agent.py  # 3-phase agent: DISCOVERY→ENRICHMENT→EXECUTION
      style_enricher.py      # LLM enrichment + 30-day cache
      profile_validator.py   # StyleProfile validation
      style_database.py      # 50 YAML genre files with search
    config_paths.py          # ← SINGLE SOURCE OF TRUTH for all config file paths
    workers/
      celery_app.py          # Celery + Redis (graceful fallback)
      tasks/analysis.py
      tasks/arrangement.py
      tasks/render.py
    configs/styles/genres/   # 50 YAML genre files (klezmer, bossa nova, etc.)
    tests/                   # 847 tests, 6 skipped

lib/
  api-spec/                  # OpenAPI 3.1 spec (source of truth)
  api-client-react/          # Generated TanStack Query hooks
  api-zod/                   # Generated Zod validators
  db/schema/projects.ts      # Drizzle schema
```

## Key Features

### Audio Analysis (MIR)
- Rhythm: BPM, beat grid, time signature (madmom + librosa)
- Key/Mode: HPCP chroma + Krumhansl-Schmuckler profiles, modulation detection
- Chords: Extended vocabulary, template matching, Roman numerals, alternatives
- Melody: F0 extraction (pyin), note segmentation
- Structure: Self-similarity matrix + novelty detection, section labels
- Source Separation: Demucs (ML) + HPSS fallback → stems
- Feature caching: SHA-256 keyed disk cache, 7-day TTL

### Arrangement Engine
- 50+ musical styles via YAML genre database
- Multi-track MIDI: drums(ch9), bass, piano, guitar, strings, pad, brass, violin, oud, nay, qanun...
- 6 arranger personas (hasidic-wedding, cinematic, modern-pop, live-band, jazz-quartet, electronic-producer)
- Section-aware generation, performance humanization
- Lock/unlock fields during re-arrangement

### Export
- MIDI (.mid, multi-track via mido)
- MusicXML (.musicxml via music21)
- Lead Sheet PDF
- WAV (24-bit PCM), FLAC, MP3 (320kbps), Stems

### AI Style Agent
- Hebrew/English conversation (3 phases: DISCOVERY → ENRICHMENT → EXECUTION)
- LLM via OpenAI (Replit AI proxy) with YAML fallback
- StyleProfile → arrangement bridge

### Dev / Mock Mode
- `MOCK_MODE=true` (default in dev): Node.js simulates full pipeline, no Python needed
- `GET /api/projects/mock-mode` → `{isMock, pipelineVersion, modelVersions}`
- Mock results labelled `isMock: true`, amber banner in UI

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List projects (paginated) |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/:id` | Get project |
| DELETE | `/api/projects/:id` | Delete project |
| POST | `/api/projects/:id/upload` | Upload audio (200MB) |
| POST | `/api/projects/:id/analyze` | Start MIR analysis |
| GET | `/api/projects/:id/analysis` | Get analysis results |
| PATCH | `/api/projects/:id/corrections` | Override BPM/key/mode |
| POST | `/api/projects/:id/arrange` | Generate arrangement |
| GET | `/api/projects/:id/arrangement` | Get arrangement |
| POST | `/api/projects/:id/arrangement/section/:label/regenerate` | Regen section |
| POST | `/api/projects/:id/arrangement/track/:id/regenerate` | Regen track |
| POST | `/api/projects/:id/export` | Export MIDI/MusicXML/PDF |
| POST | `/api/projects/:id/render` | Render WAV/FLAC/MP3/Stems |
| GET | `/api/projects/:id/audio` | Stream original audio |
| GET | `/api/projects/:id/files` | List generated files |
| GET | `/api/jobs/:jobId` | Job status |
| POST | `/api/jobs/:jobId/cancel` | Cancel job |
| POST | `/api/jobs/:jobId/retry` | Retry failed job |
| GET | `/api/styles` | List arrangement styles |
| GET | `/api/styles/personas` | List arranger personas |
| GET | `/ws` | WebSocket job updates |

## Development Commands

```bash
# Python tests
python -m pytest artifacts/music-ai-backend/tests/ -v     # all 847 tests
pnpm test:unit                                              # unit only (fast)
pnpm test:service                                           # service tests
pnpm test:integration                                       # integration (no slow)
pnpm test:all                                               # all except slow

# Frontend
pnpm --filter @workspace/music-daw run test --run           # Vitest

# TypeScript check
pnpm tsc --noEmit

# DB schema push
pnpm --filter @workspace/db run push-force

# API types from OpenAPI spec
pnpm --filter @workspace/api-spec run codegen
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_MODE` | `true` | Use simulated pipeline (no Python needed) |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `LOCAL_STORAGE_PATH` | `/tmp/musicai_storage` | File storage root |
| `PYTHON_BACKEND_PORT` | `8001` | Python FastAPI port |
| `OPENAI_MODEL` | `gpt-4o-mini` | LLM model for AI agent |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker (optional) |
| `S3_ENDPOINT` | — | S3 storage (optional, local if not set) |

## Test Infrastructure (T004)

- **Markers**: `unit` / `service` / `integration` / `slow`
- **conftest.py fixtures**: `clean_test_cache` + `isolated_storage` (autouse, tmp_path), `test_client`, `mock_project`, `mock_analysis`, `mock_arrangement`
- **DB-free**: SQLite fallback via `DATABASE_URL=sqlite+aiosqlite:///./test_db.sqlite3`
- **Storage-isolated**: `LOCAL_STORAGE_PATH` → per-test tmp dir
- See `TESTING.md` for full guide
