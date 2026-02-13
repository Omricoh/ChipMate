"""
ChipMate v2 FastAPI Application Entry Point.

This is the main application file that configures FastAPI, sets up middleware,
registers routes, manages MongoDB connection lifecycle, and serves the
React frontend as static files in production.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.dal.database import connect_to_mongo, close_mongo_connection, ensure_indexes, get_database
from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.games import router as games_router
from app.routes.chip_requests import router as chip_requests_router
from app.routes.notifications import router as notifications_router
from app.routes.admin import router as admin_router
from app.tasks import start_expiry_checker, stop_expiry_checker

logger = logging.getLogger("chipmate.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events for MongoDB connection.
    """
    # Startup: Connect to MongoDB and ensure indexes
    try:
        await connect_to_mongo()
        db = get_database()
        await ensure_indexes(db)
        logger.info("ChipMate v%s started with database connection", settings.APP_VERSION)

        # Start background task for game expiry
        start_expiry_checker()
    except Exception as e:
        # Allow the app to start even if MongoDB is not available
        # This enables Railway health checks to pass during initial deployment
        logger.warning(
            "Failed to connect to MongoDB during startup: %s. "
            "Application will start but database operations will fail until connection is established.",
            str(e)
        )
        logger.info("ChipMate v%s started WITHOUT database connection", settings.APP_VERSION)

    yield

    # Shutdown: Stop background tasks and close MongoDB connection
    stop_expiry_checker()
    await close_mongo_connection()
    logger.info("ChipMate v2 shutdown complete")


# Initialize FastAPI application
app = FastAPI(
    title="ChipMate v2 API",
    description="Live poker game management system - REST API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Player-Token"],
    expose_headers=["X-Request-ID"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Register routers
app.include_router(health_router)  # Health endpoint at root level
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(games_router, prefix="/api")
app.include_router(chip_requests_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


# ---------------------------------------------------------------------------
# Serve React frontend (production: built files from ../frontend/dist)
# ---------------------------------------------------------------------------

# Resolve the frontend dist directory relative to this file.
# In nixpacks deployment: /app/backend/app/main.py -> /app/frontend/dist
# Locally: backend/app/main.py -> frontend/dist
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    from fastapi.responses import FileResponse

    # Mount static assets (JS, CSS, images, etc.) at /assets
    # The Vite build outputs these to dist/assets/
    _ASSETS_DIR = _FRONTEND_DIST / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

    # Serve other static files (favicon, etc.) from the dist root
    @app.get("/favicon.ico")
    async def favicon():
        favicon_path = _FRONTEND_DIST / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(str(favicon_path))
        return Response(status_code=404)

    @app.get("/vite.svg")
    async def vite_svg():
        svg_path = _FRONTEND_DIST / "vite.svg"
        if svg_path.exists():
            return FileResponse(str(svg_path), media_type="image/svg+xml")
        return Response(status_code=404)

    # SPA catch-all: serve index.html for all non-API routes
    # This enables client-side routing (React Router)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA index.html for all non-API routes.

        This catch-all route enables client-side routing. When a user
        navigates directly to /game/abc123 or /join/XYZ789, the server
        returns index.html and React Router handles the routing.
        """
        # Don't serve index.html for API routes (they're handled above)
        # or for requests that look like static files
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            return Response(status_code=404)

        index_path = _FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path), media_type="text/html")
        return Response(status_code=404)

    logger.info("Serving frontend SPA from %s", _FRONTEND_DIST)
else:
    @app.get("/")
    async def root():
        """Root endpoint - API information (no frontend build found)."""
        return {
            "name": "ChipMate v2 API",
            "version": settings.APP_VERSION,
            "status": "operational",
            "docs": "/docs",
            "health": "/health",
        }

    logger.info("No frontend build found at %s — API-only mode", _FRONTEND_DIST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
