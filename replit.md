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

### T008 — Tests + replit.md Update ✅ (expanded to 188 tests)
- **188 Python tests passing, 4 skipped** (`python -m pytest tests/ -v`)
- `tests/test_feature_cache.py` — 9 tests: miss/hit, TTL expiry, stats, clear, complex JSON
- `tests/test_personas.py` — 9 tests: all 6 personas present, schema validation, `apply_persona_to_arrangement`
- `tests/test_jobs.py` — 12 tests: Celery fallback, health/styles/cancel/422 validation
- `tests/test_regen_endpoints.py` — 9 integration tests: regen-section, regen-track, personas endpoint
- `tests/test_key_mode.py` — 23 tests: chroma_to_key, top_k, analyze_key, modulation confidence
- `tests/test_storage_provider.py` — 17 tests: LocalStorage CRUD, singleton factory, S3 env routing
- `tests/test_rhythm.py` — 15 tests: BPM plausibility, time sig format, silence/noise fallback
- `tests/test_chords.py` — 10 tests: analyze_chords signature, chord timeline, monotonicity
- `tests/test_structure.py` — 12 tests: analyze_structure signature, segments, monotonic times
- `tests/test_export_engine.py` — 30 tests: export_midi (MThd header), export_musicxml, run_export
- `tests/test_persona_loader.py` — 17 tests: load/get all 6 personas, uniqueness, None on unknown
- `tests/test_celery_workers.py` — 11 tests: import, CELERY_AVAILABLE bool, task callability
- `tests/test_api_routes.py` — 18 tests: health, styles, cache, analysis, arrangement, jobs endpoints
- `tests/conftest.py` — autouse cache fixture + test_client (FastAPI TestClient) + mock_project fixture
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

## Phase 2+ Features (Current Session)

### Export Center ✅
- `artifacts/music-daw/src/pages/export-center.tsx` — unified Export tab with format cards
- Score group: MIDI, MusicXML, Lead Sheet PDF
- Audio group: WAV (24-bit), FLAC, MP3 320kbps, Stems (per-instrument)
- Format selection with toggle cards + single Export button
- Downloads list with file metadata + direct download links
- Integrated into project-studio.tsx Export tab (replaced inline form)

### Storage Abstraction ✅
- `artifacts/music-ai-backend/storage/storage_provider.py` — `StorageProvider` ABC
- `LocalStorage`: writes to `/tmp/muzikal` (or `LOCAL_STORAGE_PATH`)
- `S3Storage`: boto3 + presigned URLs (activated when `S3_ENDPOINT` env var set)
- `get_storage()` factory returns singleton; auto-selects backend from environment

### Docker Compose + Dockerfiles ✅
- `docker-compose.yml` — full stack: postgres, redis, python-backend, celery-worker, api-server, frontend
- `artifacts/music-ai-backend/Dockerfile` — python:3.11-slim, ffmpeg, uvicorn 2-worker
- `artifacts/api-server/Dockerfile` — node:20-slim multi-stage builder + runtime
- `artifacts/music-daw/Dockerfile` — node:20-slim build + nginx:alpine SPA server
- Named volumes: postgres_data, redis_data, audio_storage, stems_storage
- Health checks on all services

### Tonal Timeline Improvement ✅
- `audio/key_mode.py` — modulation entries now include `confidence` field (was missing)
- Each `{"timeSeconds", "fromKey", "toKey", "confidence"}` — confidence in [0.0, 1.0]

### Pagination + Correlation IDs ✅
- `GET /api/projects` returns `{projects, pagination}` with `page`, `limit`, `total`, `pages`
- `home.tsx` handles both legacy array and new paginated shape transparently
- Pagination footer shown when `pages > 1`
- `x-correlation-id` header propagated on every request (generated if missing)

## Universal Style Engine (Phase 3) ✅

### Python Agent Package (`agent/`)
- `agent/__init__.py` — exports ConversationAgent, StyleEnricher, ProfileValidator, StyleDatabase, prompts
- `agent/conversation_agent.py` — 3-phase agent: DISCOVERY → ENRICHMENT → EXECUTION
  - In-memory session store (session_id → ConversationAgent)
  - `create_session()`, `get_session()`, `delete_session()` session management
  - `_extract_params_heuristic()` — Hebrew + English keyword extraction fallback
  - `HEBREW_GENRE_ALIASES` — maps Hebrew genre names to genre IDs
  - Calls LLM via OpenAI SDK (Replit AI proxy) when `AI_INTEGRATIONS_OPENAI_BASE_URL` is set
- `agent/style_enricher.py` — LLM enrichment + 30-day cache (`configs/ai_knowledge_cache.json`)
  - `_adapt_to_analysis()` — adjusts BPM range, sets detectedKey, sets scaleType from analysis
  - `_build_from_yaml()` — YAML fallback with volume weight budget ≤ 4.0
  - Cache key: `{genre}:{era}:{region}`, TTL=30 days
- `agent/profile_validator.py` — validates StyleProfile before arrangement
  - Required roles: BASS, RHYTHM_KICK, MELODY_LEAD
  - `midiProgram` must be 0–127; `volumeWeight` sum ≤ 4.0; `bpmRange[0]` < `[1]`
- `agent/prompts.py` — EXTRACTION_PROMPT + ENRICHMENT_PROMPT + CLARIFICATION_QUESTIONS
- `agent/style_database.py` — YAML loader with search, fallback, find_by_parent

### YAML Genre Database (`configs/styles/genres/`)
11 genres: klezmer, bossa_nova, flamenco, maqam_hijaz, afrobeat, hasidic_nigun, tango, jazz_bebop, celtic, sephardic, generic_world_music (fallback)
Each file: harmony (scale_type, progressions, cadences), rhythm (bpm_range, time_signature, patterns), instrumentation (core, optional, avoid), ornaments, reference_artists, gm_programs

### Python API Routes (`api/agent_routes.py`)
- `POST /agent/chat` — sends message to agent, creates/resumes session
- `GET /agent/session/:id` — returns session state and collected_params
- `POST /agent/confirm` — confirms StyleProfile, validates it
- `GET /agent/genres` — lists all YAML genres with metadata
- `GET /agent/styles/:id/profile` — returns raw YAML for a genre
- `POST /agent/enrich` — direct LLM enrichment endpoint

### Node.js API Routes (`api-server/src/routes/agent.ts`)
Mounted at `/api/agent`, proxies to Python backend:
- POST /api/agent/chat, GET /api/agent/session/:id, POST /api/agent/confirm, POST /api/agent/enrich
Also added to stylesRouter: GET /api/styles/genres, GET /api/styles/:id/profile

### Frontend Components
- `components/chat-agent.tsx` — Hebrew RTL chat UI with:
  - Bubble messages (user/assistant), loading states, phase indicator
  - Auto-scrolls to latest message
  - Shows StyleProfileCard when profile is ready
  - Sends to `/api/agent/chat`, calls `/api/agent/confirm`
- `components/style-profile-card.tsx` — visual preview of StyleProfile with:
  - Instrument badges with role-colored pills + icons
  - Rhythm panel (time signature, BPM, swing) + harmony panel (scale, chords)
  - Section labels, texture, reverb, humanization fields
  - "Confirm & Process" button
- **5th tab added to project-studio.tsx** — "AI Style Agent" / "סוכן AI"

### i18n Updates
- en.ts + he.ts: agent.* keys (title, phases, placeholder, confirm) + genres.* keys (10 genres)

### Tests: 360 passing (from 188), 6 skipped
- `test_yaml_genres.py` — 30+ tests: YAML structure, bpm_range validity, id=filename, StyleDatabase CRUD
- `test_conversation_agent.py` — 24 tests: sessions, AgentResponse, heuristic extraction (Hebrew+English), process_message
- `test_style_enricher.py` — 24 tests: cache TTL, adapt_to_analysis, build_from_yaml, enrich fallback

### OpenAI Integration
- `AI_INTEGRATIONS_OPENAI_BASE_URL` + `AI_INTEGRATIONS_OPENAI_API_KEY` provisioned via Replit AI proxy
- Python `openai>=1.40.0` package added to requirements.txt
- LLM calls use `gpt-5-mini` with `max_completion_tokens=2048`
- Graceful fallback: if no LLM client, uses YAML + heuristic extraction

## Step 7: StyleProfile → Arranger Bridge ✅

### New File: `orchestration/style_profile_adapter.py`
- **`adapt_profile_to_arranger_args(profile, analysis, persona_id)`** — main entry point
- **`_derive_style_id(profile)`** — maps genre → STYLES key with GENRE_PARENT_MAP fallback
- **`_extract_instruments(profile)`** — InstrumentConfig[] → canonical arranger instrument names
  - INSTRUMENT_NAME_MAP: clarinet→brass, kick→drums, flute→nay, voice_wordless→choir, etc.
  - Role ordering: MELODY_LEAD → HARMONY → BASS → RHYTHM → COLOR
  - Fallback: empty profile returns ["drums", "bass", "piano"]
- **`_derive_density(profile)`** — textureType: sparse→0.35, medium→0.60, layered→0.75, dense→0.90
- **`_derive_tempo_factor(profile, analysis)`** — detected BPM → target BPM midpoint, clamped 0.5–2.0
- **`_patch_analysis_with_profile(analysis, profile)`** — injects _profileScaleType, _profileHarmonicTendency, _profileTimeSignature, _profileSwingFactor, _profileGrooveTemplate, _profileOrnamentStyle, _profileChordVocabulary into analysis dict

### Updated: `orchestration/arranger.py`
- `generate_arrangement()` gains `style_profile: Optional[dict] = None` parameter
- When provided: injects swing/ornament/time_signature/groove into analysis; appends styleProfileGenre/Era/Region/isFallback to result
- `generate_drum_pattern()` gains `analysis: Optional[Dict] = None` parameter; reads `_profileTimeSignature` to override time_sig (3/4→3, 6/8→6, 7/8→7)

### Updated: `api/schemas.py`
- `ArrangeRequest`: added `persona_id: Optional[str]`, `style_profile: Optional[dict]`

### Updated: `api/routes.py`
- `start_arrangement()`: when `style_profile` present, calls adapter to derive style_id/instruments/density/persona_id
- `run_arrangement_pipeline()`: added `persona_id`, `style_profile` params; calls adapter on analysis before generate_arrangement

### Updated: `api/agent_routes.py`
- `confirm_profile()`: when `project_id` provided, auto-dispatches `/python-api/arrange` with `style_profile`; returns `arrangement_job_id`

### Updated: `artifacts/api-server/src/routes/projects.ts`
- `POST /:id/arrangement`: extracts `styleProfile` from req.body; passes `style_profile` to Python backend

### Updated: `artifacts/music-daw/src/components/chat-agent.tsx`
- `confirmProfile()`: two-step flow — (1) POST /api/agent/confirm with `session_id`, (2) POST /api/projects/:id/arrangement with `styleProfile`; shows job ID in chat

### Updated: `artifacts/music-daw/src/components/style-profile-card.tsx`
- isFallback badge text improved: "Fallback — AI data unavailable"

### Tests: `tests/test_style_profile_adapter.py` (55 tests, all passing)
- TestDeriveStyleId (12 tests), TestExtractInstruments (9), TestDeriveDensity (6), TestDeriveTempoFactor (6), TestPatchAnalysis (6), TestAdaptProfileFull (9), TestInstrumentNameMap (4), TestScaleToHarmonic (3)

## Final Test Counts: 411 passing, 10 skipped

All tests passing. Test breakdown by major feature:
- Core MIR analysis: rhythm, key, chords, melody, structure — 60+ tests
- Arranger engine: tracks, personas, sections — 40+ tests
- Universal Style Engine: conversation_agent, style_enricher, profile_validator, yaml_genres — 90+ tests
- StyleProfile Adapter (Step 7): 55 tests
- E2E endpoints: regen, cache, jobs, export — 100+ tests
- Audio core: feature_cache, ingestion — 30+ tests

## WaveSurfer.js + MIDI Player + 50 Genres ✅

### T001: WaveSurfer.js Interactive Waveform Player
- **New file**: `artifacts/music-daw/src/components/waveform-player.tsx`
- WaveSurfer.js v7 — peaks mode (pre-computed waveformData) + full audio mode (audioUrl)
- Audio streamed from `/api/projects/:id/audio` (HTTP range requests)
- Controls: Play/Pause, Skip Back, Zoom In/Out (10x–200x), Volume slider
- Keyboard: Space=play/pause, ←/→=seek 5s
- Dark theme, RTL-safe, loading/error states
- Replaced legacy `WaveformVisualizer` (static bar chart) in project-studio.tsx

### T002: Soundfont / MIDI Playback Engine
- **New file**: `artifacts/music-daw/src/components/midi-player.tsx`
- `soundfont-player` + Web Audio API — loads GM soundfonts from CDN per instrument
- Packages: `wavesurfer.js`, `soundfont-player`, `tone`
- GM Program Map: 50+ instrument mappings (piano, strings, brass, woodwinds, oud, ney, darbuka...)
- Per-track: Mute, Solo, Volume slider
- Master volume + progress bar + Play/Pause/Stop transport
- Integrated into Arrange tab of project-studio.tsx as "MIDI Preview" panel

### T003: 50 Genre YAML Database (11 → 50)
39 new genre files added:
- **African**: ethiopian_tizita, gnawa
- **Latin**: cumbia, salsa, reggaeton, mariachi, son_cubano
- **Middle East/Med**: turkish_makam, persian_classical, arabic_pop, greek_laiko, armenian_folk
- **Jewish/E.Europe**: ashkenazi_folk, mizrahi_pop, piyyut, romani_swing, bulgarian_folk, hungarian_csardas
- **Caribbean**: reggae, dancehall, ska, calypso
- **American Roots**: blues_delta, gospel, country, bluegrass, zydeco, new_orleans_jazz
- **Electronic**: ambient_drone, lo_fi_hiphop, dub_techno, drum_and_bass
- **Classical**: baroque, classical_era, romantic, impressionist
- **Contemporary**: neo_soul, trap, indie_folk
- All 50 files validated (id, display_name, harmony, rhythm, instrumentation, gm_programs)

### Final Test Counts: 801 passing, 10 skipped
- Parametrized genre tests auto-discovered all 50 YAML files
- +390 new tests from genre discovery (≈10 per genre file)
- All existing 411 tests still green

## Remaining Features (Future)

- FluidSynth/soundfont rendering server-side (higher quality audio export)
- 100+ additional genres
- AI-generated soundfont samples per cultural instrument
