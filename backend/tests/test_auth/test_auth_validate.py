"""Integration tests for the /api/auth/validate endpoint.

Tests validate endpoint for session restoration functionality,
supporting both admin JWT and player token authentication.
"""

import os
from datetime import timedelta

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
from app.routes import auth as auth_route_module
from app.models.game import Game
from app.models.player import Player
from app.models.common import GameStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock database and patch get_database refs."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]

    getter = lambda: db
    orig_db = db_module.get_database
    orig_auth_route = auth_route_module.get_database

    db_module.get_database = getter
    auth_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_route_module.get_database = orig_auth_route
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


@pytest.fixture
def expired_admin_token() -> str:
    """An expired admin JWT."""
    return create_access_token(
        data={"sub": settings.ADMIN_USERNAME, "role": "admin"},
        expires_delta=timedelta(seconds=-1),
    )


@pytest.fixture
def non_admin_token() -> str:
    """A valid JWT without admin role."""
    return create_access_token(data={"sub": "regular_user", "role": "player"})


@pytest_asyncio.fixture
async def game_in_db(mock_db) -> Game:
    """Insert a test game into the mock database and return it."""
    game_dal = GameDAL(mock_db)
    game = Game(
        code="TESTGM",
        manager_player_token=generate_player_token(),
    )
    return await game_dal.create(game)


@pytest_asyncio.fixture
async def player_in_game(mock_db, game_in_db: Game) -> Player:
    """Insert a test player into the mock database and return it."""
    player_dal = PlayerDAL(mock_db)
    player = Player(
        game_id=game_in_db.id,
        player_token=generate_player_token(),
        display_name="TestPlayer",
        is_manager=False,
    )
    return await player_dal.create(player)


@pytest_asyncio.fixture
async def manager_in_game(mock_db, game_in_db: Game) -> Player:
    """Insert a test manager into the mock database and return it."""
    player_dal = PlayerDAL(mock_db)
    player = Player(
        game_id=game_in_db.id,
        player_token=generate_player_token(),
        display_name="TestManager",
        is_manager=True,
    )
    return await player_dal.create(player)


# ---------------------------------------------------------------------------
# GET /api/auth/validate - Admin JWT tests
# ---------------------------------------------------------------------------


class TestValidateAdminJwt:
    """Tests for validate endpoint with admin JWT."""

    @pytest.mark.asyncio
    async def test_valid_admin_token(self, test_client: AsyncClient, admin_token: str):
        """Valid admin JWT returns valid=true with admin user context."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["user"]["user_id"] == "admin"
        assert data["user"]["role"] == "ADMIN"
        assert data["user"]["username"] == settings.ADMIN_USERNAME

    @pytest.mark.asyncio
    async def test_expired_admin_token(
        self, test_client: AsyncClient, expired_admin_token: str
    ):
        """Expired admin JWT returns valid=false with error."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {expired_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Token has expired"

    @pytest.mark.asyncio
    async def test_invalid_admin_token(self, test_client: AsyncClient):
        """Invalid/malformed JWT returns valid=false with error."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Invalid token"

    @pytest.mark.asyncio
    async def test_non_admin_jwt_returns_invalid(
        self, test_client: AsyncClient, non_admin_token: str
    ):
        """JWT with non-admin role returns valid=false."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Invalid token role"


# ---------------------------------------------------------------------------
# GET /api/auth/validate - Player token tests
# ---------------------------------------------------------------------------


class TestValidatePlayerToken:
    """Tests for validate endpoint with player token."""

    @pytest.mark.asyncio
    async def test_valid_player_token(
        self, test_client: AsyncClient, player_in_game: Player, game_in_db: Game
    ):
        """Valid player token returns valid=true with player user context."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player_in_game.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        user = data["user"]
        assert user["user_id"] == player_in_game.id
        assert user["role"] == "PLAYER"
        assert user["player_id"] == player_in_game.player_token
        assert user["game_id"] == game_in_db.id
        assert user["game_code"] == game_in_db.code
        assert user["is_manager"] is False

    @pytest.mark.asyncio
    async def test_valid_manager_token(
        self, test_client: AsyncClient, manager_in_game: Player, game_in_db: Game
    ):
        """Valid manager token returns valid=true with MANAGER role."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": manager_in_game.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        user = data["user"]
        assert user["user_id"] == manager_in_game.id
        assert user["role"] == "MANAGER"
        assert user["player_id"] == manager_in_game.player_token
        assert user["game_id"] == game_in_db.id
        assert user["game_code"] == game_in_db.code
        assert user["is_manager"] is True

    @pytest.mark.asyncio
    async def test_invalid_player_token_format(self, test_client: AsyncClient):
        """Invalid player token format returns valid=false."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": "not-a-uuid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Invalid player token format"

    @pytest.mark.asyncio
    async def test_player_token_not_found(self, test_client: AsyncClient, mock_db):
        """Player token not in database returns valid=false."""
        token = generate_player_token()
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Player not found"

    @pytest.mark.asyncio
    async def test_player_with_deleted_game(self, test_client: AsyncClient, mock_db):
        """Player whose game was deleted returns valid=false."""
        # Create player with non-existent game_id
        player_dal = PlayerDAL(mock_db)
        player = Player(
            game_id="000000000000000000000000",  # Non-existent game
            player_token=generate_player_token(),
            display_name="OrphanPlayer",
            is_manager=False,
        )
        await player_dal.create(player)

        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Game not found"

    @pytest.mark.asyncio
    async def test_player_with_closed_game(self, test_client: AsyncClient, mock_db):
        """Player whose game is closed returns valid=false."""
        game_dal = GameDAL(mock_db)
        player_dal = PlayerDAL(mock_db)

        # Create a closed game
        game = Game(
            code="CLOSED",
            manager_player_token=generate_player_token(),
            status=GameStatus.CLOSED,
        )
        game = await game_dal.create(game)

        # Create player in the closed game
        player = Player(
            game_id=game.id,
            player_token=generate_player_token(),
            display_name="ClosedGamePlayer",
            is_manager=False,
        )
        await player_dal.create(player)

        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Game has ended"

    @pytest.mark.asyncio
    async def test_player_with_settling_game(
        self, test_client: AsyncClient, mock_db
    ):
        """Player whose game is settling can still validate (rejoin)."""
        game_dal = GameDAL(mock_db)
        player_dal = PlayerDAL(mock_db)

        # Create a settling game
        game = Game(
            code="SETTLE",
            manager_player_token=generate_player_token(),
            status=GameStatus.SETTLING,
        )
        game = await game_dal.create(game)

        # Create player in the settling game
        player = Player(
            game_id=game.id,
            player_token=generate_player_token(),
            display_name="SettlingGamePlayer",
            is_manager=False,
        )
        await player_dal.create(player)

        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["user"]["role"] == "PLAYER"
        assert data["user"]["game_code"] == "SETTLE"

    @pytest.mark.asyncio
    async def test_inactive_player(self, test_client: AsyncClient, mock_db):
        """Inactive player returns valid=false."""
        game_dal = GameDAL(mock_db)
        player_dal = PlayerDAL(mock_db)

        # Create a game
        game = Game(
            code="ACTIVE",
            manager_player_token=generate_player_token(),
        )
        game = await game_dal.create(game)

        # Create an inactive player
        player = Player(
            game_id=game.id,
            player_token=generate_player_token(),
            display_name="InactivePlayer",
            is_manager=False,
            is_active=False,
        )
        await player_dal.create(player)

        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "Player is inactive"

    @pytest.mark.asyncio
    async def test_validate_returns_display_name(
        self, test_client: AsyncClient, player_in_game: Player, game_in_db: Game
    ):
        """Valid player token returns display_name in response."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"X-Player-Token": player_in_game.player_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["user"]["display_name"] == player_in_game.display_name


# ---------------------------------------------------------------------------
# GET /api/auth/validate - No auth tests
# ---------------------------------------------------------------------------


class TestValidateNoAuth:
    """Tests for validate endpoint with no authentication."""

    @pytest.mark.asyncio
    async def test_no_auth_header(self, test_client: AsyncClient):
        """No authentication header returns valid=false."""
        resp = await test_client.get("/api/auth/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "No authentication provided"

    @pytest.mark.asyncio
    async def test_empty_bearer_token(self, test_client: AsyncClient):
        """Empty bearer token (just 'Bearer ') returns valid=false."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        # Empty token will fail JWT decode
        assert "Invalid token" in data["error"]

    @pytest.mark.asyncio
    async def test_non_bearer_authorization(self, test_client: AsyncClient):
        """Authorization header without Bearer prefix returns valid=false."""
        resp = await test_client.get(
            "/api/auth/validate",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] == "No authentication provided"
