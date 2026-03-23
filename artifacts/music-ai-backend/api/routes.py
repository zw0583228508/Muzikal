"""
API routes aggregator.

Combines all domain-specific routers into a single router.
Imported by main.py as: from api.routes import router

Domain modules:
  health_routes      — /models, /storage/serve, /styles
  analysis_routes    — /analyze
  arrangement_routes — /arrange
  export_routes      — /export, /projects/{id}/export/bundle
  render_routes      — /render
  jobs_routes        — /jobs/{id}/cancel
  chords_routes      — /chords/{chord}/substitutions
"""

from fastapi import APIRouter

from api.health_routes import router as health_router
from api.analysis_routes import router as analysis_router
from api.arrangement_routes import router as arrangement_router
from api.export_routes import router as export_router
from api.render_routes import router as render_router
from api.jobs_routes import router as jobs_router
from api.chords_routes import router as chords_router

router = APIRouter()

router.include_router(health_router)
router.include_router(analysis_router)
router.include_router(arrangement_router)
router.include_router(export_router)
router.include_router(render_router)
router.include_router(jobs_router)
router.include_router(chords_router)
