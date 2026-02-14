"""Unit tests for SettlementService chip submission, validation, rejection, and manager input."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import CheckoutStatus, GameStatus, RequestType
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
async def settling_game(game_service, request_service, settlement_service):
    """Create a settling game with Alice (manager, 200 cash) and Bob (100 cash + 100 credit).

    All requests are approved, then start_settling is called.
    Returns game_id, manager_token, bob_token.
    """
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

    # Bob buys in 100 cash
    bob_cash_req = await request_service.create_request(
        game_id=game_id, player_token=bob_token,
        request_type=RequestType.CASH, amount=100,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(bob_cash_req.id),
        manager_token=manager_token,
    )

    # Bob buys in 100 credit
    bob_credit_req = await request_service.create_request(
        game_id=game_id, player_token=bob_token,
        request_type=RequestType.CREDIT, amount=100,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(bob_credit_req.id),
        manager_token=manager_token,
    )

    # Start settling
    await settlement_service.start_settling(game_id)

    return {
        "game_id": game_id,
        "manager_token": manager_token,
        "bob_token": bob_token,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSubmitChips:

    async def test_player_submits_chips(
        self, settlement_service, player_dal, settling_game
    ):
        """Submit auto-validates: Bob (credit player) goes to CREDIT_DEDUCTED, fields saved."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=100,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert player.submitted_chip_count == 200
        assert player.preferred_cash == 100
        assert player.preferred_credit == 100
        assert player.validated_chip_count == 200

    async def test_submit_fails_if_locked(
        self, settlement_service, player_dal, settling_game
    ):
        """400 if manager locked input."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        # Lock the player
        await player_dal.update_by_token(game_id, bob_token, {"input_locked": True})

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.submit_chips(
                game_id=game_id,
                player_token=bob_token,
                chip_count=200,
                preferred_cash=100,
                preferred_credit=100,
            )
        assert exc_info.value.status_code == 400

    async def test_submit_fails_if_not_pending(
        self, settlement_service, player_dal, settling_game
    ):
        """400 if not in PENDING state."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        # Move to SUBMITTED first
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=100,
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.submit_chips(
                game_id=game_id,
                player_token=bob_token,
                chip_count=200,
                preferred_cash=100,
                preferred_credit=100,
            )
        assert exc_info.value.status_code == 400


class TestSubmitAutoValidates:

    async def test_cash_only_submit_goes_straight_to_done(
        self, settlement_service, player_dal, game_dal, settling_game
    ):
        """Cash-only player submitting chips should auto-validate to DONE."""
        game_id = settling_game["game_id"]
        manager_token = settling_game["manager_token"]

        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=manager_token,
            chip_count=250,
            preferred_cash=250,
            preferred_credit=0,
        )

        player = await player_dal.get_by_token(game_id, manager_token)
        assert player.checkout_status == CheckoutStatus.DONE
        assert player.checked_out is True
        assert player.validated_chip_count == 250
        assert player.distribution == {"cash": 250, "credit_from": []}

    async def test_credit_player_submit_goes_to_credit_deducted(
        self, settlement_service, player_dal, settling_game
    ):
        """Player with credit submitting chips should auto-validate to CREDIT_DEDUCTED."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=0,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert player.validated_chip_count == 200
        assert player.credit_repaid == 100
        assert player.chips_after_credit == 100

    async def test_all_players_done_updates_settlement_state(
        self, settlement_service, player_dal, game_dal, settling_game
    ):
        """When all players reach DONE after submit, settlement_state should update."""
        game_id = settling_game["game_id"]
        manager_token = settling_game["manager_token"]
        bob_token = settling_game["bob_token"]

        # Alice (cash-only) submits → auto-validates to DONE
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=manager_token,
            chip_count=250,
            preferred_cash=250,
            preferred_credit=0,
        )

        # Bob (has credit) submits → auto-validates to CREDIT_DEDUCTED
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=150,
            preferred_cash=50,
            preferred_credit=0,
        )

        # Bob needs distribution, so not all done yet
        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.CREDIT_DEDUCTED

        # Override distribution for Bob
        await settlement_service.override_distribution(game_id, {
            bob_token: {"cash": 50, "credit_from": []},
        })

        # Confirm Bob
        await settlement_service.confirm_distribution(game_id, bob_token)

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.DONE

        # Now all players are DONE — game should be closeable
        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.SETTLING

        # Close should succeed
        result = await settlement_service.close_game(game_id)
        assert result["status"] == "CLOSED"


class TestValidateChips:

    async def test_submit_auto_validates_credit_math(
        self, settlement_service, player_dal, settling_game
    ):
        """Submit auto-validates: correct math for Bob (100 cash + 100 credit, returning 200 chips)."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        # Bob submits 200 chips — auto-validates
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=100,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert player.validated_chip_count == 200
        # P/L = 200 - (100 + 100) = 0
        assert player.profit_loss == 0
        # credit_repaid = min(200, 100) = 100
        assert player.credit_repaid == 100
        # chips_after_credit = max(0, 200 - 100) = 100
        assert player.chips_after_credit == 100
        # credit_owed = max(0, 100 - 200) = 0
        assert player.credits_owed == 0


class TestRejectChips:

    async def test_manager_rejects_after_auto_validate(
        self, settlement_service, player_dal, settling_game
    ):
        """Reject from CREDIT_DEDUCTED resets to PENDING, all fields cleared."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        # Submit (auto-validates to CREDIT_DEDUCTED)
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=100,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.CREDIT_DEDUCTED

        await settlement_service.reject_chips(game_id, bob_token)

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.PENDING
        assert player.submitted_chip_count is None
        assert player.preferred_cash is None
        assert player.preferred_credit is None
        assert player.validated_chip_count is None


class TestManagerInput:

    async def test_manager_input_locks_player(
        self, settlement_service, player_dal, settling_game
    ):
        """input_locked=True, auto-validates through to CREDIT_DEDUCTED."""
        game_id = settling_game["game_id"]
        bob_token = settling_game["bob_token"]

        await settlement_service.manager_input(
            game_id=game_id,
            player_token=bob_token,
            chip_count=200,
            preferred_cash=100,
            preferred_credit=100,
        )

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.input_locked is True
        assert player.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert player.validated_chip_count == 200
        assert player.credit_repaid == 100
        assert player.chips_after_credit == 100


class TestCashOnlyFastPath:

    async def test_cash_only_player_submit_goes_to_done(
        self, settlement_service, player_dal, game_dal, settling_game
    ):
        """Alice (cash only) submit auto-validates -> DONE, cash_pool decremented."""
        game_id = settling_game["game_id"]
        manager_token = settling_game["manager_token"]

        # Get initial cash_pool
        game_before = await game_dal.get_by_id(game_id)
        initial_cash_pool = game_before.cash_pool

        # Alice submits 250 chips (cash-only player, preferred_credit=0) — auto-validates to DONE
        await settlement_service.submit_chips(
            game_id=game_id,
            player_token=manager_token,
            chip_count=250,
            preferred_cash=250,
            preferred_credit=0,
        )

        player = await player_dal.get_by_token(game_id, manager_token)
        assert player.checkout_status == CheckoutStatus.DONE
        assert player.checked_out is True
        assert player.checked_out_at is not None
        # chips_after_credit = max(0, 250 - 0) = 250
        assert player.chips_after_credit == 250
        assert player.distribution == {"cash": 250, "credit_from": []}

        # cash_pool should be decremented by 250
        game_after = await game_dal.get_by_id(game_id)
        assert game_after.cash_pool == initial_cash_pool - 250
