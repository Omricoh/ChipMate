"""Integration tests for chip request route handlers.

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock MongoDB database and patch all get_database refs."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]

    getter = lambda: db
    orig_db = db_module.get_database
    orig_auth = auth_deps_module.get_database
    orig_games = games_route_module.get_database
    orig_requests = chip_requests_route_module.get_database
    orig_notifications = notifications_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter
    chip_requests_route_module.get_database = getter
    notifications_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth
    games_route_module.get_database = orig_games
    chip_requests_route_module.get_database = orig_requests
    notifications_route_module.get_database = orig_notifications
    client.close()


@pytest_asyncio.fixture
async def test_client(mock_db):
    """Async HTTP client wired to the FastAPI app with mocked db."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_game(test_client, manager_name="Alice"):
    resp = await test_client.post("/api/games", json={"manager_name": manager_name})
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client, game_id, player_name):
    resp = await test_client.post(f"/api/games/{game_id}/join", json={"player_name": player_name})
    assert resp.status_code == 201
    return resp.json()


async def _create_request(test_client, game_id, player_token, request_type="CASH", amount=100):
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": request_type, "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests -- Create chip request
# ---------------------------------------------------------------------------

class TestCreateChipRequest:

    @pytest.mark.asyncio
    async def test_create_cash_request_returns_201(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests",
            json={"request_type": "CASH", "amount": 200},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["request_type"] == "CASH"
        assert data["amount"] == 200
        assert data["status"] == "PENDING"
        assert data["player_token"] == bob["player_token"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_credit_request(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests",
            json={"request_type": "CREDIT", "amount": 50},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "CREDIT"

    @pytest.mark.asyncio
    async def test_create_request_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests",
            json={"request_type": "CASH", "amount": 100},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_request_invalid_amount_returns_422(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests",
            json={"request_type": "CASH", "amount": 0},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_request_negative_amount_returns_422(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests",
            json={"request_type": "CASH", "amount": -10},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/pending
# ---------------------------------------------------------------------------

class TestGetPendingRequests:

    @pytest.mark.asyncio
    async def test_pending_returns_only_pending(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req1 = await _create_request(test_client, game["game_id"], bob["player_token"])
        req2 = await _create_request(test_client, game["game_id"], bob["player_token"], amount=50)
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req1['id']}/approve",
            headers={"X-Player-Token": manager_token},
        )
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/pending",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == req2["id"]

    @pytest.mark.asyncio
    async def test_pending_requires_manager(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/pending",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pending_empty_list(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/pending",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/mine
# ---------------------------------------------------------------------------

class TestGetMyRequests:

    @pytest.mark.asyncio
    async def test_mine_returns_own_requests(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")
        await _create_request(test_client, game["game_id"], bob["player_token"])
        await _create_request(test_client, game["game_id"], charlie["player_token"])
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/mine",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["player_token"] == bob["player_token"]

    @pytest.mark.asyncio
    async def test_mine_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.get(f"/api/games/{game['game_id']}/requests/mine")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/approve
# ---------------------------------------------------------------------------

class TestApproveRequest:

    @pytest.mark.asyncio
    async def test_approve_returns_approved_status(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "APPROVED"
        assert data["resolved_by"] == game["player_token"]
        assert data["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_approve_already_approved_returns_400(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": game["player_token"]},
        )
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_requires_manager(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/decline
# ---------------------------------------------------------------------------

class TestDeclineRequest:

    @pytest.mark.asyncio
    async def test_decline_returns_declined_status(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/decline",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DECLINED"
        assert data["resolved_by"] == game["player_token"]

    @pytest.mark.asyncio
    async def test_decline_already_declined_returns_400(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/decline",
            headers={"X-Player-Token": game["player_token"]},
        )
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/decline",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_decline_requires_manager(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/decline",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/edit
# ---------------------------------------------------------------------------

class TestEditAndApproveRequest:

    @pytest.mark.asyncio
    async def test_edit_returns_edited_status(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"], amount=100)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/edit",
            json={"new_amount": 75},
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "EDITED"
        assert data["edited_amount"] == 75
        assert data["amount"] == 100

    @pytest.mark.asyncio
    async def test_edit_invalid_amount_returns_422(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/edit",
            json={"new_amount": 0},
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_edit_requires_manager(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/edit",
            json={"new_amount": 50},
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_already_processed_returns_400(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": game["player_token"]},
        )
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/edit",
            json={"new_amount": 50},
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 400
