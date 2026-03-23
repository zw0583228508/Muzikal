"""
Muzikal — monorepo bootstrap entrypoint.

This file is NOT the application server. It documents how to start each service.

── How to run ────────────────────────────────────────────────────────────────

  Python backend (FastAPI):
      cd artifacts/music-ai-backend
      uvicorn main:app --host 0.0.0.0 --port 8001 --reload

  Node API server:
      pnpm --filter @workspace/api-server run dev

  Frontend (React/Vite):
      pnpm --filter @workspace/music-daw run dev

  All services (via Replit workflows):
      Use the workflow panel — workflows are pre-configured.

── Architecture ──────────────────────────────────────────────────────────────

  Frontend (React/Vite)  :19270  ── public UI
  Node API (Express)     :8080   ── public REST API  (/api/...)
  Python backend (FastAPI):8001  ── internal service (/python-api/...)

  The Node API is the single public entrypoint.
  The Python backend is an internal service — not directly exposed to browsers.
  The frontend communicates exclusively with the Node API.

── Testing ───────────────────────────────────────────────────────────────────

  Python backend tests:
      cd artifacts/music-ai-backend && python -m pytest tests/ -v

  Frontend tests:
      pnpm --filter @workspace/music-daw run test

  TypeScript typecheck:
      pnpm --filter @workspace/api-server run typecheck

── Environment variables ─────────────────────────────────────────────────────

  LOCAL_STORAGE_PATH   Override storage root (default: /app/storage, dev: /tmp/musicai_storage)
  OPENAI_MODEL         LLM model (default: gpt-4o-mini)
  DATABASE_URL         PostgreSQL connection string
  REDIS_URL            Redis URL for Celery (optional)

See replit.md for full architecture documentation.
"""

if __name__ == "__main__":
    import sys
    print(__doc__)
    print("To start the Python backend, run:")
    print("  cd artifacts/music-ai-backend && uvicorn main:app --host 0.0.0.0 --port 8001")
    sys.exit(0)
