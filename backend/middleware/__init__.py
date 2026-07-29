"""FastAPI middleware for the application."""

from backend.middleware.cors import setup_cors

__all__ = ["setup_cors"]
