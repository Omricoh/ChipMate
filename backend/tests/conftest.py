"""
Pytest configuration and fixtures for ChipMate v2 tests.

This module provides shared fixtures for testing async FastAPI endpoints
and MongoDB interactions using mongomock-motor (no real MongoDB required).
"""

import os

# Set required env vars before any app imports
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")
# Disable rate limiting in tests
os.environ["TESTING"] = "1"

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def anyio_backend():
    """Specify anyio backend for async tests."""
    return "asyncio"


@pytest_asyncio.fixture
async def test_db():
    """In-memory MongoDB mock database for unit tests.

    Uses mongomock-motor so no real MongoDB instance is needed.
    The database is ephemeral -- it disappears after each test.

    Yields:
        An AsyncIOMotorDatabase-compatible mock database instance.
    """
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints.

    Yields:
        AsyncClient: HTTPX async client with the FastAPI app.
    """
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
