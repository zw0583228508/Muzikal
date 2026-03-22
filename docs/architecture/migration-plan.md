# Migration Plan — Current → Target

## Phase 1: Stabilize (DONE ✅)

- [x] All workflows boot cleanly
- [x] 120 tests passing
- [x] Mock mode fully functional
- [x] Job system visible and debuggable
- [x] Confidence + warnings on all analysis modules
- [x] Lock system (7 components)
- [x] Chord editing with alternatives in UI
- [x] PIPELINE_VERSION + MODEL_VERSIONS tracking

## Phase 2: Upgrade Analysis (IN PROGRESS 🔄)

- [x] rhythm.py — beat tracking + confidence
- [x] key_mode.py — Essentia + chroma + alternatives
- [x] chords.py — template + HMM + confidence
- [x] melody.py — pyin + basic-pitch + confidence
- [x] structure.py — MSAF + confidence
- [x] vocal_analysis.py — pyin + confidence + warnings
- [ ] Feature extraction cache (keyed by audio checksum)
- [ ] Tonal timeline (key modulation over time)
- [ ] Feature reuse across jobs (one extraction → all analysis)

## Phase 3: Real Async Workers (PLANNED)

- [ ] Add Redis (Replit integration or managed)
- [ ] Implement Celery app + workers (analysis, arrangement, render)
- [ ] Job schema: add startedAt, finishedAt, errorCode, inputPayload
- [ ] Job retry endpoint
- [ ] Job cancel endpoint (Celery revoke)
- [ ] Worker health checks

## Phase 4: Stem Separation (PLANNED)

- [ ] Provider abstraction interface for separator
- [ ] Cache stems by audio checksum + model version
- [ ] Frontend stem preview player
- [ ] "Export rehearsal without vocals" option

## Phase 5: Rebuild Arranger (IN PROGRESS 🔄)

- [x] Section-aware arrangement (intro/verse/chorus/outro)
- [x] Transitions (build/drop/fade/crossfade)
- [x] Instrumentation plan
- [x] Harmonic plan
- [ ] Arranger personas (6 personas in YAML)
- [ ] Regenerate-by-section
- [ ] Regenerate-by-track
- [ ] "Make drums simpler" semantic controls

## Phase 6: Render + Export (PLANNED)

- [x] Preview render (FluidSynth/pedalboard)
- [x] High-quality render scaffold
- [x] MIDI export
- [x] MusicXML export
- [ ] Object storage for exports (replace /tmp)
- [ ] Signed URL generation
- [ ] Archive bundle (JSON timeline + MIDI + metadata)

## Phase 7: Harden for Production (PLANNED)

- [ ] Docker + docker-compose for all services
- [ ] Observability (structured logging, correlation IDs, tracing)
- [ ] Quotas + job limits
- [ ] Authenticated project ownership
- [ ] Signed asset access
- [ ] Smoke tests
- [ ] GPU deployment configs

## File-by-File Migration Plan

### Keep As-Is
- `audio/rhythm.py` — solid hybrid DSP+ML
- `audio/key_mode.py` — solid Essentia integration
- `audio/chords.py` — solid template+HMM
- `audio/melody.py` — solid pyin pipeline
- `audio/structure.py` — solid MSAF
- `audio/vocal_analysis.py` — solid pyin+confidence
- `audio/separator.py` — solid Demucs wrapper
- `packages/audio_core/ingestion.py` — production-grade
- `packages/common-schemas/` — all Zod schemas up to date

### Enhance
- `audio/analyzer.py` — add feature cache integration
- `orchestration/arranger.py` — add persona support + regen-by-scope
- `main.py` — add /health, /models, /cache endpoints
- `lib/db/src/schema/projects.ts` — add startedAt, finishedAt, errorCode
- `artifacts/api-server/src/routes/projects.ts` — add retry/cancel endpoints

### Create
- `packages/audio_core/feature_cache.py` — disk cache by checksum
- `orchestration/arranger_personas.yaml` — 6 persona definitions
- `workers/celery_app.py` — Celery app definition
- `workers/tasks/analysis.py` — analysis tasks
- `workers/tasks/arrangement.py` — arrangement tasks
- `workers/tasks/render.py` — render tasks
- `artifacts/music-daw/src/pages/analysis-inspector.tsx` — new frontend page

### Remove / Replace
- `audio/mixing.py` — replace with pedalboard-based mixing
- `workers/__init__.py` (stub) — replace with real Celery app

## Dependency Order

```
Feature Cache → Updated Analyzer → Updated Tests
    ↓
Job Schema Hardening → Retry/Cancel API → Updated Frontend

Arranger Personas → Regen-by-section → Regen-by-track
    ↓
Analysis Inspector (frontend, reads existing data)

Redis Setup → Celery Workers → Job Migration
    ↓
Object Storage → Signed URLs → Export Center
    ↓
Docker → Production Deploy
```
