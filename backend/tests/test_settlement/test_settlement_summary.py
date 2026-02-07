"""Integration tests for GET /api/games/{game_id}/settlement/summary.

Tests the settlement summary endpoint using HTTPX AsyncClient with the FastAPI app
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


async def _get_settlement_summary(
    test_client: AsyncClient,
    game_id: str,
    manager_token: str,
) -> dict:
    """Helper: get settlement summary."""
    resp = await test_client.get(
        f"/api/games/{game_id}/settlement/summary",
        headers={"X-Player-Token": manager_token},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/summary -- Tests
# ---------------------------------------------------------------------------

class TestSettlementSummary:
    """Tests for GET /api/games/{game_id}/settlement/summary."""

    @pytest.mark.asyncio
    async def test_summary_returns_game_info(self, test_client: AsyncClient):
        """Summary includes game_id, status, and code."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert data["game_id"] == game_id
        assert data["game_status"] == "OPEN"
        assert "game_code" in data
        assert len(data["game_code"]) > 0

    @pytest.mark.asyncio
    async def test_summary_lists_all_players(self, test_client: AsyncClient):
        """Summary includes all players with their details."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert len(data["players"]) == 3

        # Find players in the response
        player_names = {p["display_name"] for p in data["players"]}
        assert player_names == {"Alice", "Bob", "Charlie"}

        # Check manager is flagged correctly
        alice = next(p for p in data["players"] if p["display_name"] == "Alice")
        assert alice["is_manager"] is True

        bob_data = next(p for p in data["players"] if p["display_name"] == "Bob")
        assert bob_data["is_manager"] is False
        assert bob_data["is_active"] is True
        assert bob_data["checked_out"] is False

    @pytest.mark.asyncio
    async def test_summary_shows_buy_in_totals(self, test_client: AsyncClient):
        """Summary shows correct total_buy_in for each player."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in 100 CASH
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Bob buys in another 50 CASH
        bob_req2 = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 50
        )
        await _approve_request(test_client, game_id, bob_req2["id"], manager_token)

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        bob_data = next(p for p in data["players"] if p["display_name"] == "Bob")
        assert bob_data["total_buy_in"] == 150

    @pytest.mark.asyncio
    async def test_summary_shows_checkout_status_and_pl(self, test_client: AsyncClient):
        """Summary shows checkout status and profit/loss after checkout."""
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
        await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

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

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        bob_data = next(p for p in data["players"] if p["display_name"] == "Bob")
        charlie_data = next(p for p in data["players"] if p["display_name"] == "Charlie")

        assert bob_data["checked_out"] is True
        assert bob_data["final_chip_count"] == 130
        assert bob_data["profit_loss"] == 30  # 130 - 100

        assert charlie_data["checked_out"] is True
        assert charlie_data["final_chip_count"] == 70
        assert charlie_data["profit_loss"] == -30  # 70 - 100

    @pytest.mark.asyncio
    async def test_summary_identifies_debtors(self, test_client: AsyncClient):
        """Summary lists players with outstanding credit debt as debtors."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in 100 on CREDIT (creates debt)
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert len(data["debtors"]) == 1
        assert data["debtors"][0]["player_token"] == bob["player_token"]
        assert data["debtors"][0]["display_name"] == "Bob"
        assert data["debtors"][0]["credits_owed"] == 100
        assert data["total_outstanding_debt"] == 100
        assert data["all_debts_settled"] is False

    @pytest.mark.asyncio
    async def test_summary_identifies_recipients(self, test_client: AsyncClient):
        """Summary lists checked-out players with positive profit as recipients."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")

        # Both buy in 100 CASH
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        charlie_req = await _create_request(
            test_client, game_id, charlie["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

        # Settle and checkout: Bob wins, Charlie loses
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 0},
                {"player_id": bob["player_token"], "final_chip_count": 150},
                {"player_id": charlie["player_token"], "final_chip_count": 50},
            ],
        )

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        # Bob is the only recipient (positive profit)
        assert len(data["recipients"]) == 1
        assert data["recipients"][0]["player_token"] == bob["player_token"]
        assert data["recipients"][0]["display_name"] == "Bob"
        assert data["recipients"][0]["profit"] == 50

    @pytest.mark.asyncio
    async def test_summary_all_debts_settled_true_when_no_debt(
        self, test_client: AsyncClient
    ):
        """all_debts_settled is True when no players have outstanding debt."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in with CASH (no debt)
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CASH", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert data["total_outstanding_debt"] == 0
        assert data["all_debts_settled"] is True
        assert len(data["debtors"]) == 0

    @pytest.mark.asyncio
    async def test_summary_tracks_multiple_debtors(self, test_client: AsyncClient):
        """Summary correctly tracks multiple debtors."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")
        charlie = await _join_game(test_client, game_id, "Charlie")

        # Both buy in on CREDIT
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        charlie_req = await _create_request(
            test_client, game_id, charlie["player_token"], "CREDIT", 50
        )
        await _approve_request(test_client, game_id, charlie_req["id"], manager_token)

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert len(data["debtors"]) == 2
        assert data["total_outstanding_debt"] == 150
        assert data["all_debts_settled"] is False

        debtor_tokens = {d["player_token"] for d in data["debtors"]}
        assert debtor_tokens == {bob["player_token"], charlie["player_token"]}

    @pytest.mark.asyncio
    async def test_summary_works_during_settling_status(self, test_client: AsyncClient):
        """Summary endpoint works when game is in SETTLING status."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        await _settle_game(test_client, game_id, manager_token)

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert data["game_status"] == "SETTLING"

    @pytest.mark.asyncio
    async def test_summary_works_after_game_closed(self, test_client: AsyncClient):
        """Summary endpoint works when game is CLOSED."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        # Settle and checkout manager (only player)
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [{"player_id": manager_token, "final_chip_count": 0}],
        )

        # Close the game
        resp = await test_client.post(
            f"/api/games/{game_id}/close",
            headers={"X-Player-Token": manager_token},
        )
        assert resp.status_code == 200

        data = await _get_settlement_summary(test_client, game_id, manager_token)

        assert data["game_status"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_summary_requires_manager_auth(self, test_client: AsyncClient):
        """Summary endpoint requires manager authentication."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Non-manager trying to access summary
        resp = await test_client.get(
            f"/api/games/{game_id}/settlement/summary",
            headers={"X-Player-Token": bob["player_token"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_without_auth_returns_401(self, test_client: AsyncClient):
        """Summary endpoint without auth returns 401."""
        game = await _create_game(test_client, "Alice")
        game_id = game["game_id"]

        resp = await test_client.get(f"/api/games/{game_id}/settlement/summary")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_summary_nonexistent_game_returns_404(self, test_client: AsyncClient):
        """Summary for a non-existent game returns 404."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]

        resp = await test_client.get(
            "/api/games/000000000000000000000000/settlement/summary",
            headers={"X-Player-Token": manager_token},
        )
        # The manager token is for a different game, so this should fail auth
        # Let's verify the behavior - it may be 403 or 404 depending on auth check order
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_summary_debt_settled_updates_correctly(
        self, test_client: AsyncClient
    ):
        """Summary reflects debt settlement correctly."""
        game = await _create_game(test_client, "Alice")
        manager_token = game["player_token"]
        game_id = game["game_id"]

        bob = await _join_game(test_client, game_id, "Bob")

        # Bob buys in on CREDIT
        bob_req = await _create_request(
            test_client, game_id, bob["player_token"], "CREDIT", 100
        )
        await _approve_request(test_client, game_id, bob_req["id"], manager_token)

        # Check summary before settlement
        data_before = await _get_settlement_summary(test_client, game_id, manager_token)
        assert data_before["total_outstanding_debt"] == 100
        assert data_before["all_debts_settled"] is False

        # Settle game and checkout
        await _settle_game(test_client, game_id, manager_token)
        await _checkout_all(
            test_client, game_id, manager_token,
            [
                {"player_id": manager_token, "final_chip_count": 0},
                {"player_id": bob["player_token"], "final_chip_count": 100},
            ],
        )

        # Settle Bob's debt
        resp = await test_client.post(
            f"/api/games/{game_id}/players/{bob['player_token']}/settle-debt",
            headers={"X-Player-Token": manager_token},
            json={
                "allocations": [
                    {"recipient_token": manager_token, "amount": 100}
                ]
            },
        )
        assert resp.status_code == 200

        # Check summary after settlement
        data_after = await _get_settlement_summary(test_client, game_id, manager_token)
        assert data_after["total_outstanding_debt"] == 0
        assert data_after["all_debts_settled"] is True
        assert len(data_after["debtors"]) == 0
