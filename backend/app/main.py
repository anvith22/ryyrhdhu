"""FastAPI main application entrypoint for UK Wind Generation & Forecast Evaluation."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router as api_router

app = FastAPI(
    title="UK Wind Generation Forecast & Evaluation API",
    description=(
        "Analytics and decision-support API for UK power traders. "
        "Evaluates Elexon BMRS day-ahead wind generation forecasts against actuals. "
        "All calculations and timestamps operate strictly in UTC."
    ),
    version="1.0.0",
)

# Enable CORS for localhost frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",  # Permissive for local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all /api routes first so they take strict priority over static files
app.include_router(api_router)

# Resolve path to frontend distribution artifacts
FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not FRONTEND_DIST_DIR.exists():
    FRONTEND_DIST_DIR = Path("/app/frontend/dist")
if not FRONTEND_DIST_DIR.exists():
    FRONTEND_DIST_DIR = Path("frontend/dist").resolve()

if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "index.html").exists():
    # Mount assets folder if present
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback: serve static file if it exists, otherwise return index.html."""
        requested_file = FRONTEND_DIST_DIR / full_path
        if full_path and requested_file.is_file():
            return FileResponse(requested_file)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return {
            "name": "UK Wind Generation Forecast & Evaluation API",
            "docs_url": "/docs",
            "health_url": "/api/health",
            "status": "online",
            "timezone": "UTC",
        }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port)
