"""Integration tests for settlement route handlers.

Tests the full HTTP stack using HTTPX AsyncClient with the FastAPI app
and mongomock-motor (no real MongoDB required).
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.dal import database as db_module
from app.auth import dependencies as auth_deps_module
from app.routes import games as games_route_module
from app.routes import chip_requests as chip_requests_route_module
from app.routes import notifications as notifications_route_module
from app.routes import settlement as settlement_route_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock MongoDB database and patch all get_database refs."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]

    getter = lambda: db
    originals = {
        "db": db_module.get_database,
        "auth": auth_deps_module.get_database,
        "games": games_route_module.get_database,
        "requests": chip_requests_route_module.get_database,
        "notifications": notifications_route_module.get_database,
        "settlement": settlement_route_module.get_database,
    }

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter
    chip_requests_route_module.get_database = getter
    notifications_route_module.get_database = getter
    settlement_route_module.get_database = getter

    yield db

    db_module.get_database = originals["db"]
    auth_deps_module.get_database = originals["auth"]
    games_route_module.get_database = originals["games"]
    chip_requests_route_module.get_database = originals["requests"]
    notifications_route_module.get_database = originals["notifications"]
    settlement_route_module.get_database = originals["settlement"]
    client.close()


@pytest_asyncio.fixture
async def test_client(mock_db):
    """Async HTTP client wired to the FastAPI app with mocked db."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_game(test_client, manager_name="Alice"):
    resp = await test_client.post("/api/games", json={"manager_name": manager_name})
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client, game_id, player_name):
    resp = await test_client.post(
        f"/api/games/{game_id}/join", json={"player_name": player_name}
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_and_approve_request(test_client, game_id, player_token, manager_token, amount=100, request_type="CASH"):
    """Create a chip request and approve it so the player has buy-in history."""
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": request_type, "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    req_id = resp.json()["id"]
    resp = await test_client.post(
        f"/api/games/{game_id}/requests/{req_id}/approve",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/start
# ---------------------------------------------------------------------------

class TestStartSettling:

    @pytest.mark.asyncio
    async def test_start_settling_returns_200(self, test_client):
        game = await _create_game(test_client)
        game_id = game["game_id"]
        manager_token = game["player_token"]

        # Add a player with a buy-in so there's data to freeze
        bob = await _join_game(test_client, game_id, "Bob")
        await _create_and_approve_request(
            test_client, game_id, bob["player_token"], manager_token
        )

        resp = await test_client.post(
            f"/api/games/{game_id}/settlement/start",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SETTLING"
        assert data["game_id"] == game_id
        assert "cash_pool" in data
        assert "player_count" in data

    @pytest.mark.asyncio
    async def test_start_settling_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settlement/start",
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_start_settling_non_manager_returns_403(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settlement/start",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/submit-chips
# ---------------------------------------------------------------------------

class TestSubmitChips:

    @pytest.mark.asyncio
    async def test_submit_chips_returns_submitted(self, test_client):
        game = await _create_game(test_client)
        game_id = game["game_id"]
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game_id, "Bob")
        await _create_and_approve_request(
            test_client, game_id, bob["player_token"], manager_token
        )

        # Start settling
        await test_client.post(
            f"/api/games/{game_id}/settlement/start",
            headers={"X-Player-Token": manager_token},
        )

        # Bob submits chips
        resp = await test_client.post(
            f"/api/games/{game_id}/settlement/submit-chips",
            json={"chip_count": 80, "preferred_cash": 80, "preferred_credit": 0},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submit_chips_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settlement/submit-chips",
            json={"chip_count": 80, "preferred_cash": 80, "preferred_credit": 0},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/pool
# ---------------------------------------------------------------------------

class TestGetPool:

    @pytest.mark.asyncio
    async def test_get_pool_returns_state(self, test_client):
        game = await _create_game(test_client)
        game_id = game["game_id"]
        manager_token = game["player_token"]

        resp = await test_client.get(
            f"/api/games/{game_id}/settlement/pool",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "cash_pool" in data
        assert "credit_pool" in data
        assert "settlement_state" in data

    @pytest.mark.asyncio
    async def test_get_pool_requires_manager(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/settlement/pool",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/close
# ---------------------------------------------------------------------------

class TestCloseGame:

    @pytest.mark.asyncio
    async def test_close_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settlement/close",
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_close_non_manager_returns_403(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settlement/close",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403
