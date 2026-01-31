"""Health check endpoint."""

from fastapi import APIRouter, HTTPException
from app.dal.database import get_database
from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint with MongoDB connectivity test.

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
        health_response["status"] = "unhealthy"
        health_response["checks"]["database"] = "down"
        raise HTTPException(
            status_code=503,
            detail=health_response
        )

    return health_response
