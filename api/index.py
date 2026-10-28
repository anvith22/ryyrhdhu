"""Vercel Serverless Function entrypoint for FastAPI backend."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is on sys.path so backend modules and data are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app  # noqa: E402

# Expose app for Vercel Python runtime ASGI handler
__all__ = ["app"]
