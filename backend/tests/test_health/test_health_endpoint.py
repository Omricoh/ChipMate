"""Tests for the health check endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from app.config import settings


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test the /health endpoint behavior."""

    async def test_health_endpoint_returns_200_when_db_is_healthy(self, client):
        """Health check returns 200 OK when database is connected."""
        # Mock successful database ping
        with patch('app.routes.health.get_database') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.command = AsyncMock(return_value={"ok": 1})
            mock_get_db.return_value = mock_db

            response = await client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["version"] == settings.APP_VERSION
            assert data["checks"]["database"] == "ok"

    async def test_health_endpoint_returns_200_when_db_is_down(self, client):
        """Health check returns 200 OK even when database is down."""
        # Mock database connection failure
        with patch('app.routes.health.get_database') as mock_get_db:
            mock_get_db.side_effect = RuntimeError("Database not initialized")

            response = await client.get("/health")

            # Should still return 200, not 503
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["database"] == "down"

    async def test_health_endpoint_returns_200_when_db_ping_fails(self, client):
        """Health check returns 200 OK when database ping fails."""
        # Mock database ping failure
        with patch('app.routes.health.get_database') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.command = AsyncMock(side_effect=Exception("Connection timeout"))
            mock_get_db.return_value = mock_db

            response = await client.get("/health")

            # Should still return 200, not 503
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["database"] == "down"

    async def test_health_endpoint_at_api_prefix(self, client):
        """Health check is also available at /api/health."""
        with patch('app.routes.health.get_database') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.command = AsyncMock(return_value={"ok": 1})
            mock_get_db.return_value = mock_db

            response = await client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "version" in data
