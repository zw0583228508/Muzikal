# Current State — MusicAI Studio (Muzikal)

> Audit date: 2026-03-22 · Pipeline version 1.1.0

## Overall Architecture

```
Browser (React/TS)
    │  HTTP + WebSocket
    ▼
Node.js API Server (Express, port 8080)
    │  HTTP (MOCK_MODE bypass)
    ▼
Python FastAPI Backend (port 8001, internal)
    │
    ├─ audio/  (analysis modules)
    ├─ orchestration/ (arrangement engine)
    └─ workers/ (stub — not yet implemented)
```

## Services

| Service | Tech | Status |
|---------|------|--------|
| Frontend | React 19 + Vite + Tailwind | ✅ Running |
| API Server | Node.js + Express 5 + Drizzle ORM | ✅ Running |
| Python Backend | FastAPI + librosa + Essentia | ✅ Running |
| Database | PostgreSQL (Replit managed) | ✅ Running |
| Redis | Not configured | ❌ Missing |
| Celery Workers | Stub only | ❌ Missing |
| Object Storage | Local disk (`/tmp`) | ⚠️ Ephemeral |

## Python Analysis Modules

| Module | Method | Confidence | Cache |
|--------|--------|------------|-------|
| rhythm.py | librosa beat_track + madmom fallback | ✅ | ❌ |
| key_mode.py | Essentia + chroma heuristic | ✅ | ❌ |
| chords.py | Chroma template + HMM smoothing | ✅ | ❌ |
| melody.py | pyin + basic-pitch fallback | ✅ | ❌ |
| structure.py | librosa MSAF novelty | ✅ | ❌ |
| vocal_analysis.py | pyin, voiced ratio | ✅ | ❌ |
| separator.py | Demucs htdemucs | ✅ | ❌ |
| analyzer.py | Orchestrator (no cache) | — | ❌ |

## Arrangement Engine

| Layer | Status | Notes |
|-------|--------|-------|
| Style profiles (YAML) | ✅ | 15 styles loaded |
| Arranger profiles (YAML) | ✅ | density/instrument rules |
| Track generators | ✅ | drums, bass, piano, strings, guitar |
| Harmonic plan | ✅ | per-section chord summary |
| Transitions | ✅ | build/drop/fade/crossfade |
| Instrumentation plan | ✅ | per-instrument density |
| Arranger personas | ❌ | Not yet implemented |
| Regenerate-by-section | ❌ | Not yet implemented |
| Regenerate-by-track | ❌ | Not yet implemented |

## Job System

| Feature | Status |
|---------|--------|
| Job types | upload, analysis, arrangement, export, render |
| Job statuses | queued, running, completed, failed, cancelled |
| WebSocket progress | ✅ Real-time via ws |
| Job persistence | ✅ PostgreSQL |
| startedAt / finishedAt | ❌ Missing from schema |
| errorCode | ❌ Missing from schema |
| inputPayload / outputPayload | ❌ Missing from schema |
| Retry / cancel | ❌ Not implemented |
| Celery async workers | ❌ Not implemented |

## Frontend Pages

| Page | Status |
|------|--------|
| Home / Upload | ✅ |
| Project Studio | ✅ (analysis + arrangement + export tabs) |
| Analysis Inspector | ❌ Not implemented |
| Export Center | ⚠️ Partial (in Studio tabs) |

## What Works Today

- Full mock-mode pipeline: upload → analyze → arrange → export (simulated)
- 120 passing automated tests
- Real Python analysis runs when a real audio file is uploaded
- Chord editing with alternatives in UI
- Section transitions and instrumentation plan visible in UI
- Lock system for 7 components (harmony, structure, melody, tracks, key, chords, bpm)
- Hebrew/English i18n

## Known Gaps

1. No feature caching — every analysis recomputes all features
2. No Redis/Celery — jobs run as in-process promises
3. No object storage — stems/exports stored in ephemeral /tmp
4. No arranger personas — style profiles only
5. No regenerate-by-section or regenerate-by-track
6. No Analysis Inspector page
7. Job schema missing startedAt, finishedAt, errorCode
8. No model registry
9. No Docker/production deployment configuration
