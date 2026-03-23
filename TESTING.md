# Muzikal — Testing Guide

## Quick Start

```bash
# All Python tests (847+, takes ~35s)
python -m pytest artifacts/music-ai-backend/tests/ -v

# Unit tests only (fast, < 10s)
python -m pytest -m unit -q

# Service tests (file I/O, module-level, ~15s)
python -m pytest -m service -q

# Integration tests (starts FastAPI app)
python -m pytest -m integration -q

# Skip slow tests (> 5s)
python -m pytest -m "not slow" -q
```

## Test Categories

| Mark | What it covers | Speed |
|------|---------------|-------|
| `unit` | Pure logic, no I/O, no network | < 1s each |
| `service` | One module with real tmp filesystem | < 3s each |
| `integration` | Full FastAPI app via TestClient | < 5s each |
| `slow` | Integration tests with ML pipelines | 5–60s |

## Test Files

### Unit tests (`-m unit`)
| File | Coverage |
|------|----------|
| `test_chords.py` | `audio/chords.py` — chord detection |
| `test_rhythm.py` | `audio/rhythm.py` — BPM, time sig, beat grid |
| `test_key_mode.py` | `audio/key_mode.py` — key, mode, modulations |
| `test_harmonic_engine.py` | `orchestration/harmonic_engine.py` |
| `test_chord_substitutions.py` | Chord substitution rules |
| `test_structure.py` | `audio/structure.py` — section detection |
| `test_celery_workers.py` | Celery availability + task callability |
| `test_persona_loader.py` | `orchestration/persona_loader.py` — YAML loader |
| `test_personas.py` | Apply persona to arrangement |
| `test_style_profile_adapter.py` | StyleProfile → arranger bridge |

### Service tests (`-m service`)
| File | Coverage |
|------|----------|
| `test_feature_cache.py` | `packages/audio_core/feature_cache.py` — disk cache |
| `test_storage_provider.py` | `storage/storage_provider.py` — Local/S3 |
| `test_export_engine.py` | `audio/export_engine.py` — MIDI/MusicXML export |
| `test_conversation_agent.py` | `agent/conversation_agent.py` — LLM sessions |
| `test_style_enricher.py` | `agent/style_enricher.py` — LLM enrichment |
| `test_yaml_genres.py` | 50 YAML genre files — structure validation |

### Integration tests (`-m integration`)
| File | Coverage |
|------|----------|
| `test_api_routes.py` | FastAPI endpoints: health, styles, cache, analysis, arrangement, jobs |
| `test_jobs.py` | Job lifecycle via TestClient |
| `test_regen_endpoints.py` | Section/track regeneration endpoints, personas endpoint |
| `test_arranger_integration.py` (**slow**) | Full arranger pipeline |

## Fixtures (conftest.py)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `clean_test_cache` | function (autouse) | Isolated `FEATURE_CACHE_DIR` per test |
| `isolated_storage` | function (autouse) | Isolated `LOCAL_STORAGE_PATH` per test |
| `test_client` | session | FastAPI `TestClient` for integration tests |
| `mock_project` | function | Minimal project dict |
| `mock_analysis` | function | Minimal analysis result |
| `mock_arrangement` | function | Minimal arrangement result |

## Environment

Tests run without a live Postgres (SQLite fallback via `DATABASE_URL`).
Tests never touch production storage (autouse `isolated_storage` fixture).

```bash
# If you need to test against a real DB, override:
DATABASE_URL=postgresql://... python -m pytest -m integration
```

## CI Commands

```bash
# Match CI unit job:
python -m pytest -m "unit or service" --tb=short --timeout=30 -q

# Match CI integration job:
python -m pytest -m "integration and not slow" --tb=short --timeout=60 -q

# Full suite without slow tests (matches python-all CI job):
python -m pytest artifacts/music-ai-backend/tests/ -m "not slow" --tb=short -q
```

## Frontend Tests

```bash
# Run all Vitest tests (from repo root)
pnpm --filter @workspace/music-daw run test --run

# Watch mode (development)
pnpm --filter @workspace/music-daw run test
```

## TypeScript

```bash
# Full monorepo typecheck
pnpm tsc --noEmit
```
