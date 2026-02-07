"""Integration tests for chip request history and detail endpoints.

Tests the GET /api/games/{game_id}/requests/history and
GET /api/games/{game_id}/requests/{request_id} endpoints.
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
    resp = await test_client.post(
        f"/api/games/{game_id}/join", json={"player_name": player_name}
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_request(
    test_client, game_id, player_token, request_type="CASH", amount=100
):
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": request_type, "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/{request_id} -- Single request detail
# ---------------------------------------------------------------------------

class TestGetRequestById:

    @pytest.mark.asyncio
    async def test_get_request_by_id_returns_200(self, test_client):
        """Player can get details of a request by ID."""
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/{req['id']}",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == req["id"]
        assert data["player_token"] == bob["player_token"]
        assert data["player_name"] == "Bob"
        assert data["request_type"] == "CASH"
        assert data["amount"] == 100
        assert data["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_get_request_by_id_includes_all_fields(self, test_client):
        """Verify response includes all expected fields."""
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(
            test_client, game["game_id"], bob["player_token"], "CREDIT", 200
        )

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/{req['id']}",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "game_id" in data
        assert "player_token" in data
        assert "requested_by" in data
        assert "player_name" in data
        assert "request_type" in data
        assert "amount" in data
        assert "status" in data
        assert "created_at" in data
        assert data["request_type"] == "CREDIT"
        assert data["amount"] == 200

    @pytest.mark.asyncio
    async def test_get_request_by_id_manager_can_view(self, test_client):
        """Manager can view any request in the game."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/{req['id']}",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == req["id"]
        assert data["player_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_request_by_id_not_found(self, test_client):
        """Returns 404 for non-existent request ID."""
        game = await _create_game(test_client)
        fake_id = "507f1f77bcf86cd799439011"

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/{fake_id}",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_request_by_id_wrong_game(self, test_client):
        """Returns 404 when request belongs to a different game."""
        game1 = await _create_game(test_client, "Alice")
        game2 = await _create_game(test_client, "Charlie")
        bob = await _join_game(test_client, game1["game_id"], "Bob")
        req = await _create_request(test_client, game1["game_id"], bob["player_token"])

        # Try to access request from game1 via game2's URL
        dan = await _join_game(test_client, game2["game_id"], "Dan")
        resp = await test_client.get(
            f"/api/games/{game2['game_id']}/requests/{req['id']}",
            headers={"X-Player-Token": dan["player_token"]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_request_by_id_without_auth(self, test_client):
        """Returns 401 without authentication."""
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        req = await _create_request(test_client, game["game_id"], bob["player_token"])

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/{req['id']}"
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/history -- Full request history
# ---------------------------------------------------------------------------

class TestGetRequestHistory:

    @pytest.mark.asyncio
    async def test_history_manager_sees_all_requests(self, test_client):
        """Manager can see all requests from all players."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")

        await _create_request(test_client, game["game_id"], bob["player_token"])
        await _create_request(test_client, game["game_id"], charlie["player_token"])
        await _create_request(
            test_client, game["game_id"], bob["player_token"], "CREDIT", 50
        )

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_history_player_sees_only_own_requests(self, test_client):
        """Regular player sees only their own requests."""
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")

        await _create_request(test_client, game["game_id"], bob["player_token"])
        await _create_request(test_client, game["game_id"], charlie["player_token"])
        await _create_request(
            test_client, game["game_id"], bob["player_token"], "CREDIT", 50
        )

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        for req in data:
            assert req["player_token"] == bob["player_token"]

    @pytest.mark.asyncio
    async def test_history_includes_all_statuses(self, test_client):
        """History includes PENDING, APPROVED, DECLINED, and EDITED statuses."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")

        # Create 4 requests
        req1 = await _create_request(test_client, game["game_id"], bob["player_token"])
        req2 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=200
        )
        req3 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=300
        )
        req4 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=400
        )

        # Approve req1
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req1['id']}/approve",
            headers={"X-Player-Token": manager_token},
        )
        # Decline req2
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req2['id']}/decline",
            headers={"X-Player-Token": manager_token},
        )
        # Edit req3
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req3['id']}/edit",
            json={"new_amount": 250},
            headers={"X-Player-Token": manager_token},
        )
        # Leave req4 as PENDING

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

        statuses = {req["status"] for req in data}
        assert "APPROVED" in statuses
        assert "DECLINED" in statuses
        assert "EDITED" in statuses
        assert "PENDING" in statuses

    @pytest.mark.asyncio
    async def test_history_sorted_newest_first(self, test_client):
        """History is sorted by created_at descending (newest first)."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")

        req1 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=100
        )
        req2 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=200
        )
        req3 = await _create_request(
            test_client, game["game_id"], bob["player_token"], amount=300
        )

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

        # Newest first means req3, req2, req1
        assert data[0]["amount"] == 300
        assert data[1]["amount"] == 200
        assert data[2]["amount"] == 100

    @pytest.mark.asyncio
    async def test_history_includes_player_name(self, test_client):
        """History includes player_name field."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")

        await _create_request(test_client, game["game_id"], bob["player_token"])

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["player_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_history_includes_timestamps(self, test_client):
        """History includes created_at and resolved_at timestamps."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        bob = await _join_game(test_client, game["game_id"], "Bob")

        req = await _create_request(test_client, game["game_id"], bob["player_token"])

        # Approve to get resolved_at
        await test_client.post(
            f"/api/games/{game['game_id']}/requests/{req['id']}/approve",
            headers={"X-Player-Token": manager_token},
        )

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["created_at"] is not None
        assert data[0]["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_history_without_auth(self, test_client):
        """Returns 401 without authentication."""
        game = await _create_game(test_client)

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_empty_list(self, test_client):
        """Returns empty list when no requests exist."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]

        resp = await test_client.get(
            f"/api/games/{game['game_id']}/requests/history",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_history_game_not_found(self, test_client):
        """Returns 404 for non-existent game."""
        game = await _create_game(test_client)
        fake_game_id = "507f1f77bcf86cd799439011"

        resp = await test_client.get(
            f"/api/games/{fake_game_id}/requests/history",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 404
