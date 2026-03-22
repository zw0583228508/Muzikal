"""
MusicAI Studio - Python Audio Processing Backend
Handles: Source separation, MIR analysis, chord detection, melody extraction, arrangement generation
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MusicAI Backend...")
    await init_db()
    yield
    logger.info("Shutting down MusicAI Backend...")


app = FastAPI(
    title="MusicAI Studio API",
    description="AI-powered music intelligence and generation backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/python-api")


@app.get("/python-api/health")
async def health():
    return {"status": "ok", "service": "music-ai-backend"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PYTHON_BACKEND_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
