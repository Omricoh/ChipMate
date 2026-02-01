"""Integration tests for debt resolution and game close route handlers.

Tests the full HTTP stack using HTTPX AsyncClient with the FastAPI app
and mongomock-motor (no real MongoDB required).

Covers:
    POST /api/games/{game_id}/players/{player_token}/settle-debt
    POST /api/games/{game_id}/close
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
from app.routes import checkout as checkout_route_module


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
    orig_settlement = settlement_route_module.get_database
    orig_checkout = checkout_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter
    chip_requests_route_module.get_database = getter
    notifications_route_module.get_database = getter
    settlement_route_module.get_database = getter
    checkout_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth
    games_route_module.get_database = orig_games
    chip_requests_route_module.get_database = orig_requests
    notifications_route_module.get_database = orig_notifications
    settlement_route_module.get_database = orig_settlement
    checkout_route_module.get_database = orig_checkout
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

async def _create_game(test_client: AsyncClient, manager_name: str = "Alice") -> dict:
    """Helper: create a game and return the response dict."""
    resp = await test_client.post("/api/games", json={"manager_name": manager_name})
    assert resp.status_code == 201
    return resp.json()


async def _join_game(test_client: AsyncClient, game_id: str, player_name: str) -> dict:
    """Helper: join a game and return the response dict."""
    resp = await test_client.post(
        f"/api/games/{game_id}/join",
        json={"player_name": player_name},
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_request(
    test_client: AsyncClient,
    game_id: str,
    player_token: str,
    request_type: str = "CASH",
    amount: int = 100,
) -> dict:
    """Helper: create a chip request and return the response dict."""
    resp = await test_client.post(
        f"/api/games/{game_id}/requests",
        json={"request_type": request_type, "amount": amount},
        headers={"X-Player-Token": player_token},
    )
    assert resp.status_code == 201
    return resp.json()


async def _approve_request(
    test_client: AsyncClient,
    game_id: str,
    request_id: str,
    manager_token: str,
) -> dict:
    """Helper: approve a chip request."""
    resp = await test_client.post(
        f"/api/games/{game_id}/requests/{request_id}/approve",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


async def _settle_game(
    test_client: AsyncClient,
    game_id: str,
    manager_token: str,
) -> dict:
    """Helper: settle a game (OPEN -> SETTLING)."""
    resp = await test_client.post(
        f"/api/games/{game_id}/settle",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


async def _checkout_all(
    test_client: AsyncClient,
    game_id: str,
    manager_token: str,
    player_chips: list[dict],
) -> dict:
    """Helper: checkout all players."""
    resp = await test_client.post(
        f"/api/games/{game_id}/checkout-all",
        json={"player_chips": player_chips},
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


async def _setup_settled_game_with_credit_player(test_client: AsyncClient):
    """Setup a game in SETTLING status with one credit-debt player checked out.

    Creates:
    - Alice (manager) with no buy-in
    - Bob with a 100-chip CREDIT buy-in (will have credits_owed=100)

    Settles game, then checks out all players. Bob ends with 80 chips
    and still has credit debt.

    Returns (game, manager_token, bob).
    """
    game = await _create_game(test_client, "Alice")
    manager_token = game["player_token"]
    game_id = game["game_id"]

    bob = await _join_game(test_client, game_id, "Bob")

    # Bob buys in 100 on CREDIT
    bob_req = await _create_request(
        test_client, game_id, bob["player_token"], "CREDIT", 100
    )
    await _approve_request(test_client, game_id, bob_req["id"], manager_token)

    # Settle the game
    await _settle_game(test_client, game_id, manager_token)

    # Checkout all players
    await _checkout_all(
        test_client, game_id, manager_token,
        [
            {"player_id": manager_token, "final_chip_count": 0},
            {"player_id": bob["player_token"], "final_chip_count": 80},
        ],
    )

    return game, manager_token, bob


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/players/{player_token}/settle-debt
# ---------------------------------------------------------------------------

class TestSettleDebt:
    """Tests for POST /api/games/{game_id}/players/{player_token}/settle-debt."""

    @pytest.mark.asyncio
    async def test_settle_debt_success(self, test_client: AsyncClient):
        """Successfully settle a checked-out player's credit debt."""
        game, manager_token, bob = await _setup_settled_game_with_credit_player(
            test_client
        )
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == bob["player_token"]
        assert data["player_name"] == "Bob"
        assert data["previous_credits_owed"] == 100
        assert data["credits_owed"] == 0
        assert data["settled"] is True

    @pytest.mark.asyncio
    async def test_settle_debt_player_not_found(self, test_client: AsyncClient):
        """Settle debt for a non-existent player returns 404."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/players/nonexistent-token/settle-debt",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_settle_debt_player_not_checked_out(self, test_client: AsyncClient):
        """Settle debt for a player who is not checked out returns 400."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in on CREDIT (gives him debt)
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Bob is NOT checked out -- attempt to settle debt
        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400
        assert "checked out" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_settle_debt_no_debt(self, test_client: AsyncClient):
        """Settle debt for a player with no outstanding debt returns 400."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in on CASH (no debt)
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Settle game and checkout all
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 0},
                {"player_id": bob["player_token"], "final_chip_count": 100},
            ],
        )

        # Bob is checked out but has no debt
        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400
        assert "no outstanding debt" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_settle_debt_non_manager_returns_403(self, test_client: AsyncClient):
        """Settle debt by non-manager returns 403."""
        game, manager_token, bob = await _setup_settled_game_with_credit_player(
            test_client
        )
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_settle_debt_no_auth_returns_401(self, test_client: AsyncClient):
        """Settle debt without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/players/some-token/settle-debt",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/close
# ---------------------------------------------------------------------------

class TestCloseGame:
    """Tests for POST /api/games/{game_id}/close."""

    @pytest.mark.asyncio
    async def test_close_game_success(self, test_client: AsyncClient):
        """Successfully close a SETTLING game with all players checked out."""
        game, manager_token, bob = await _setup_settled_game_with_credit_player(
            test_client
        )
        game_id = game["game_id"]

        # Settle Bob's debt first so we can test the clean close
        await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": manager_token},
        )

        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == game_id
        assert data["status"] == "CLOSED"
        assert "closed_at" in data
        assert data["summary"]["total_players"] == 2
        assert data["summary"]["unsettled_debts"] == 0

    @pytest.mark.asyncio
    async def test_close_game_not_settling_returns_400(self, test_client: AsyncClient):
        """Close game that is not in SETTLING status returns 400."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Game is OPEN, not SETTLING
        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400
        assert "settling" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_close_game_active_players_remain_returns_400(
        self, test_client: AsyncClient
    ):
        """Close game with unchecked-out active players returns 400."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Settle the game (OPEN -> SETTLING)
        await _settle_game(test_client, game_id, manager_token)

        # Do NOT checkout anyone -- attempt to close
        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400
        assert "checked out" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_close_game_with_unsettled_debts_succeeds(
        self, test_client: AsyncClient
    ):
        """Close game succeeds even when players have unsettled debts."""
        game, manager_token, bob = await _setup_settled_game_with_credit_player(
            test_client
        )
        game_id = game["game_id"]

        # Do NOT settle Bob's debt -- close the game anyway
        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CLOSED"
        assert data["summary"]["unsettled_debts"] == 1

    @pytest.mark.asyncio
    async def test_close_game_non_manager_returns_403(self, test_client: AsyncClient):
        """Close game by non-manager returns 403."""
        game, manager_token, bob = await _setup_settled_game_with_credit_player(
            test_client
        )
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_close_game_no_auth_returns_401(self, test_client: AsyncClient):
        """Close game without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        resp = await test_client.post(f"/api/games/{game_id}/close")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_close_game_summary_totals(self, test_client: AsyncClient):
        """Close game response includes correct summary totals."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")

        # Bob buys in 100 CASH
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Charlie buys in 100 CASH
        charlie_req = await _create_request(
            test_client, game_id, charlie["player_token"], "CASH", 100
        )
        await _approve_request(
            test_client, game_id, charlie_req["id"], manager_token
        )

        # Settle and checkout
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 0},
                {"player_id": bob["player_token"], "final_chip_count": 130},
                {"player_id": charlie["player_token"], "final_chip_count": 70},
            ],
        )

        # Close
        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert summary["total_players"] == 3
        # Bob: 130-100=+30, Charlie: 70-100=-30, Manager: 0
        assert summary["total_profit"] == 30
        assert summary["total_loss"] == 30
        assert summary["unsettled_debts"] == 0
