"""Integration tests for notification route handlers.

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_game(test_client, manager_name="Alice"):
    resp = await test_client.post("/api/games", json={"manager_name": manager_name})
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client, game_id, player_name):
    resp = await test_client.post(f"/api/games/{game_id}/join", json={"player_name": player_name})
    assert resp.status_code == 201
    return resp.json()


async def _create_and_approve_request(test_client, game_id, player_token, manager_token, amount=100):
    """Create a chip request and approve it, which generates a notification for the player."""
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": "CASH", "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]
    resp = await test_client.post(
        f"/api/games/{game_id}/requests/{request_id}/approve",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return request_id


async def _create_and_decline_request(test_client, game_id, player_token, manager_token, amount=50):
    """Create a chip request and decline it, which generates a notification for the player."""
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": "CASH", "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]
    resp = await test_client.post(
        f"/api/games/{game_id}/requests/{request_id}/decline",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return request_id


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/notifications
# ---------------------------------------------------------------------------

class TestGetNotifications:

    @pytest.mark.asyncio
    async def test_get_notifications_returns_unread(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] >= 1
        assert len(data["notifications"]) >= 1
        # Verify notification structure
        notif = data["notifications"][0]
        assert "id" in notif
        assert notif["game_id"] == game["game_id"]
        assert notif["player_token"] == bob["player_token"]
        assert notif["is_read"] is False
        assert "message" in notif
        assert "created_at" in notif

    @pytest.mark.asyncio
    async def test_get_notifications_empty_when_no_activity(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] == 0
        assert data["notifications"] == []

    @pytest.mark.asyncio
    async def test_get_notifications_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.get(f"/api/games/{game['game_id']}/notifications")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_notifications_multiple(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        # Create two notifications via approve and decline
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"], amount=100
        )
        await _create_and_decline_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"], amount=50
        )
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] >= 2
        assert len(data["notifications"]) >= 2

    @pytest.mark.asyncio
    async def test_notifications_are_scoped_to_player(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")
        # Only Bob gets a notification
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        # Charlie should have no notifications
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": charlie["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] == 0
        assert data["notifications"] == []


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/notifications/{notification_id}/read
# ---------------------------------------------------------------------------

class TestMarkNotificationRead:

    @pytest.mark.asyncio
    async def test_mark_read_returns_success(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        # Get the notification ID
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        notif_id = resp.json()["notifications"][0]["id"]
        # Mark it as read
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/{notif_id}/read",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_mark_read_reduces_unread_count(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        # Get notification
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        initial_count = resp.json()["unread_count"]
        notif_id = resp.json()["notifications"][0]["id"]
        # Mark as read
        await test_client.post(
            f"/api/games/{game['game_id']}/notifications/{notif_id}/read",
            headers={"X-Player-Token": bob["player_token"]},
        )
        # Check unread count decreased
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.json()["unread_count"] == initial_count - 1

    @pytest.mark.asyncio
    async def test_mark_read_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/fakeid/read"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_mark_read_wrong_player_returns_403(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        # Get Bob's notification
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        notif_id = resp.json()["notifications"][0]["id"]
        # Charlie tries to mark Bob's notification as read
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/{notif_id}/read",
            headers={"X-Player-Token": charlie["player_token"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/notifications/read-all
# ---------------------------------------------------------------------------

class TestMarkAllRead:

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_count(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"], amount=100
        )
        await _create_and_decline_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"], amount=50
        )
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/read-all",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["marked_count"] >= 2

    @pytest.mark.asyncio
    async def test_mark_all_read_then_zero_unread(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        # Mark all read
        await test_client.post(
            f"/api/games/{game['game_id']}/notifications/read-all",
            headers={"X-Player-Token": bob["player_token"]},
        )
        # Check unread count is 0
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_when_none_returns_zero(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/read-all",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["marked_count"] == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/notifications/read-all"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_mark_all_read_only_affects_own_notifications(self, test_client):
        game = await _create_game(test_client)
        bob = await _join_game(test_client, game["game_id"], "Bob")
        charlie = await _join_game(test_client, game["game_id"], "Charlie")
        # Both get a notification
        await _create_and_approve_request(
            test_client, game["game_id"], bob["player_token"], game["player_token"]
        )
        await _create_and_approve_request(
            test_client, game["game_id"], charlie["player_token"], game["player_token"]
        )
        # Bob marks all read
        await test_client.post(
            f"/api/games/{game['game_id']}/notifications/read-all",
            headers={"X-Player-Token": bob["player_token"]},
        )
        # Charlie still has unread
        resp = await test_client.get(
            f"/api/games/{game['game_id']}/notifications",
            headers={"X-Player-Token": charlie["player_token"]},
        )
        assert resp.json()["unread_count"] >= 1
