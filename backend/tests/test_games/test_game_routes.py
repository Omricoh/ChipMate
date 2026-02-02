"""Integration tests for game route handlers.

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
from app.auth.player_token import generate_player_token
from app.config import settings
from app.dal import database as db_module
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus
from app.models.player import Player
from app.services.game_service import _CODE_CHARS
from app.auth import dependencies as auth_deps_module
from app.routes import games as games_route_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock MongoDB database and patch all get_database refs."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]

    # Patch everywhere get_database is imported
    getter = lambda: db
    orig_db = db_module.get_database
    orig_auth = auth_deps_module.get_database
    orig_routes = games_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth
    games_route_module.get_database = orig_routes
    client.close()


@pytest_asyncio.fixture
async def test_client(mock_db):
    """Async HTTP client wired to the FastAPI app with mocked db."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_token() -> str:
    """A valid admin JWT for test use."""
    return create_access_token(data={"sub": settings.ADMIN_USERNAME, "role": "admin"})


async def _create_game(test_client: AsyncClient, manager_name: str = "Alice") -> dict:
    """Helper to create a game and return the response dict."""
    resp = await test_client.post(
        "/api/games",
        json={"manager_name": manager_name},
    )
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client: AsyncClient, game_id: str, player_name: str) -> dict:
    """Helper to join a game and return the response dict."""
    resp = await test_client.post(
        f"/api/games/{game_id}/join",
        json={"player_name": player_name},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/games -- Create game
# ---------------------------------------------------------------------------

class TestCreateGameRoute:
    """Tests for POST /api/games."""

    @pytest.mark.asyncio
    async def test_create_game_returns_201(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/games",
            json={"manager_name": "Alice"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "game_id" in data
        assert "game_code" in data
        assert "player_token" in data
        assert data["manager_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_game_code_format(self, test_client: AsyncClient):
        data = await _create_game(test_client)
        code = data["game_code"]
        assert len(code) == 6
        for ch in code:
            assert ch in _CODE_CHARS, f"Unexpected char '{ch}' in code"

    @pytest.mark.asyncio
    async def test_game_code_excludes_ambiguous(self, test_client: AsyncClient):
        """Run several creations and verify no I, O, 0, or 1 appear."""
        ambiguous = set("IO01")
        for _ in range(10):
            data = await _create_game(test_client)
            code_chars = set(data["game_code"])
            assert ambiguous.isdisjoint(code_chars), (
                f"Code '{data['game_code']}' has ambiguous chars"
            )

    @pytest.mark.asyncio
    async def test_create_game_name_too_short(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/games",
            json={"manager_name": "A"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_game_name_too_long(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/games",
            json={"manager_name": "A" * 31},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_game_missing_name(self, test_client: AsyncClient):
        resp = await test_client.post("/api/games", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/games/code/{game_code} -- Game code lookup
# ---------------------------------------------------------------------------

class TestGameCodeLookup:
    """Tests for GET /api/games/code/{game_code}."""

    @pytest.mark.asyncio
    async def test_lookup_existing_game(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        code = data["game_code"]

        resp = await test_client.get(f"/api/games/code/{code}")
        assert resp.status_code == 200
        lookup = resp.json()
        assert lookup["game_id"] == data["game_id"]
        assert lookup["game_code"] == code
        assert lookup["status"] == "OPEN"
        assert lookup["can_join"] is True
        assert lookup["manager_name"] == "Alice"
        assert lookup["player_count"] >= 1  # at least manager

    @pytest.mark.asyncio
    async def test_lookup_nonexistent_code_returns_404(self, test_client: AsyncClient):
        resp = await test_client.get("/api/games/code/ZZZZZZ")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_lookup_settling_game_cannot_join(
        self, test_client: AsyncClient, mock_db
    ):
        data = await _create_game(test_client, "Alice")
        game_dal = GameDAL(mock_db)
        await game_dal.update_status(data["game_id"], GameStatus.SETTLING)

        resp = await test_client.get(f"/api/games/code/{data['game_code']}")
        assert resp.status_code == 200
        assert resp.json()["can_join"] is False


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/join -- Join game
# ---------------------------------------------------------------------------

class TestJoinGameRoute:
    """Tests for POST /api/games/{game_id}/join."""

    @pytest.mark.asyncio
    async def test_join_open_game(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")

        resp = await test_client.post(
            f"/api/games/{data['game_id']}/join",
            json={"player_name": "Bob"},
        )
        assert resp.status_code == 201
        join_data = resp.json()
        assert "player_id" in join_data
        assert "player_token" in join_data
        assert "game" in join_data
        assert join_data["game"]["game_id"] == data["game_id"]
        assert join_data["game"]["game_code"] == data["game_code"]
        assert join_data["game"]["manager_name"] == "Alice"
        assert join_data["game"]["status"] == "OPEN"

    @pytest.mark.asyncio
    async def test_join_settling_game_returns_400(
        self, test_client: AsyncClient, mock_db
    ):
        data = await _create_game(test_client, "Alice")
        game_dal = GameDAL(mock_db)
        await game_dal.update_status(data["game_id"], GameStatus.SETTLING)

        resp = await test_client.post(
            f"/api/games/{data['game_id']}/join",
            json={"player_name": "Bob"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_join_closed_game_returns_400(
        self, test_client: AsyncClient, mock_db
    ):
        from datetime import datetime, timezone

        data = await _create_game(test_client, "Alice")
        game_dal = GameDAL(mock_db)
        await game_dal.update_status(
            data["game_id"],
            GameStatus.CLOSED,
            closed_at=datetime.now(timezone.utc),
        )

        resp = await test_client.post(
            f"/api/games/{data['game_id']}/join",
            json={"player_name": "Bob"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_join_nonexistent_game_returns_404(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/games/000000000000000000000000/join",
            json={"player_name": "Bob"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_join_name_too_short(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.post(
            f"/api/games/{data['game_id']}/join",
            json={"player_name": "B"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_join_name_too_long(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.post(
            f"/api/games/{data['game_id']}/join",
            json={"player_name": "B" * 31},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/games/{game_id} -- Get game details (auth required)
# ---------------------------------------------------------------------------

class TestGetGameRoute:
    """Tests for GET /api/games/{game_id}."""

    @pytest.mark.asyncio
    async def test_get_game_with_player_token(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(
            f"/api/games/{data['game_id']}",
            headers={"X-Player-Token": data["player_token"]},
        )
        assert resp.status_code == 200
        game_data = resp.json()
        assert game_data["game_id"] == data["game_id"]
        assert game_data["status"] == "OPEN"

    @pytest.mark.asyncio
    async def test_get_game_with_admin_token(
        self, test_client: AsyncClient, admin_token: str
    ):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(
            f"/api/games/{data['game_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_game_without_auth_returns_401(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(f"/api/games/{data['game_id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/players -- List players (auth required)
# ---------------------------------------------------------------------------

class TestListPlayersRoute:
    """Tests for GET /api/games/{game_id}/players."""

    @pytest.mark.asyncio
    async def test_list_players_returns_all(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        await _join_game(test_client, data["game_id"], "Bob")
        await _join_game(test_client, data["game_id"], "Charlie")

        resp = await test_client.get(
            f"/api/games/{data['game_id']}/players",
            headers={"X-Player-Token": data["player_token"]},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["total_count"] == 3
        names = {p["display_name"] for p in result["players"]}
        assert names == {"Alice", "Bob", "Charlie"}

    @pytest.mark.asyncio
    async def test_list_players_identifies_manager(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(
            f"/api/games/{data['game_id']}/players",
            headers={"X-Player-Token": data["player_token"]},
        )
        assert resp.status_code == 200
        players = resp.json()["players"]
        manager_count = sum(1 for p in players if p["is_manager"])
        assert manager_count == 1

    @pytest.mark.asyncio
    async def test_list_players_without_auth_returns_401(
        self, test_client: AsyncClient
    ):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(f"/api/games/{data['game_id']}/players")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/status -- Game status with bankroll
# ---------------------------------------------------------------------------

class TestGameStatusRoute:
    """Tests for GET /api/games/{game_id}/status."""

    @pytest.mark.asyncio
    async def test_status_returns_expected_structure(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(
            f"/api/games/{data['game_id']}/status",
            headers={"X-Player-Token": data["player_token"]},
        )
        assert resp.status_code == 200
        status_data = resp.json()
        assert "game" in status_data
        assert "players" in status_data
        assert "bank" in status_data
        assert status_data["game"]["status"] == "OPEN"

    @pytest.mark.asyncio
    async def test_status_player_count(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        await _join_game(test_client, data["game_id"], "Bob")

        resp = await test_client.get(
            f"/api/games/{data['game_id']}/status",
            headers={"X-Player-Token": data["player_token"]},
        )
        assert resp.status_code == 200
        assert resp.json()["players"]["total"] == 2

    @pytest.mark.asyncio
    async def test_status_bank_defaults(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(
            f"/api/games/{data['game_id']}/status",
            headers={"X-Player-Token": data["player_token"]},
        )
        bank = resp.json()["bank"]
        assert bank["total_cash_in"] == 0
        assert bank["total_credit_in"] == 0
        assert bank["total_chips_in_play"] == 0

    @pytest.mark.asyncio
    async def test_status_without_auth_returns_401(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(f"/api/games/{data['game_id']}/status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/games/{game_code}/qr -- QR code
# ---------------------------------------------------------------------------

try:
    import qrcode  # noqa: F401
    _has_qrcode = True
except ImportError:
    _has_qrcode = False


@pytest.mark.skipif(not _has_qrcode, reason="qrcode library not installed")
class TestQRCodeRoute:
    """Tests for GET /api/games/{game_code}/qr."""

    @pytest.mark.asyncio
    async def test_qr_returns_png(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        code = data["game_code"]

        resp = await test_client.get(f"/api/games/{code}/qr")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # PNG files start with the magic bytes 0x89504E47
        assert resp.content[:4] == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_qr_nonexistent_code_returns_404(self, test_client: AsyncClient):
        resp = await test_client.get("/api/games/ZZZZZZ/qr")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_qr_response_is_non_empty(self, test_client: AsyncClient):
        data = await _create_game(test_client, "Alice")
        resp = await test_client.get(f"/api/games/{data['game_code']}/qr")
        assert len(resp.content) > 100  # a valid PNG is at least a few hundred bytes
