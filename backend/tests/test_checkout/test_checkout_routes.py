"""Integration tests for checkout route handlers.

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
    orig_checkout = checkout_route_module.get_database

    db_module.get_database = getter
    auth_deps_module.get_database = getter
    games_route_module.get_database = getter
    chip_requests_route_module.get_database = getter
    notifications_route_module.get_database = getter
    checkout_route_module.get_database = getter

    yield db

    db_module.get_database = orig_db
    auth_deps_module.get_database = orig_auth
    games_route_module.get_database = orig_games
    chip_requests_route_module.get_database = orig_requests
    notifications_route_module.get_database = orig_notifications
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
# Helper functions
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


async def _approve_request(test_client, game_id, request_id, manager_token):
    resp = await test_client.post(
        f"/api/games/{game_id}/requests/{request_id}/approve",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


async def _setup_player_with_buy_in(
    test_client,
    game_id,
    manager_token,
    player_name="Bob",
    request_type="CASH",
    amount=100,
):
    """Create a player, submit a request, approve it, and return player info."""
    player = await _join_game(test_client, game_id, player_name)
    req = await _create_request(
        test_client, game_id, player["player_token"], request_type, amount
    )
    await _approve_request(test_client, game_id, req["id"], manager_token)
    return player


async def _checkout_player(test_client, game_id, player_token, manager_token, final_chip_count):
    """Checkout a player and return the response object."""
    resp = await test_client.post(
        f"/api/games/{game_id}/players/{player_token}/checkout",
        json={"final_chip_count": final_chip_count},
        headers={"X-Player-Token": manager_token},
    )
    return resp


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/players/{player_token}/checkout
# ---------------------------------------------------------------------------

class TestCheckoutPlayerProfit:
    """Test checkout when player has a profit (final > buy-in)."""

    @pytest.mark.asyncio
    async def test_checkout_with_profit(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        resp = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 150
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == bob["player_token"]
        assert data["player_name"] == "Bob"
        assert data["final_chip_count"] == 150
        assert data["total_buy_in"] == 100
        assert data["profit_loss"] == 50
        assert data["credits_owed"] == 0
        assert data["has_debt"] is False
        assert data["checked_out_at"] is not None


class TestCheckoutPlayerLoss:
    """Test checkout when player has a loss (final < buy-in)."""

    @pytest.mark.asyncio
    async def test_checkout_with_loss(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 200
        )

        resp = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 50
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["final_chip_count"] == 50
        assert data["total_buy_in"] == 200
        assert data["profit_loss"] == -150


class TestCheckoutPlayerBreakEven:
    """Test checkout when player breaks even (final == buy-in)."""

    @pytest.mark.asyncio
    async def test_checkout_break_even(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        resp = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 100
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["final_chip_count"] == 100
        assert data["total_buy_in"] == 100
        assert data["profit_loss"] == 0


class TestCheckoutPlayerWithCredits:
    """Test checkout when player has outstanding credits (has_debt=True)."""

    @pytest.mark.asyncio
    async def test_checkout_with_credits_owed(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Player buys in with both cash and credit
        bob = await _join_game(test_client, game_id, "Bob")
        bob_token = bob["player_token"]

        # Cash buy-in of 100
        cash_req = await _create_request(
            test_client, game_id, bob_token, "CASH", 100
        )
        await _approve_request(test_client, game_id, cash_req["id"], manager_token)

        # Credit buy-in of 50
        credit_req = await _create_request(
            test_client, game_id, bob_token, "CREDIT", 50
        )
        await _approve_request(test_client, game_id, credit_req["id"], manager_token)

        # Checkout with 120 chips
        resp = await _checkout_player(
            test_client, game_id, bob_token, manager_token, 120
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_buy_in"] == 150  # 100 cash + 50 credit
        assert data["profit_loss"] == -30   # 120 - 150
        assert data["credits_owed"] == 50
        assert data["has_debt"] is True


class TestCheckoutAlreadyCheckedOut:
    """Test that checking out an already checked-out player returns 400."""

    @pytest.mark.asyncio
    async def test_checkout_already_checked_out_returns_400(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # First checkout succeeds
        resp1 = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 80
        )
        assert resp1.status_code == 200

        # Second checkout returns 400
        resp2 = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 80
        )
        assert resp2.status_code == 400
        assert "already checked out" in resp2.json()["detail"].lower()


class TestCheckoutClosedGame:
    """Test that checkout in a CLOSED game returns 400."""

    @pytest.mark.asyncio
    async def test_checkout_in_closed_game_returns_400(self, test_client, mock_db):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # Manually close the game in the database
        from bson import ObjectId

        await mock_db["games"].update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"status": "CLOSED"}},
        )

        resp = await _checkout_player(
            test_client, game_id, bob["player_token"], manager_token, 80
        )
        assert resp.status_code == 400
        assert "CLOSED" in resp.json()["detail"]


class TestCheckoutNonexistentPlayer:
    """Test that checkout for a nonexistent player returns 404."""

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_player_returns_404(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        fake_token = "00000000-0000-4000-8000-000000000000"

        resp = await _checkout_player(
            test_client, game_id, fake_token, manager_token, 0
        )
        assert resp.status_code == 404


class TestCheckoutRequiresManager:
    """Test that non-manager players cannot checkout others."""

    @pytest.mark.asyncio
    async def test_checkout_as_non_manager_returns_403(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )
        charlie = await _join_game(test_client, game_id, "Charlie")

        # Charlie (non-manager) tries to checkout Bob
        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/checkout",
            json={"final_chip_count": 80},
            headers={"X-Player-Token": charlie["player_token"]},
        )
        assert resp.status_code == 403


class TestCheckoutNoAuth:
    """Test that checkout without auth header returns 401."""

    @pytest.mark.asyncio
    async def test_checkout_without_auth_returns_401(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # No X-Player-Token header
        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/checkout",
            json={"final_chip_count": 80},
        )
        assert resp.status_code == 401


class TestCheckoutNegativeChips:
    """Test that negative final_chip_count returns 422 (validation error)."""

    @pytest.mark.asyncio
    async def test_checkout_negative_chips_returns_422(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/checkout",
            json={"final_chip_count": -10},
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 422
