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
    """Helper: settle a game."""
    resp = await test_client.post(
        f"/api/games/{game_id}/settle",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


async def _setup_game_with_players(test_client: AsyncClient):
    """Helper: create game with manager (Alice) + two players (Bob, Charlie).

    Each player gets a 100-chip CASH buy-in approved.
    Returns (game, alice_token, bob, charlie).
    """
    game = await _create_game(test_client, "Alice")
    manager_token = game["player_token"]
    game_id = game["game_id"]

    bob = await _join_game(test_client, game_id, "Bob")
    charlie = await _join_game(test_client, game_id, "Charlie")

    # Bob buys in 100 CASH
    bob_req = await _create_request(test_client, game_id, bob["player_token"], "CASH", 100)
    await _approve_request(test_client, game_id, bob_req["id"], manager_token)

    # Charlie buys in 100 CASH
    charlie_req = await _create_request(test_client, game_id, charlie["player_token"], "CASH", 100)
    await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

    return game, manager_token, bob, charlie


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settle -- Start settling
# ---------------------------------------------------------------------------

class TestSettleGame:
    """Tests for POST /api/games/{game_id}/settle."""

    @pytest.mark.asyncio
    async def test_settle_transitions_open_to_settling(self, test_client: AsyncClient):
        """Start settling transitions OPEN -> SETTLING."""
        game = await _create_game(test_client, "Alice")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settle",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SETTLING"
        assert data["game_id"] == game["game_id"]
        assert "settling" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_settle_non_open_game_returns_400(self, test_client: AsyncClient):
        """Start settling on a non-OPEN game returns 400."""
        game = await _create_game(test_client, "Alice")
        # First settle
        await _settle_game(test_client, game["game_id"], game["player_token"])
        # Attempt to settle again (SETTLING -> SETTLING should fail)
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settle",
            headers={"X-Player-Token": game["player_token"]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_settle_requires_manager(self, test_client: AsyncClient):
        """Start settling requires manager auth."""
        game = await _create_game(test_client, "Alice")
        bob = await _join_game(test_client, game["game_id"], "Bob")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/settle",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_settle_without_auth_returns_401(self, test_client: AsyncClient):
        """Start settling without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        resp = await test_client.post(f"/api/games/{game['game_id']}/settle")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_settle_declines_pending_requests(self, test_client: AsyncClient):
        """Start settling declines all pending requests."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Create two pending requests
        await _create_request(test_client, game_id, bob["player_token"], "CASH", 100)
        await _create_request(test_client, game_id, bob["player_token"], "CASH", 200)

        # Settle the game
        await _settle_game(test_client, game_id, manager_token)

        # Verify pending requests are now empty
        resp = await test_client.get(
            f"/api/games/{game_id}/requests/pending",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/checkout-all -- Batch checkout
# ---------------------------------------------------------------------------

class TestCheckoutAll:
    """Tests for POST /api/games/{game_id}/checkout-all."""

    @pytest.mark.asyncio
    async def test_checkout_all_success(self, test_client: AsyncClient):
        """Checkout all players successfully."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        # Settle the game
        await _settle_game(test_client, game_id, manager_token)

        # Checkout all (manager included as active player)
        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 120},
                    {"player_id": charlie["player_token"], "final_chip_count": 80},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["checked_out"]) == 3
        assert data["summary"]["total_checked_out"] == 3

    @pytest.mark.asyncio
    async def test_checkout_all_correct_pl(self, test_client: AsyncClient):
        """Checkout all calculates correct P/L for each player."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 150},
                    {"player_id": charlie["player_token"], "final_chip_count": 50},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Find Bob and Charlie in results
        bob_result = next(
            p for p in data["checked_out"]
            if p["player_id"] == bob["player_token"]
        )
        charlie_result = next(
            p for p in data["checked_out"]
            if p["player_id"] == charlie["player_token"]
        )
        manager_result = next(
            p for p in data["checked_out"]
            if p["player_id"] == manager_token
        )

        # Bob bought in 100, ended with 150 -> P/L = +50
        assert bob_result["profit_loss"] == 50
        assert bob_result["final_chip_count"] == 150

        # Charlie bought in 100, ended with 50 -> P/L = -50
        assert charlie_result["profit_loss"] == -50
        assert charlie_result["final_chip_count"] == 50

        # Manager had 0 buy-in, 0 final -> P/L = 0
        assert manager_result["profit_loss"] == 0

    @pytest.mark.asyncio
    async def test_checkout_all_flags_credit_debt(self, test_client: AsyncClient):
        """Checkout all flags credit-debt players."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in 100 on CREDIT
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        await _settle_game(test_client, game_id, manager_token)

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 80},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        data = resp.json()

        bob_result = next(
            p for p in data["checked_out"]
            if p["player_id"] == bob["player_token"]
        )
        assert bob_result["has_debt"] is True
        assert data["summary"]["debt_players_count"] >= 1

    @pytest.mark.asyncio
    async def test_checkout_all_requires_settling(self, test_client: AsyncClient):
        """Checkout all requires SETTLING status (OPEN returns 400)."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        # Do NOT settle -- game is still OPEN
        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 100},
                    {"player_id": charlie["player_token"], "final_chip_count": 100},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_all_missing_player_returns_400(self, test_client: AsyncClient):
        """Checkout all requires all active players (missing returns 400)."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        # Only include Bob, missing Charlie and manager
        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": bob["player_token"], "final_chip_count": 100},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400
        assert "missing" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_checkout_all_negative_chip_count_returns_422(self, test_client: AsyncClient):
        """Checkout all with negative chip count returns 422."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": -10},
                    {"player_id": charlie["player_token"], "final_chip_count": 100},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_checkout_all_requires_manager(self, test_client: AsyncClient):
        """Checkout all requires manager auth."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 100},
                    {"player_id": charlie["player_token"], "final_chip_count": 100},
                ],
            },
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_checkout_all_without_auth_returns_401(self, test_client: AsyncClient):
        """Checkout all without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        resp = await test_client.post(
            f"/api/games/{game['game_id']}/checkout-all",
            json={"player_chips": []},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_checkout_all_no_active_players_returns_400(
        self, test_client: AsyncClient, mock_db
    ):
        """Checkout all with no active players returns 400."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Settle the game
        await _settle_game(test_client, game_id, manager_token)

        # Manually check out the manager via single checkout to leave 0 active
        from app.dal.players_dal import PlayerDAL
        player_dal = PlayerDAL(mock_db)
        manager_player = await player_dal.get_by_token(game_id, manager_token)
        await player_dal.update(
            str(manager_player.id),
            {"checked_out": True, "final_chip_count": 0, "profit_loss": 0},
        )

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_all_summary_totals(self, test_client: AsyncClient):
        """Summary totals are correct."""
        game, manager_token, bob, charlie = await _setup_game_with_players(test_client)
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout-all",
            json={
                "player_chips": [
                    {"player_id": manager_token, "final_chip_count": 0},
                    {"player_id": bob["player_token"], "final_chip_count": 130},
                    {"player_id": charlie["player_token"], "final_chip_count": 70},
                ],
            },
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]

        # Bob: 130 - 100 = +30, Charlie: 70 - 100 = -30, Manager: 0 - 0 = 0
        assert summary["total_checked_out"] == 3
        assert summary["total_profit"] == 30
        assert summary["total_loss"] == 30
        assert summary["debt_players_count"] == 0
