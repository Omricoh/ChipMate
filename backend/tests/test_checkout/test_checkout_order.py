"""Integration tests for checkout order route handlers.

Tests the checkout order and checkout next endpoints using HTTPX AsyncClient
with the FastAPI app and mongomock-motor (no real MongoDB required).
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


async def _get_checkout_order(test_client, game_id, manager_token):
    """Get checkout order and return the response object."""
    resp = await test_client.get(
        f"/api/games/{game_id}/checkout/order",
        headers={"X-Player-Token": manager_token},
    )
    return resp


async def _checkout_next(test_client, game_id, manager_token, final_chip_count):
    """Checkout next player and return the response object."""
    resp = await test_client.post(
        f"/api/games/{game_id}/checkout/next",
        json={"final_chip_count": final_chip_count},
        headers={"X-Player-Token": manager_token},
    )
    return resp


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/checkout/order
# ---------------------------------------------------------------------------

class TestGetCheckoutOrderEmpty:
    """Test checkout order when there are no players to checkout."""

    @pytest.mark.asyncio
    async def test_checkout_order_empty_game(self, test_client):
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()
        # Manager is the only player and they are active
        assert data["total_players"] == 1
        assert len(data["order"]) == 1
        assert data["order"][0]["display_name"] == "Alice"


class TestGetCheckoutOrderBasic:
    """Test basic checkout order without credits."""

    @pytest.mark.asyncio
    async def test_checkout_order_alphabetical(self, test_client):
        """Players without credits should be sorted alphabetically."""
        game = await _create_game(test_client, manager_name="Zara")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Create players in non-alphabetical order
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Charlie", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_players"] == 4  # manager + 3 players

        names = [p["display_name"] for p in data["order"]]
        # Should be alphabetical: Alice, Bob, Charlie, Zara
        assert names == ["Alice", "Bob", "Charlie", "Zara"]

        # All players should have no debt
        for player in data["order"]:
            assert player["has_debt"] is False
            assert player["credits_owed"] == 0


class TestGetCheckoutOrderWithCredits:
    """Test checkout order prioritizes players with credits."""

    @pytest.mark.asyncio
    async def test_credit_players_first(self, test_client):
        """Players with credits should come before players without."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Create player with only cash (no credits)
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )

        # Create player with credits
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CREDIT", 50
        )

        # Create another player with only cash
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Charlie", "CASH", 100
        )

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_players"] == 4

        names = [p["display_name"] for p in data["order"]]
        # Bob (credit) should be first, then alphabetical: Alice, Charlie, Manager
        assert names == ["Bob", "Alice", "Charlie", "Manager"]

        # Check Bob has debt
        assert data["order"][0]["has_debt"] is True
        assert data["order"][0]["credits_owed"] == 50


class TestGetCheckoutOrderMultipleCredits:
    """Test checkout order with multiple credit players."""

    @pytest.mark.asyncio
    async def test_multiple_credit_players_alphabetical(self, test_client):
        """Multiple credit players should be sorted alphabetically among themselves."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Credit players in non-alphabetical order
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Zoe", "CREDIT", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Aaron", "CREDIT", 50
        )

        # Non-credit players
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Mike", "CASH", 100
        )

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()

        names = [p["display_name"] for p in data["order"]]
        # Credit players first (alphabetical): Aaron, Zoe
        # Then non-credit (alphabetical): Manager, Mike
        assert names == ["Aaron", "Zoe", "Manager", "Mike"]


class TestGetCheckoutOrderCaseInsensitive:
    """Test checkout order uses case-insensitive alphabetical sorting."""

    @pytest.mark.asyncio
    async def test_case_insensitive_sorting(self, test_client):
        """Sorting should be case-insensitive."""
        game = await _create_game(test_client, manager_name="manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "bob", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "CHARLIE", "CASH", 100
        )

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()

        names = [p["display_name"] for p in data["order"]]
        # Case-insensitive: Alice, bob, CHARLIE, manager
        assert names == ["Alice", "bob", "CHARLIE", "manager"]


class TestGetCheckoutOrderAuth:
    """Test authentication requirements for checkout order."""

    @pytest.mark.asyncio
    async def test_checkout_order_requires_manager(self, test_client):
        """Non-manager should not be able to get checkout order."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        player = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # Bob (non-manager) tries to get checkout order
        resp = await test_client.get(
            f"/api/games/{game_id}/checkout/order",
            headers={"X-Player-Token": player["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_checkout_order_requires_auth(self, test_client):
        """Request without auth should return 401."""
        game = await _create_game(test_client)
        game_id = game["game_id"]

        resp = await test_client.get(f"/api/games/{game_id}/checkout/order")
        assert resp.status_code == 401


class TestGetCheckoutOrderNotFound:
    """Test checkout order for non-existent game."""

    @pytest.mark.asyncio
    async def test_checkout_order_game_not_found(self, test_client):
        """Request for non-existent game should return 404."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]

        fake_game_id = "000000000000000000000000"
        resp = await test_client.get(
            f"/api/games/{fake_game_id}/checkout/order",
            headers={"X-Player-Token": manager_token},
        )
        # Should return 404 for game not found
        assert resp.status_code == 404


class TestGetCheckoutOrderExcludesCheckedOut:
    """Test that checkout order excludes already checked-out players."""

    @pytest.mark.asyncio
    async def test_excludes_checked_out_players(self, test_client):
        """Players who are already checked out should not appear in the order."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        alice = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # Checkout Alice
        await test_client.post(
            f"/api/games/{game_id}/players/{alice['player_token']}/checkout",
            json={"final_chip_count": 100},
            headers={"X-Player-Token": manager_token},
        )

        resp = await _get_checkout_order(test_client, game_id, manager_token)

        assert resp.status_code == 200
        data = resp.json()

        names = [p["display_name"] for p in data["order"]]
        # Alice should not be in the order (checked out)
        assert "Alice" not in names
        assert "Bob" in names
        assert "Manager" in names


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/checkout/next
# ---------------------------------------------------------------------------

class TestCheckoutNextBasic:
    """Test basic checkout next functionality."""

    @pytest.mark.asyncio
    async def test_checkout_next_single_player(self, test_client):
        """Checkout next should checkout the first player in the order."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )

        resp = await _checkout_next(test_client, game_id, manager_token, 150)

        assert resp.status_code == 200
        data = resp.json()
        # Alice should be checked out first (alphabetically before Manager)
        assert data["player_name"] == "Alice"
        assert data["final_chip_count"] == 150
        assert data["total_buy_in"] == 100
        assert data["profit_loss"] == 50


class TestCheckoutNextOrder:
    """Test that checkout next respects the priority order."""

    @pytest.mark.asyncio
    async def test_checkout_next_respects_credit_priority(self, test_client):
        """Credit players should be checked out before non-credit players."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Non-credit player (alphabetically first)
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Aaron", "CASH", 100
        )
        # Credit player (alphabetically last)
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Zoe", "CREDIT", 50
        )

        # First checkout should be Zoe (credit player)
        resp1 = await _checkout_next(test_client, game_id, manager_token, 50)
        assert resp1.status_code == 200
        assert resp1.json()["player_name"] == "Zoe"

        # Second checkout should be Aaron
        resp2 = await _checkout_next(test_client, game_id, manager_token, 100)
        assert resp2.status_code == 200
        assert resp2.json()["player_name"] == "Aaron"

        # Third checkout should be Manager
        resp3 = await _checkout_next(test_client, game_id, manager_token, 0)
        assert resp3.status_code == 200
        assert resp3.json()["player_name"] == "Manager"


class TestCheckoutNextSequential:
    """Test sequential checkout next calls."""

    @pytest.mark.asyncio
    async def test_checkout_next_sequential(self, test_client):
        """Multiple checkout next calls should process players in order."""
        game = await _create_game(test_client, manager_name="Zara")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Charlie", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Alice", "CASH", 100
        )
        await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # Checkout in alphabetical order: Alice, Bob, Charlie, Zara
        resp1 = await _checkout_next(test_client, game_id, manager_token, 100)
        assert resp1.json()["player_name"] == "Alice"

        resp2 = await _checkout_next(test_client, game_id, manager_token, 100)
        assert resp2.json()["player_name"] == "Bob"

        resp3 = await _checkout_next(test_client, game_id, manager_token, 100)
        assert resp3.json()["player_name"] == "Charlie"

        resp4 = await _checkout_next(test_client, game_id, manager_token, 100)
        assert resp4.json()["player_name"] == "Zara"


class TestCheckoutNextEmpty:
    """Test checkout next when no players remain."""

    @pytest.mark.asyncio
    async def test_checkout_next_no_players_returns_400(self, test_client):
        """Checkout next with no remaining players should return 400."""
        game = await _create_game(test_client, manager_name="Manager")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Checkout the only player (manager)
        resp1 = await _checkout_next(test_client, game_id, manager_token, 0)
        assert resp1.status_code == 200

        # Try to checkout again - no players left
        resp2 = await _checkout_next(test_client, game_id, manager_token, 0)
        assert resp2.status_code == 400
        assert "no players remaining" in resp2.json()["detail"].lower()


class TestCheckoutNextAuth:
    """Test authentication requirements for checkout next."""

    @pytest.mark.asyncio
    async def test_checkout_next_requires_manager(self, test_client):
        """Non-manager should not be able to checkout next."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        player = await _setup_player_with_buy_in(
            test_client, game_id, manager_token, "Bob", "CASH", 100
        )

        # Bob (non-manager) tries to checkout next
        resp = await test_client.post(
            f"/api/games/{game_id}/checkout/next",
            json={"final_chip_count": 100},
            headers={"X-Player-Token": player["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_checkout_next_requires_auth(self, test_client):
        """Request without auth should return 401."""
        game = await _create_game(test_client)
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout/next",
            json={"final_chip_count": 100},
        )
        assert resp.status_code == 401


class TestCheckoutNextValidation:
    """Test input validation for checkout next."""

    @pytest.mark.asyncio
    async def test_checkout_next_negative_chips_returns_422(self, test_client):
        """Negative final_chip_count should return 422."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout/next",
            json={"final_chip_count": -10},
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_checkout_next_missing_body_returns_422(self, test_client):
        """Missing request body should return 422."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]
        game_id = game["game_id"]

        resp = await test_client.post(
            f"/api/games/{game_id}/checkout/next",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 422


class TestCheckoutNextNotFound:
    """Test checkout next for non-existent game."""

    @pytest.mark.asyncio
    async def test_checkout_next_game_not_found(self, test_client):
        """Request for non-existent game should return 404."""
        game = await _create_game(test_client)
        manager_token = game["player_token"]

        fake_game_id = "000000000000000000000000"
        resp = await test_client.post(
            f"/api/games/{fake_game_id}/checkout/next",
            json={"final_chip_count": 100},
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 404
