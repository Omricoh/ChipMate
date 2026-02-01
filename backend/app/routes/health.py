"""Health check endpoint."""

import logging
from fastapi import APIRouter
from app.dal.database import get_database
from app.config import settings

logger = logging.getLogger("chipmate.routes.health")
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint with MongoDB connectivity test.
    
    Returns 200 OK even if database is unavailable to allow the service
    to start up and accept traffic. The database status is reported in
    the response body for monitoring purposes.

    Returns:
        dict: Health status, version, and database connectivity status.
    """
    health_response = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "checks": {
            "database": "unknown"
        }
    }

    # Test database connectivity
    try:
        db = get_database()
        await db.command("ping")
        health_response["checks"]["database"] = "ok"
    except Exception as e:
        # Log the error but don't fail the health check
        # This allows the service to start even if MongoDB is temporarily unavailable
        logger.warning("Database health check failed: %s", str(e))
        health_response["checks"]["database"] = "down"
        health_response["status"] = "degraded"

    return health_response
