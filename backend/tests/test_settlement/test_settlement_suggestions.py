"""Integration tests for GET /api/games/{game_id}/settlement/suggestions.

Tests the smart settlement suggestions endpoint that calculates optimal
debt transfers to minimize the number of payments.
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


async def _get_settlement_suggestions(
    test_client: AsyncClient,
    game_id: str,
    manager_token: str,
) -> dict:
    """Helper: get settlement suggestions."""
    resp = await test_client.get(
        f"/api/games/{game_id}/settlement/suggestions",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/suggestions -- Tests
# ---------------------------------------------------------------------------

class TestSettlementSuggestions:
    """Tests for GET /api/games/{game_id}/settlement/suggestions."""

    @pytest.mark.asyncio
    async def test_suggestions_returns_empty_when_no_debt(
        self, test_client: AsyncClient
    ):
        """Returns empty suggestions when there are no debtors."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        assert data["game_id"] == game_id
        assert data["suggestions"] == []
        assert data["total_debt"] == 0
        assert data["transfer_count"] == 0

    @pytest.mark.asyncio
    async def test_suggestions_single_debtor_single_recipient(
        self, test_client: AsyncClient
    ):
        """Suggests single transfer when one debtor owes one recipient."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Alice buys 200 CASH
        alice_req = await _create_request(
            test_client, game_id, manager_token, "CASH", 200
        )
        await _approve_request(test_client, game_id, alice_req["id"], manager_token)

        # Bob buys 200 CREDIT (creates debt)
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 200
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Settle and checkout: Alice wins big, Bob loses
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 300},
                {"player_id": bob["player_token"], "final_chip_count": 100},
            ],
        )

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        # Bob still owes 100 (200 credit - 100 repaid from chips)
        assert data["total_debt"] == 100
        assert data["transfer_count"] == 1
        assert len(data["suggestions"]) == 1

        suggestion = data["suggestions"][0]
        assert suggestion["from_name"] == "Bob"
        assert suggestion["to_name"] == "Alice"
        assert suggestion["amount"] == 100

    @pytest.mark.asyncio
    async def test_suggestions_multiple_debtors_one_recipient(
        self, test_client: AsyncClient
    ):
        """Suggests multiple transfers when multiple debtors owe one recipient."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")

        # Alice buys 400 CASH
        alice_req = await _create_request(
            test_client, game_id, manager_token, "CASH", 400
        )
        await _approve_request(test_client, game_id, alice_req["id"], manager_token)

        # Bob buys 100 CREDIT
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Charlie buys 150 CREDIT
        charlie_req = await _create_request(
            test_client, game_id, charlie["player_token"], "CREDIT", 150
        )
        await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

        # Settle and checkout: Alice wins, Bob and Charlie bust out
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 650},
                {"player_id": bob["player_token"], "final_chip_count": 0},
                {"player_id": charlie["player_token"], "final_chip_count": 0},
            ],
        )

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        # Bob owes 100, Charlie owes 150 = 250 total
        assert data["total_debt"] == 250
        assert data["transfer_count"] == 2

        # Both should pay Alice
        from_names = {s["from_name"] for s in data["suggestions"]}
        assert from_names == {"Bob", "Charlie"}

        for suggestion in data["suggestions"]:
            assert suggestion["to_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_suggestions_minimizes_transfers(
        self, test_client: AsyncClient
    ):
        """Algorithm minimizes transfers by matching largest amounts first."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")
        dan = await _join_game(test_client, game_id, "Dan")

        # Alice buys 500 CASH
        alice_req = await _create_request(
            test_client, game_id, manager_token, "CASH", 500
        )
        await _approve_request(test_client, game_id, alice_req["id"], manager_token)

        # Bob buys 200 CASH
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 200
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Charlie buys 100 CREDIT (creates debt)
        charlie_req = await _create_request(
            test_client, game_id, charlie["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

        # Dan buys 200 CREDIT (creates debt)
        dan_req = await _create_request(
            test_client, game_id, dan["player_token"], "CREDIT", 200
        )
        await _approve_request(test_client, game_id, dan_req["id"], manager_token)

        # Settle and checkout:
        # Alice ends with 500 (profit 0)
        # Bob ends with 500 (profit 300)
        # Charlie ends with 0 (owes 100)
        # Dan ends with 0 (owes 200)
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 500},
                {"player_id": bob["player_token"], "final_chip_count": 500},
                {"player_id": charlie["player_token"], "final_chip_count": 0},
                {"player_id": dan["player_token"], "final_chip_count": 0},
            ],
        )

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        # Total debt is 300 (Charlie 100 + Dan 200)
        assert data["total_debt"] == 300

        # Should have 2 transfers (Dan->Bob 200, Charlie->Bob 100)
        # since Bob has 300 profit and both debtors together owe 300
        assert data["transfer_count"] == 2

    @pytest.mark.asyncio
    async def test_suggestions_requires_manager_auth(
        self, test_client: AsyncClient
    ):
        """Suggestions endpoint requires manager authentication."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        resp = await test_client.get(
            f"/api/games/{game_id}/settlement/suggestions",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_suggestions_without_auth_returns_401(
        self, test_client: AsyncClient
    ):
        """Suggestions endpoint without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        resp = await test_client.get(
            f"/api/games/{game_id}/settlement/suggestions"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_suggestions_includes_game_code(
        self, test_client: AsyncClient
    ):
        """Suggestions response includes game code."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        assert "game_code" in data
        assert len(data["game_code"]) > 0

    @pytest.mark.asyncio
    async def test_suggestions_fallback_to_host_when_no_recipients(
        self, test_client: AsyncClient
    ):
        """When no recipients have profit, debt is directed to host."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Only Bob buys in on CREDIT
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Settle and checkout: Bob loses everything
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 0},
                {"player_id": bob["player_token"], "final_chip_count": 0},
            ],
        )

        data = await _get_settlement_suggestions(test_client, game_id, manager_token)

        # Bob owes 100, no one has profit, so debt goes to host (Alice)
        assert data["total_debt"] == 100
        assert data["transfer_count"] == 1

        suggestion = data["suggestions"][0]
        assert suggestion["from_name"] == "Bob"
        assert suggestion["to_name"] == "Alice"
        assert suggestion["amount"] == 100
        assert "Host" in suggestion.get("note", "")
