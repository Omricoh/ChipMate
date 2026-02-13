"""Unit tests for SettlementService.start_settling."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, CheckoutStatus, RequestStatus, RequestType
from app.models.game import Game
from app.models.player import Player
from app.models.chip_request import ChipRequest
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
async def open_game_with_players(game_service, request_service):
    """Create an open game with manager Alice and player Bob, each with approved buy-ins."""
    game_data = await game_service.create_game(manager_name="Alice")
    game_id = game_data["game_id"]
    manager_token = game_data["player_token"]

    # Bob joins
    bob_data = await game_service.join_game(game_id, player_name="Bob")
    bob_token = bob_data["player_token"]

    # Alice buys in 200 cash (create + approve)
    alice_req = await request_service.create_request(
        game_id=game_id, player_token=manager_token,
        request_type=RequestType.CASH, amount=200,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(alice_req.id),
        manager_token=manager_token,
    )

    # Bob buys in 100 cash + 100 credit (create + approve each)
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

class TestStartSettling:

    async def test_start_settling_transitions_game(
        self, settlement_service, game_dal, open_game_with_players
    ):
        game_id = open_game_with_players["game_id"]
        result = await settlement_service.start_settling(game_id)

        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.SETTLING
        assert game.settlement_state == "SETTLING_CHIP_COUNT"
        assert game.frozen_at is not None
        assert game.cash_pool > 0

    async def test_start_settling_freezes_player_buy_ins(
        self, settlement_service, player_dal, open_game_with_players
    ):
        game_id = open_game_with_players["game_id"]
        bob_token = open_game_with_players["bob_token"]

        await settlement_service.start_settling(game_id)

        players = await player_dal.get_by_game(game_id)
        for p in players:
            assert p.checkout_status == CheckoutStatus.PENDING
            assert p.frozen_buy_in is not None
            assert "total_cash_in" in p.frozen_buy_in
            assert "total_credit_in" in p.frozen_buy_in
            assert "total_buy_in" in p.frozen_buy_in

    async def test_start_settling_declines_pending_requests(
        self, settlement_service, request_service, chip_request_dal, open_game_with_players
    ):
        game_id = open_game_with_players["game_id"]
        bob_token = open_game_with_players["bob_token"]

        # Create a pending request that should be auto-declined
        await request_service.create_request(
            game_id=game_id, player_token=bob_token,
            request_type=RequestType.CASH, amount=50,
        )

        # Verify there's a pending request
        pending = await chip_request_dal.get_pending_by_game(game_id)
        assert len(pending) > 0

        await settlement_service.start_settling(game_id)

        # All pending should now be declined
        pending_after = await chip_request_dal.get_pending_by_game(game_id)
        assert len(pending_after) == 0

    async def test_start_settling_fails_if_not_open(
        self, settlement_service, game_dal, open_game_with_players
    ):
        game_id = open_game_with_players["game_id"]

        # First settle it
        await settlement_service.start_settling(game_id)

        # Try again - should fail
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.start_settling(game_id)
        assert exc_info.value.status_code == 400
