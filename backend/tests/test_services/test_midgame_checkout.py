"""Unit tests for mid-game checkout (single player checkout during OPEN state)."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, CheckoutStatus, RequestType
from app.services.settlement_service import SettlementService
from app.services.game_service import GameService
from app.services.request_service import RequestService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def game_dal(mock_db) -> GameDAL:
    return GameDAL(mock_db)


@pytest_asyncio.fixture
async def player_dal(mock_db) -> PlayerDAL:
    return PlayerDAL(mock_db)


@pytest_asyncio.fixture
async def chip_request_dal(mock_db) -> ChipRequestDAL:
    return ChipRequestDAL(mock_db)


@pytest_asyncio.fixture
async def notification_dal(mock_db) -> NotificationDAL:
    return NotificationDAL(mock_db)


@pytest_asyncio.fixture
async def game_service(game_dal, player_dal, chip_request_dal) -> GameService:
    return GameService(game_dal, player_dal, chip_request_dal)


@pytest_asyncio.fixture
async def request_service(game_dal, player_dal, chip_request_dal, notification_dal) -> RequestService:
    return RequestService(game_dal, player_dal, chip_request_dal, notification_dal)


@pytest_asyncio.fixture
async def settlement_service(game_dal, player_dal, chip_request_dal, notification_dal) -> SettlementService:
    return SettlementService(game_dal, player_dal, chip_request_dal, notification_dal)


@pytest_asyncio.fixture
async def open_game_with_cash_player(game_service, request_service):
    """Create an open game with manager Alice (200 cash) and cash-only player Bob (100 cash)."""
    game_data = await game_service.create_game(manager_name="Alice")
    game_id = game_data["game_id"]
    manager_token = game_data["player_token"]

    # Bob joins
    bob_data = await game_service.join_game(game_id, player_name="Bob")
    bob_token = bob_data["player_token"]

    # Alice buys in 200 cash
    alice_req = await request_service.create_request(
        game_id=game_id, player_token=manager_token,
        request_type=RequestType.CASH, amount=200,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(alice_req.id),
        manager_token=manager_token,
    )

    # Bob buys in 100 cash only
    bob_cash_req = await request_service.create_request(
        game_id=game_id, player_token=bob_token,
        request_type=RequestType.CASH, amount=100,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(bob_cash_req.id),
        manager_token=manager_token,
    )

    return {
        "game_id": game_id,
        "manager_token": manager_token,
        "bob_token": bob_token,
    }


@pytest_asyncio.fixture
async def open_game_with_credit_player(game_service, request_service):
    """Create an open game with manager Alice and player Bob who has cash + credit."""
    game_data = await game_service.create_game(manager_name="Alice")
    game_id = game_data["game_id"]
    manager_token = game_data["player_token"]

    bob_data = await game_service.join_game(game_id, player_name="Bob")
    bob_token = bob_data["player_token"]

    # Alice buys in 200 cash
    alice_req = await request_service.create_request(
        game_id=game_id, player_token=manager_token,
        request_type=RequestType.CASH, amount=200,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(alice_req.id),
        manager_token=manager_token,
    )

    # Bob buys in 100 cash + 100 credit
    bob_cash_req = await request_service.create_request(
        game_id=game_id, player_token=bob_token,
        request_type=RequestType.CASH, amount=100,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(bob_cash_req.id),
        manager_token=manager_token,
    )

    bob_credit_req = await request_service.create_request(
        game_id=game_id, player_token=bob_token,
        request_type=RequestType.CREDIT, amount=100,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(bob_credit_req.id),
        manager_token=manager_token,
    )

    return {
        "game_id": game_id,
        "manager_token": manager_token,
        "bob_token": bob_token,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMidgameCheckout:

    async def test_midgame_checkout_sets_pending(
        self, settlement_service, player_dal, open_game_with_cash_player
    ):
        """Player gets PENDING status and frozen_buy_in after requesting mid-game checkout."""
        game_id = open_game_with_cash_player["game_id"]
        bob_token = open_game_with_cash_player["bob_token"]

        result = await settlement_service.request_midgame_checkout(game_id, bob_token)

        assert result["status"] == "checkout_initiated"
        assert result["player_token"] == bob_token

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.PENDING
        assert player.frozen_buy_in is not None
        assert player.frozen_buy_in["total_cash_in"] == 100
        assert player.frozen_buy_in["total_credit_in"] == 0
        assert player.frozen_buy_in["total_buy_in"] == 100

    async def test_midgame_checkout_fails_if_not_open(
        self, settlement_service, game_dal, open_game_with_cash_player
    ):
        """400 if game is SETTLING (not OPEN)."""
        game_id = open_game_with_cash_player["game_id"]
        bob_token = open_game_with_cash_player["bob_token"]

        # Transition game to SETTLING
        await settlement_service.start_settling(game_id)

        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.request_midgame_checkout(game_id, bob_token)
        assert exc_info.value.status_code == 400
        assert "OPEN" in exc_info.value.detail

    async def test_midgame_checkout_fails_if_already_in_checkout(
        self, settlement_service, open_game_with_cash_player
    ):
        """400 if player already has a checkout_status."""
        game_id = open_game_with_cash_player["game_id"]
        bob_token = open_game_with_cash_player["bob_token"]

        # First checkout request succeeds
        await settlement_service.request_midgame_checkout(game_id, bob_token)

        # Second request should fail
        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.request_midgame_checkout(game_id, bob_token)
        assert exc_info.value.status_code == 400
        assert "already in checkout" in exc_info.value.detail

    async def test_midgame_cash_only_full_flow(
        self, settlement_service, player_dal, open_game_with_cash_player
    ):
        """Cash-only player: request -> submit -> validate -> DONE (fast path)."""
        game_id = open_game_with_cash_player["game_id"]
        bob_token = open_game_with_cash_player["bob_token"]

        # Step 1: Request mid-game checkout
        await settlement_service.request_midgame_checkout(game_id, bob_token)

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.PENDING

        # Step 2: Submit chips (Bob has 100 buy-in, submitting 120 = profit of 20)
        await settlement_service.submit_chips(
            game_id, bob_token,
            chip_count=120, preferred_cash=120, preferred_credit=0,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.SUBMITTED

        # Step 3: Validate chips — cash-only fast path should go straight to DONE
        await settlement_service.validate_chips(game_id, bob_token)

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.DONE
        assert player.checked_out is True
        assert player.validated_chip_count == 120
        assert player.distribution == {"cash": 120, "credit_from": []}
