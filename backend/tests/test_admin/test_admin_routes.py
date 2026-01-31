"""Integration tests for admin route handlers.

Tests the full HTTP stack using HTTPX AsyncClient with the FastAPI app
and mongomock-motor (no real MongoDB required).
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.auth.jwt import create_access_token
from app.dal import database as db_module
from app.auth import dependencies as auth_deps_module
from app.routes import games as games_route_module
from app.routes import chip_requests as chip_requests_route_module
from app.routes import notifications as notifications_route_module
from app.routes import admin as admin_route_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_token() -> str:
    """Create a valid admin JWT for testing."""
    return create_access_token(data={"sub": "admin", "role": "admin"})


def _admin_headers() -> dict[str, str]:
    """Return Authorization header with a valid admin JWT."""
    return {"Authorization": f"Bearer {_admin_token()}"}


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
    orig_admin = admin_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter
    chip_requests_route_module.get_database = getter
    notifications_route_module.get_database = getter
    admin_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth
    games_route_module.get_database = orig_games
    chip_requests_route_module.get_database = orig_requests
    notifications_route_module.get_database = orig_notifications
    admin_route_module.get_database = orig_admin
    client.close()


@pytest_asyncio.fixture
async def test_client(mock_db):
    """Async HTTP client wired to the FastAPI app with mocked db."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_game(test_client, manager_name="Alice"):
    """Helper to create a game via the API."""
    resp = await test_client.post("/api/games", json={"manager_name": manager_name})
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client, game_id, player_name):
    """Helper to join a game via the API."""
    resp = await test_client.post(
        f"/api/games/{game_id}/join", json={"player_name": player_name}
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/admin/games -- List all games
# ---------------------------------------------------------------------------

class TestListGames:

    @pytest.mark.asyncio
    async def test_list_games_empty(self, test_client):
        """List games returns empty list when no games exist."""
        resp = await test_client.get("/api/admin/games", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["games"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_games_returns_games(self, test_client):
        """List games returns created games."""
        await _create_game(test_client, "Alice")
        await _create_game(test_client, "Bob")

        resp = await test_client.get("/api/admin/games", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["games"]) == 2
        # Each game should have expected fields
        game = data["games"][0]
        assert "game_id" in game
        assert "game_code" in game
        assert "status" in game
        assert "player_count" in game
        assert "bank" in game
        assert "created_at" in game

    @pytest.mark.asyncio
    async def test_list_games_filter_by_status(self, test_client):
        """List games with status filter returns only matching games."""
        game1 = await _create_game(test_client, "Alice")
        await _create_game(test_client, "Bob")

        # Force close game1
        await test_client.post(
            f"/api/admin/games/{game1['game_id']}/force-close",
            headers=_admin_headers(),
        )

        # Filter for OPEN games only
        resp = await test_client.get(
            "/api/admin/games", params={"status": "OPEN"}, headers=_admin_headers()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["games"][0]["status"] == "OPEN"

        # Filter for CLOSED games only
        resp = await test_client.get(
            "/api/admin/games", params={"status": "CLOSED"}, headers=_admin_headers()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["games"][0]["status"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_list_games_requires_admin_jwt(self, test_client):
        """List games without auth returns 401."""
        resp = await test_client.get("/api/admin/games")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_games_pagination(self, test_client):
        """List games respects limit and offset."""
        await _create_game(test_client, "Alice")
        await _create_game(test_client, "Bob")
        await _create_game(test_client, "Charlie")

        resp = await test_client.get(
            "/api/admin/games",
            params={"limit": 2, "offset": 0},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.json()["games"]) == 2

        resp = await test_client.get(
            "/api/admin/games",
            params={"limit": 2, "offset": 2},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.json()["games"]) == 1


# ---------------------------------------------------------------------------
# GET /api/admin/games/{game_id} -- Get detailed game info
# ---------------------------------------------------------------------------

class TestGetGameDetail:

    @pytest.mark.asyncio
    async def test_game_detail_returns_full_info(self, test_client):
        """Get game detail returns game, players, and request stats."""
        game = await _create_game(test_client, "Alice")
        await _join_game(test_client, game["game_id"], "Bob")

        resp = await test_client.get(
            f"/api/admin/games/{game['game_id']}", headers=_admin_headers()
        )
        assert resp.status_code == 200
        data = resp.json()

        # Game info
        assert data["game"]["game_id"] == game["game_id"]
        assert data["game"]["status"] == "OPEN"
        assert "bank" in data["game"]
        assert "created_at" in data["game"]
        assert "expires_at" in data["game"]

        # Players
        assert len(data["players"]) == 2
        display_names = {p["display_name"] for p in data["players"]}
        assert "Alice" in display_names
        assert "Bob" in display_names

        # Request stats
        assert data["request_stats"]["total"] == 0
        assert data["request_stats"]["pending"] == 0
        assert data["request_stats"]["approved"] == 0

    @pytest.mark.asyncio
    async def test_game_detail_nonexistent_returns_404(self, test_client):
        """Get game detail for nonexistent game returns 404."""
        resp = await test_client.get(
            "/api/admin/games/000000000000000000000000",
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_game_detail_requires_admin_jwt(self, test_client):
        """Get game detail without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        resp = await test_client.get(f"/api/admin/games/{game['game_id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/games/{game_id}/force-close -- Force close a game
# ---------------------------------------------------------------------------

class TestForceCloseGame:

    @pytest.mark.asyncio
    async def test_force_close_changes_status(self, test_client):
        """Force close sets game status to CLOSED."""
        game = await _create_game(test_client, "Alice")

        resp = await test_client.post(
            f"/api/admin/games/{game['game_id']}/force-close",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CLOSED"
        assert data["game_id"] == game["game_id"]
        assert data["closed_at"] is not None

        # Verify via detail endpoint
        detail_resp = await test_client.get(
            f"/api/admin/games/{game['game_id']}", headers=_admin_headers()
        )
        assert detail_resp.json()["game"]["status"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_force_close_already_closed_succeeds(self, test_client):
        """Force closing an already closed game still succeeds."""
        game = await _create_game(test_client, "Alice")

        # Close first time
        resp1 = await test_client.post(
            f"/api/admin/games/{game['game_id']}/force-close",
            headers=_admin_headers(),
        )
        assert resp1.status_code == 200

        # Close again -- should still succeed
        resp2 = await test_client.post(
            f"/api/admin/games/{game['game_id']}/force-close",
            headers=_admin_headers(),
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_force_close_nonexistent_returns_404(self, test_client):
        """Force close nonexistent game returns 404."""
        resp = await test_client.post(
            "/api/admin/games/000000000000000000000000/force-close",
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_force_close_requires_admin_jwt(self, test_client):
        """Force close without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        resp = await test_client.post(
            f"/api/admin/games/{game['game_id']}/force-close"
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/stats -- Dashboard statistics
# ---------------------------------------------------------------------------

class TestDashboardStats:

    @pytest.mark.asyncio
    async def test_stats_returns_correct_counts(self, test_client):
        """Dashboard stats returns correct game and player counts."""
        # Create 3 games
        game1 = await _create_game(test_client, "Alice")
        game2 = await _create_game(test_client, "Bob")
        game3 = await _create_game(test_client, "Charlie")

        # Add players to game1
        await _join_game(test_client, game1["game_id"], "Player1")
        await _join_game(test_client, game1["game_id"], "Player2")

        # Force close game3
        await test_client.post(
            f"/api/admin/games/{game3['game_id']}/force-close",
            headers=_admin_headers(),
        )

        resp = await test_client.get("/api/admin/stats", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_games"] == 3
        assert data["active_games"] == 2  # game1 and game2 are OPEN
        assert data["settling_games"] == 0
        assert data["closed_games"] == 1  # game3 is CLOSED
        # 3 managers + 2 joined players = 5 total players
        assert data["total_players"] == 5

    @pytest.mark.asyncio
    async def test_stats_empty_database(self, test_client):
        """Dashboard stats on empty database returns all zeros."""
        resp = await test_client.get("/api/admin/stats", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_games"] == 0
        assert data["active_games"] == 0
        assert data["settling_games"] == 0
        assert data["closed_games"] == 0
        assert data["total_players"] == 0

    @pytest.mark.asyncio
    async def test_stats_requires_admin_jwt(self, test_client):
        """Dashboard stats without auth returns 401."""
        resp = await test_client.get("/api/admin/stats")
        assert resp.status_code == 401
