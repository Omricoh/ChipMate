"""Integration tests for auth route handlers.

These tests use HTTPX AsyncClient with the FastAPI test app and
mongomock-motor so no real MongoDB instance is needed.
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
from app.auth import dependencies as auth_deps_module
from app.routes import auth as auth_route_module
from app.models.player import Player


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock database and patch all get_database refs."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]

    getter = lambda: db
    orig_db = db_module.get_database
    orig_auth_deps = auth_deps_module.get_database
    orig_auth_route = auth_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    auth_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth_deps
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
async def player_in_game(mock_db) -> Player:
    """Insert a test player into the mock database and return it."""
    player = Player(
        game_id="665f1a2b3c4d5e6f7a8b9c0d",
        player_token=generate_player_token(),
        display_name="TestPlayer",
        is_manager=False,
    )
    await mock_db.players.insert_one(player.to_mongo_dict())
    return player


@pytest_asyncio.fixture
async def manager_in_game(mock_db) -> Player:
    """Insert a test manager into the mock database and return it."""
    player = Player(
        game_id="665f1a2b3c4d5e6f7a8b9c0d",
        player_token=generate_player_token(),
        display_name="TestManager",
        is_manager=True,
    )
    await mock_db.players.insert_one(player.to_mongo_dict())
    return player


# ---------------------------------------------------------------------------
# POST /api/auth/admin/login
# ---------------------------------------------------------------------------

class TestAdminLogin:
    """Tests for the admin login endpoint."""

    @pytest.mark.asyncio
    async def test_valid_login(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/auth/admin/login",
            json={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    @pytest.mark.asyncio
    async def test_wrong_password(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/auth/admin/login",
            json={
                "username": settings.ADMIN_USERNAME,
                "password": "wrong-password",
            },
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_username(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/auth/admin/login",
            json={
                "username": "not-admin",
                "password": settings.ADMIN_PASSWORD,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_fields(self, test_client: AsyncClient):
        resp = await test_client.post("/api/auth/admin/login", json={})
        assert resp.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_empty_username(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/auth/admin/login",
            json={"username": "", "password": "something"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returned_token_is_decodable(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/auth/admin/login",
            json={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
        )
        token = resp.json()["access_token"]
        from app.auth.jwt import decode_token

        payload = decode_token(token)
        assert payload["sub"] == settings.ADMIN_USERNAME
        assert payload["role"] == "admin"


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

class TestGetMe:
    """Tests for the /me endpoint."""

    @pytest.mark.asyncio
    async def test_admin_me(self, test_client: AsyncClient, admin_token: str):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        assert data["username"] == settings.ADMIN_USERNAME

    @pytest.mark.asyncio
    async def test_player_me(self, test_client: AsyncClient, player_in_game: Player):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"X-Player-Token": player_in_game.player_token},
            params={"game_id": player_in_game.game_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "player"
        assert data["name"] == "TestPlayer"
        assert data["game_id"] == player_in_game.game_id
        assert data["player_token"] == player_in_game.player_token

    @pytest.mark.asyncio
    async def test_manager_me(self, test_client: AsyncClient, manager_in_game: Player):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"X-Player-Token": manager_in_game.player_token},
            params={"game_id": manager_in_game.game_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "manager"
        assert data["name"] == "TestManager"

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, test_client: AsyncClient):
        resp = await test_client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_401(
        self, test_client: AsyncClient, expired_admin_token: str
    ):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_admin_token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, test_client: AsyncClient):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_player_token_format_returns_401(
        self, test_client: AsyncClient
    ):
        resp = await test_client.get(
            "/api/auth/me",
            headers={"X-Player-Token": "not-a-uuid"},
            params={"game_id": "somegame"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_player_token_not_in_db_returns_404(
        self, test_client: AsyncClient
    ):
        from app.auth.player_token import generate_player_token

        token = generate_player_token()
        resp = await test_client.get(
            "/api/auth/me",
            headers={"X-Player-Token": token},
            params={"game_id": "665f1a2b3c4d5e6f7a8b9c0d"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_player_me_without_game_id_uses_token_only(
        self, test_client: AsyncClient, player_in_game: Player
    ):
        """When no game_id query param, falls back to get_by_token_only."""
        resp = await test_client.get(
            "/api/auth/me",
            headers={"X-Player-Token": player_in_game.player_token},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "TestPlayer"


# ---------------------------------------------------------------------------
# Auth dependency tests via protected endpoint simulation
# ---------------------------------------------------------------------------

class TestNonAdminJwtForbidden:
    """Ensure a valid JWT without admin role is rejected by admin-only logic."""

    @pytest.mark.asyncio
    async def test_non_admin_jwt_on_me_returns_non_admin_info(
        self, test_client: AsyncClient, non_admin_token: str
    ):
        """GET /me with a non-admin JWT should still return whatever role is in the token.
        The /me endpoint doesn't enforce admin-only; it just reports.
        For a non-admin JWT, it will not match role=='admin' and fall through
        to the player path, which will fail with 401 if no X-Player-Token."""
        resp = await test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )
        # The JWT is valid but role != admin, so the admin branch is skipped.
        # No X-Player-Token header, so we get 401.
        assert resp.status_code == 401
