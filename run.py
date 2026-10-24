"""Application Launcher for Food Freshness Platform.

Runs the FastAPI Uvicorn development server with optimized file watchers
that ignore .venv and OneDrive synchronization noise.
Supports command-line arguments (--port, --host, --no-reload) with seamless
fallbacks to backend/.env and config settings.
"""
import argparse
from pathlib import Path
import sys
import uvicorn
from backend.app.config import BACKEND_DIR, settings

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{settings.PROJECT_NAME} Launcher")
    parser.add_argument(
        "--host",
        default=settings.HOST,
        help=f"Host address to bind server (default: {settings.HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.PORT,
        help=f"Port number to bind server (default: {settings.PORT})",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable automatic reload on code changes",
    )
    args, _ = parser.parse_known_args()

    reload_active = settings.DEBUG and not args.no_reload

    print(f"Starting {settings.PROJECT_NAME} on http://{args.host}:{args.port}")
    print(f"Monitoring code changes in: {BACKEND_DIR}")
    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=reload_active,
        reload_dirs=[str(BACKEND_DIR)] if reload_active else None,
    )
