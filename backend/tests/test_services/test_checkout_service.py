"""Unit tests for CheckoutService business logic.

Tests cover:
    - checkout_player (profit, loss, break-even, with credits)
    - checkout in SETTLING game (valid)
    - checkout in CLOSED game (400)
    - checkout already checked-out player (400)
    - checkout nonexistent game/player (404)
    - _compute_total_buy_in (only approved/edited, not pending/declined)
    - bank updates after checkout
    - notification created on checkout
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, RequestType
from app.services.checkout_service import CheckoutService
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
async def game_dal(mock_db):
    return GameDAL(mock_db)


@pytest_asyncio.fixture
async def player_dal(mock_db):
    return PlayerDAL(mock_db)


@pytest_asyncio.fixture
async def chip_request_dal(mock_db):
    return ChipRequestDAL(mock_db)


@pytest_asyncio.fixture
async def notification_dal(mock_db):
    return NotificationDAL(mock_db)


@pytest_asyncio.fixture
async def game_service(game_dal, player_dal, chip_request_dal):
    return GameService(game_dal, player_dal, chip_request_dal)


@pytest_asyncio.fixture
async def request_service(game_dal, player_dal, chip_request_dal, notification_dal):
    return RequestService(game_dal, player_dal, chip_request_dal, notification_dal)


@pytest_asyncio.fixture
async def checkout_service(game_dal, player_dal, chip_request_dal, notification_dal):
    return CheckoutService(game_dal, player_dal, chip_request_dal, notification_dal)


@pytest_asyncio.fixture
async def game_with_player(game_service, request_service):
    """Create an OPEN game with Alice (manager) and Bob with 100 CASH buy-in approved."""
    game = await game_service.create_game(manager_name="Alice")
    bob = await game_service.join_game(game["game_id"], "Bob")

    req = await request_service.create_request(
        game["game_id"], bob["player_token"], RequestType.CASH, 100,
    )
    await request_service.approve_request(
        game["game_id"], req.id, game["player_token"],
    )
    return game, bob


# ---------------------------------------------------------------------------
# checkout_player -- happy paths
# ---------------------------------------------------------------------------

class TestCheckoutPlayerHappyPaths:

    @pytest.mark.asyncio
    async def test_checkout_with_profit(
        self, checkout_service, game_with_player
    ):
        game, bob = game_with_player
        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=150,
        )
        assert result["player_id"] == bob["player_token"]
        assert result["player_name"] == "Bob"
        assert result["final_chip_count"] == 150
        assert result["total_buy_in"] == 100
        assert result["profit_loss"] == 50
        assert result["has_debt"] is False
        assert result["checked_out_at"] is not None

    @pytest.mark.asyncio
    async def test_checkout_with_loss(
        self, checkout_service, game_with_player
    ):
        game, bob = game_with_player
        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=30,
        )
        assert result["profit_loss"] == -70
        assert result["total_buy_in"] == 100

    @pytest.mark.asyncio
    async def test_checkout_break_even(
        self, checkout_service, game_with_player
    ):
        game, bob = game_with_player
        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=100,
        )
        assert result["profit_loss"] == 0

    @pytest.mark.asyncio
    async def test_checkout_with_zero_chips(
        self, checkout_service, game_with_player
    ):
        game, bob = game_with_player
        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=0,
        )
        assert result["final_chip_count"] == 0
        assert result["profit_loss"] == -100


# ---------------------------------------------------------------------------
# checkout_player -- credits / debt
# ---------------------------------------------------------------------------

class TestCheckoutWithCredits:

    @pytest.mark.asyncio
    async def test_checkout_with_credit_debt(
        self, checkout_service, game_service, request_service
    ):
        game = await game_service.create_game("Alice")
        bob = await game_service.join_game(game["game_id"], "Bob")

        # Bob buys in 100 on CREDIT
        req = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CREDIT, 100,
        )
        await request_service.approve_request(
            game["game_id"], req.id, game["player_token"],
        )

        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=80,
        )
        assert result["credits_owed"] == 100
        assert result["has_debt"] is True
        assert result["total_buy_in"] == 100
        assert result["profit_loss"] == -20

    @pytest.mark.asyncio
    async def test_checkout_mixed_cash_and_credit(
        self, checkout_service, game_service, request_service
    ):
        game = await game_service.create_game("Alice")
        bob = await game_service.join_game(game["game_id"], "Bob")

        # 100 CASH + 50 CREDIT = 150 total
        cash_req = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CASH, 100,
        )
        await request_service.approve_request(
            game["game_id"], cash_req.id, game["player_token"],
        )
        credit_req = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CREDIT, 50,
        )
        await request_service.approve_request(
            game["game_id"], credit_req.id, game["player_token"],
        )

        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=200,
        )
        assert result["total_buy_in"] == 150
        assert result["profit_loss"] == 50
        assert result["credits_owed"] == 50
        assert result["has_debt"] is True


# ---------------------------------------------------------------------------
# checkout_player -- settling game
# ---------------------------------------------------------------------------

class TestCheckoutInSettlingGame:

    @pytest.mark.asyncio
    async def test_checkout_in_settling_game_succeeds(
        self, checkout_service, game_dal, game_with_player
    ):
        game, bob = game_with_player
        await game_dal.update_status(game["game_id"], GameStatus.SETTLING)

        result = await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=80,
        )
        assert result["final_chip_count"] == 80


# ---------------------------------------------------------------------------
# checkout_player -- error cases
# ---------------------------------------------------------------------------

class TestCheckoutErrorCases:

    @pytest.mark.asyncio
    async def test_checkout_closed_game_raises_400(
        self, checkout_service, game_dal, game_with_player
    ):
        from fastapi import HTTPException
        from datetime import datetime, timezone

        game, bob = game_with_player
        await game_dal.update_status(
            game["game_id"], GameStatus.CLOSED,
            closed_at=datetime.now(timezone.utc),
        )

        with pytest.raises(HTTPException) as exc_info:
            await checkout_service.checkout_player(
                game["game_id"], bob["player_token"], final_chip_count=80,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_already_checked_out_raises_400(
        self, checkout_service, game_with_player
    ):
        from fastapi import HTTPException

        game, bob = game_with_player
        await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=80,
        )

        with pytest.raises(HTTPException) as exc_info:
            await checkout_service.checkout_player(
                game["game_id"], bob["player_token"], final_chip_count=80,
            )
        assert exc_info.value.status_code == 400
        assert "already checked out" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_game_raises_404(
        self, checkout_service
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await checkout_service.checkout_player(
                "000000000000000000000000",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                final_chip_count=0,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_player_raises_404(
        self, checkout_service, game_with_player
    ):
        from fastapi import HTTPException

        game, _ = game_with_player
        with pytest.raises(HTTPException) as exc_info:
            await checkout_service.checkout_player(
                game["game_id"],
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                final_chip_count=0,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# _compute_total_buy_in -- only counts APPROVED and EDITED
# ---------------------------------------------------------------------------

class TestComputeTotalBuyIn:

    @pytest.mark.asyncio
    async def test_declined_and_pending_not_counted(
        self, checkout_service, game_service, request_service
    ):
        game = await game_service.create_game("Alice")
        bob = await game_service.join_game(game["game_id"], "Bob")

        # Approved 100
        req1 = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CASH, 100,
        )
        await request_service.approve_request(
            game["game_id"], req1.id, game["player_token"],
        )

        # Declined 200 -- should NOT count
        req2 = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CASH, 200,
        )
        await request_service.decline_request(
            game["game_id"], req2.id, game["player_token"],
        )

        # Pending 300 -- should NOT count
        await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CASH, 300,
        )

        totals = await checkout_service._compute_total_buy_in(
            game["game_id"], bob["player_token"],
        )
        assert totals["total_buy_in"] == 100

    @pytest.mark.asyncio
    async def test_edited_request_uses_edited_amount(
        self, checkout_service, game_service, request_service
    ):
        game = await game_service.create_game("Alice")
        bob = await game_service.join_game(game["game_id"], "Bob")

        req = await request_service.create_request(
            game["game_id"], bob["player_token"], RequestType.CASH, 100,
        )
        await request_service.edit_and_approve_request(
            game["game_id"], req.id, new_amount=75,
            new_type=None,
            manager_token=game["player_token"],
        )

        totals = await checkout_service._compute_total_buy_in(
            game["game_id"], bob["player_token"],
        )
        # Should use the edited amount (75), not original (100)
        assert totals["total_buy_in"] == 75


# ---------------------------------------------------------------------------
# Bank updates after checkout
# ---------------------------------------------------------------------------

class TestBankUpdatesAfterCheckout:

    @pytest.mark.asyncio
    async def test_bank_chips_in_play_decremented(
        self, checkout_service, game_dal, game_with_player
    ):
        game, bob = game_with_player

        # Before checkout: chips_in_play should be 100 (from approved buy-in)
        game_before = await game_dal.get_by_id(game["game_id"])
        assert game_before.bank.chips_in_play == 100

        await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=80,
        )

        game_after = await game_dal.get_by_id(game["game_id"])
        # chips_in_play decremented by total_buy_in (100)
        assert game_after.bank.chips_in_play == 0
        # total_chips_returned incremented by final_chip_count (80)
        assert game_after.bank.total_chips_returned == 80


# ---------------------------------------------------------------------------
# Notification created on checkout
# ---------------------------------------------------------------------------

class TestCheckoutNotification:

    @pytest.mark.asyncio
    async def test_checkout_creates_notification(
        self, checkout_service, notification_dal, game_with_player
    ):
        game, bob = game_with_player
        await checkout_service.checkout_player(
            game["game_id"], bob["player_token"], final_chip_count=120,
        )

        notifs = await notification_dal.get_unread(
            bob["player_token"], game["game_id"],
        )
        # Should have at least the checkout notification
        # (may also have the request-approved notification)
        checkout_notifs = [
            n for n in notifs
            if "checked out" in n.message.lower()
        ]
        assert len(checkout_notifs) >= 1
