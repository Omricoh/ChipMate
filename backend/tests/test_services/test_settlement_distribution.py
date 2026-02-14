"""Unit tests for SettlementService distribution, confirm, actions, and close game."""

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
async def credit_deducted_game(game_service, request_service, settlement_service):
    """Create a settling game with players in CREDIT_DEDUCTED status.

    Setup:
    - Alice (manager): 200 cash buy-in, submits 250 chips, preferred_cash=150, preferred_credit=100
    - Bob: 100 cash + 100 credit buy-in, submits 150 chips, preferred_cash=50, preferred_credit=0
      Bob has credit_owed = 0 (150 >= 100), chips_after_credit = 50
    - Charlie: 50 cash + 150 credit, submits 100 chips, preferred_cash=0, preferred_credit=0
      Charlie has credit_owed = 50 (150 - 100), chips_after_credit = 0

    Cash pool = 200 + 100 + 50 = 350
    Credit pool = 0 (no debtors confirmed yet)
    """
    game_data = await game_service.create_game(manager_name="Alice")
    game_id = game_data["game_id"]
    manager_token = game_data["player_token"]

    # Bob joins
    bob_data = await game_service.join_game(game_id, player_name="Bob")
    bob_token = bob_data["player_token"]

    # Charlie joins
    charlie_data = await game_service.join_game(game_id, player_name="Charlie")
    charlie_token = charlie_data["player_token"]

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

    # Charlie buys in 50 cash + 150 credit
    charlie_cash_req = await request_service.create_request(
        game_id=game_id, player_token=charlie_token,
        request_type=RequestType.CASH, amount=50,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(charlie_cash_req.id),
        manager_token=manager_token,
    )
    charlie_credit_req = await request_service.create_request(
        game_id=game_id, player_token=charlie_token,
        request_type=RequestType.CREDIT, amount=150,
    )
    await request_service.approve_request(
        game_id=game_id, request_id=str(charlie_credit_req.id),
        manager_token=manager_token,
    )

    # Start settling
    await settlement_service.start_settling(game_id)

    # Alice submits 250 chips (cash-only, preferred_credit > 0 so NOT fast path)
    # Auto-validates to CREDIT_DEDUCTED
    await settlement_service.submit_chips(
        game_id=game_id, player_token=manager_token,
        chip_count=250, preferred_cash=150, preferred_credit=100,
    )

    # Bob submits 150 chips — auto-validates to CREDIT_DEDUCTED
    await settlement_service.submit_chips(
        game_id=game_id, player_token=bob_token,
        chip_count=150, preferred_cash=50, preferred_credit=0,
    )

    # Charlie submits 100 chips (debtor: credit_owed=50, chips_after_credit=0)
    # Auto-validates to CREDIT_DEDUCTED
    await settlement_service.submit_chips(
        game_id=game_id, player_token=charlie_token,
        chip_count=100, preferred_cash=0, preferred_credit=0,
    )

    return {
        "game_id": game_id,
        "manager_token": manager_token,
        "bob_token": bob_token,
        "charlie_token": charlie_token,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetDistribution:

    async def test_get_distribution_returns_suggestion(
        self, settlement_service, credit_deducted_game
    ):
        """Calls algorithm, returns per-player allocation."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        suggestion = await settlement_service.get_distribution_suggestion(game_id)

        # All three players should have entries
        assert manager_token in suggestion
        assert bob_token in suggestion
        assert charlie_token in suggestion

        # Each entry should have cash and credit_from keys
        for token in [manager_token, bob_token, charlie_token]:
            assert "cash" in suggestion[token]
            assert "credit_from" in suggestion[token]

        # Charlie is a debtor with chips_after_credit=0, should get nothing
        assert suggestion[charlie_token]["cash"] == 0


class TestOverrideDistribution:

    async def test_override_distribution_sets_distributed(
        self, settlement_service, player_dal, credit_deducted_game
    ):
        """Manager override sets distribution and status to DISTRIBUTED."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        # Cash pool = 350 (200+100+50). Alice gets 250 cash, Bob gets 50, Charlie gets 0.
        # But wait — total cash must equal cash_pool=350. So 300+50+0=350.
        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }

        await settlement_service.override_distribution(game_id, distribution)

        for token in [manager_token, bob_token, charlie_token]:
            player = await player_dal.get_by_token(game_id, token)
            assert player.checkout_status == CheckoutStatus.DISTRIBUTED
            assert player.distribution is not None


class TestConfirmDistribution:

    async def test_confirm_distribution_marks_done(
        self, settlement_service, player_dal, credit_deducted_game
    ):
        """Player goes DISTRIBUTED -> DONE, checked_out=True."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        await settlement_service.confirm_distribution(game_id, bob_token)

        player = await player_dal.get_by_token(game_id, bob_token)
        assert player.checkout_status == CheckoutStatus.DONE
        assert player.checked_out is True
        assert player.checked_out_at is not None

    async def test_credit_enters_pool_when_debtor_done(
        self, settlement_service, game_dal, player_dal, credit_deducted_game
    ):
        """Debtor reaching DONE adds their credit_owed to credit_pool."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        game_before = await game_dal.get_by_id(game_id)
        credit_pool_before = game_before.credit_pool

        # Charlie is a debtor with credit_owed = 50
        charlie = await player_dal.get_by_token(game_id, charlie_token)
        assert charlie.credits_owed == 50

        await settlement_service.confirm_distribution(game_id, charlie_token)

        game_after = await game_dal.get_by_id(game_id)
        assert game_after.credit_pool == credit_pool_before + 50

    async def test_cash_pool_decremented_on_confirm(
        self, settlement_service, game_dal, credit_deducted_game
    ):
        """Cash pool decremented when player distribution is confirmed."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        game_before = await game_dal.get_by_id(game_id)
        cash_pool_before = game_before.cash_pool

        await settlement_service.confirm_distribution(game_id, bob_token)

        game_after = await game_dal.get_by_id(game_id)
        assert game_after.cash_pool == cash_pool_before - 50


class TestGetPlayerActions:

    async def test_get_player_actions_cash(
        self, settlement_service, credit_deducted_game
    ):
        """Player receiving only cash gets receive_cash action."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        actions = await settlement_service.get_player_actions(game_id, bob_token)
        assert len(actions) == 1
        assert actions[0]["type"] == "receive_cash"
        assert actions[0]["amount"] == 50

    async def test_get_player_actions_credit(
        self, settlement_service, credit_deducted_game
    ):
        """Player receiving credit gets receive_credit actions."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        actions = await settlement_service.get_player_actions(game_id, manager_token)
        # Should have receive_cash and receive_credit
        cash_actions = [a for a in actions if a["type"] == "receive_cash"]
        credit_actions = [a for a in actions if a["type"] == "receive_credit"]
        assert len(cash_actions) == 1
        assert cash_actions[0]["amount"] == 300
        assert len(credit_actions) == 1
        assert credit_actions[0]["from"] == charlie_token
        assert credit_actions[0]["amount"] == 50

    async def test_get_debtor_actions(
        self, settlement_service, credit_deducted_game
    ):
        """Debtor gets pay_credit actions."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        actions = await settlement_service.get_player_actions(game_id, charlie_token)
        pay_actions = [a for a in actions if a["type"] == "pay_credit"]
        assert len(pay_actions) == 1
        assert pay_actions[0]["to"] == manager_token
        assert pay_actions[0]["amount"] == 50


class TestCloseGame:

    async def test_close_game_requires_all_done(
        self, settlement_service, credit_deducted_game
    ):
        """400 if any player not DONE."""
        game_id = credit_deducted_game["game_id"]

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await settlement_service.close_game(game_id)
        assert exc_info.value.status_code == 400

    async def test_close_game_succeeds(
        self, settlement_service, game_dal, credit_deducted_game
    ):
        """Game -> CLOSED, closed_at set when all players are DONE."""
        game_id = credit_deducted_game["game_id"]
        manager_token = credit_deducted_game["manager_token"]
        bob_token = credit_deducted_game["bob_token"]
        charlie_token = credit_deducted_game["charlie_token"]

        distribution = {
            manager_token: {"cash": 300, "credit_from": [{"from": charlie_token, "amount": 50}]},
            bob_token: {"cash": 50, "credit_from": []},
            charlie_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        # Confirm all players
        await settlement_service.confirm_distribution(game_id, charlie_token)
        await settlement_service.confirm_distribution(game_id, bob_token)
        await settlement_service.confirm_distribution(game_id, manager_token)

        await settlement_service.close_game(game_id)

        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.CLOSED
        assert game.closed_at is not None
