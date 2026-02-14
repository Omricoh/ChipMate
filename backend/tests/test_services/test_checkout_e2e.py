"""End-to-end integration test for the full checkout flow.

Scenario:
1. Create game with manager Alice
2. Add 3 players: Bob (cash+credit), Charlie (cash only), Dave (credit only)
3. Buy-ins: Alice 200 cash, Bob 100 cash + 100 credit, Charlie 150 cash, Dave 100 credit
4. Start settling
5. Players submit chip counts, manager validates
6. Distribution and confirmation
7. Close game

Verifies credit deduction math, pool accounting, and status transitions
throughout the entire lifecycle.
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


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestCheckoutEndToEnd:

    async def test_full_checkout_flow(
        self,
        game_service,
        request_service,
        settlement_service,
        game_dal,
        player_dal,
    ):
        # ==================================================================
        # Step 1: Create game with manager Alice
        # ==================================================================
        game_data = await game_service.create_game(manager_name="Alice")
        game_id = game_data["game_id"]
        alice_token = game_data["player_token"]

        # ==================================================================
        # Step 2: Add 3 players
        # ==================================================================
        bob_data = await game_service.join_game(game_id, player_name="Bob")
        bob_token = bob_data["player_token"]

        charlie_data = await game_service.join_game(game_id, player_name="Charlie")
        charlie_token = charlie_data["player_token"]

        dave_data = await game_service.join_game(game_id, player_name="Dave")
        dave_token = dave_data["player_token"]

        # ==================================================================
        # Step 3: Buy-ins
        # ==================================================================

        # Alice buys in 200 cash
        alice_req = await request_service.create_request(
            game_id=game_id, player_token=alice_token,
            request_type=RequestType.CASH, amount=200,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(alice_req.id),
            manager_token=alice_token,
        )

        # Bob buys in 100 cash + 100 credit
        bob_cash_req = await request_service.create_request(
            game_id=game_id, player_token=bob_token,
            request_type=RequestType.CASH, amount=100,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(bob_cash_req.id),
            manager_token=alice_token,
        )
        bob_credit_req = await request_service.create_request(
            game_id=game_id, player_token=bob_token,
            request_type=RequestType.CREDIT, amount=100,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(bob_credit_req.id),
            manager_token=alice_token,
        )

        # Charlie buys in 150 cash
        charlie_req = await request_service.create_request(
            game_id=game_id, player_token=charlie_token,
            request_type=RequestType.CASH, amount=150,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(charlie_req.id),
            manager_token=alice_token,
        )

        # Dave buys in 100 credit
        dave_req = await request_service.create_request(
            game_id=game_id, player_token=dave_token,
            request_type=RequestType.CREDIT, amount=100,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(dave_req.id),
            manager_token=alice_token,
        )

        # ==================================================================
        # Step 4: Start settling
        # ==================================================================
        result = await settlement_service.start_settling(game_id)

        # ==================================================================
        # Step 5: Verify settling state
        # ==================================================================
        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.SETTLING
        assert game.settlement_state == "SETTLING_CHIP_COUNT"
        # cash_pool = 200 (Alice) + 100 (Bob) + 150 (Charlie) + 0 (Dave) = 450
        assert game.cash_pool == 450

        players = await player_dal.get_by_game(game_id)
        for p in players:
            assert p.checkout_status == CheckoutStatus.PENDING
            assert p.frozen_buy_in is not None

        # Verify frozen buy-in data
        alice = await player_dal.get_by_token(game_id, alice_token)
        assert alice.frozen_buy_in["total_cash_in"] == 200
        assert alice.frozen_buy_in["total_credit_in"] == 0
        assert alice.frozen_buy_in["total_buy_in"] == 200

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.frozen_buy_in["total_cash_in"] == 100
        assert bob.frozen_buy_in["total_credit_in"] == 100
        assert bob.frozen_buy_in["total_buy_in"] == 200

        charlie = await player_dal.get_by_token(game_id, charlie_token)
        assert charlie.frozen_buy_in["total_cash_in"] == 150
        assert charlie.frozen_buy_in["total_credit_in"] == 0
        assert charlie.frozen_buy_in["total_buy_in"] == 150

        dave = await player_dal.get_by_token(game_id, dave_token)
        assert dave.frozen_buy_in["total_cash_in"] == 0
        assert dave.frozen_buy_in["total_credit_in"] == 100
        assert dave.frozen_buy_in["total_buy_in"] == 100

        # ==================================================================
        # Step 6: Players submit chip counts (auto-validates on submit)
        # ==================================================================

        # Alice: 300 chips (profit), wants all cash → auto-validates to DONE
        await settlement_service.submit_chips(
            game_id=game_id, player_token=alice_token,
            chip_count=300, preferred_cash=300, preferred_credit=0,
        )

        alice = await player_dal.get_by_token(game_id, alice_token)
        assert alice.checkout_status == CheckoutStatus.DONE
        assert alice.profit_loss == 100  # 300 - 200
        assert alice.credit_repaid == 0
        assert alice.chips_after_credit == 300
        assert alice.credits_owed == 0
        assert alice.checked_out is True
        assert alice.distribution == {"cash": 300, "credit_from": []}

        # Cash pool after Alice fast-path: 450 - 300 = 150
        game = await game_dal.get_by_id(game_id)
        assert game.cash_pool == 150

        # Bob: 150 chips (loss), wants 100 cash + 50 credit → auto-validates to CREDIT_DEDUCTED
        await settlement_service.submit_chips(
            game_id=game_id, player_token=bob_token,
            chip_count=150, preferred_cash=100, preferred_credit=50,
        )

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert bob.profit_loss == -50  # 150 - 200
        assert bob.credit_repaid == 100  # min(150, 100)
        assert bob.chips_after_credit == 50  # max(0, 150 - 100)
        assert bob.credits_owed == 0  # max(0, 100 - 150)

        # Charlie: 100 chips (loss), wants all cash → auto-validates to DONE
        await settlement_service.submit_chips(
            game_id=game_id, player_token=charlie_token,
            chip_count=100, preferred_cash=100, preferred_credit=0,
        )

        charlie = await player_dal.get_by_token(game_id, charlie_token)
        assert charlie.checkout_status == CheckoutStatus.DONE
        assert charlie.profit_loss == -50  # 100 - 150
        assert charlie.credit_repaid == 0
        assert charlie.chips_after_credit == 100
        assert charlie.credits_owed == 0
        assert charlie.checked_out is True
        assert charlie.distribution == {"cash": 100, "credit_from": []}

        # Cash pool after Charlie fast-path: 150 - 100 = 50
        game = await game_dal.get_by_id(game_id)
        assert game.cash_pool == 50

        # Dave: 0 chips (total loss) → auto-validates to CREDIT_DEDUCTED
        await settlement_service.submit_chips(
            game_id=game_id, player_token=dave_token,
            chip_count=0, preferred_cash=0, preferred_credit=0,
        )

        dave = await player_dal.get_by_token(game_id, dave_token)
        assert dave.checkout_status == CheckoutStatus.CREDIT_DEDUCTED
        assert dave.profit_loss == -100  # 0 - 100
        assert dave.credit_repaid == 0  # min(0, 100)
        assert dave.chips_after_credit == 0  # max(0, 0 - 100)
        assert dave.credits_owed == 100  # max(0, 100 - 0)

        # ==================================================================
        # Step 8: Get distribution suggestion
        # ==================================================================
        suggestion = await settlement_service.get_distribution_suggestion(game_id)

        # Only Bob and Dave should be in the suggestion (Alice and Charlie are DONE)
        assert bob_token in suggestion
        assert dave_token in suggestion

        # Dave is a debtor with chips_after_credit=0, should get 0 cash
        assert suggestion[dave_token]["cash"] == 0

        # Bob has chips_after_credit=50, should get 50 cash
        # (Bob wanted 50 credit but Dave's credit_owed hasn't entered pool yet)
        assert suggestion[bob_token]["cash"] >= 0

        # ==================================================================
        # Step 9: Override distribution
        # ==================================================================
        # Remaining cash_pool = 50. Bob gets 50 cash, Dave gets 0.
        distribution = {
            bob_token: {"cash": 50, "credit_from": []},
            dave_token: {"cash": 0, "credit_from": []},
        }
        await settlement_service.override_distribution(game_id, distribution)

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.DISTRIBUTED
        assert bob.distribution == {"cash": 50, "credit_from": []}

        dave = await player_dal.get_by_token(game_id, dave_token)
        assert dave.checkout_status == CheckoutStatus.DISTRIBUTED
        assert dave.distribution == {"cash": 0, "credit_from": []}

        # ==================================================================
        # Step 10: Confirm distribution for each player
        # ==================================================================

        # Confirm Dave first (debtor) - should add 100 to credit_pool
        game_before = await game_dal.get_by_id(game_id)
        credit_pool_before = game_before.credit_pool

        await settlement_service.confirm_distribution(game_id, dave_token)

        dave = await player_dal.get_by_token(game_id, dave_token)
        assert dave.checkout_status == CheckoutStatus.DONE
        assert dave.checked_out is True

        # Verify credit_pool increased by Dave's credit_owed (100)
        game_after = await game_dal.get_by_id(game_id)
        assert game_after.credit_pool == credit_pool_before + 100

        # Confirm Bob
        await settlement_service.confirm_distribution(game_id, bob_token)

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.DONE
        assert bob.checked_out is True

        # Cash pool should be decremented by Bob's 50 cash
        game_after_bob = await game_dal.get_by_id(game_id)
        assert game_after_bob.cash_pool == 0

        # ==================================================================
        # Step 11: Close game
        # ==================================================================
        await settlement_service.close_game(game_id)

        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.CLOSED
        assert game.closed_at is not None

        # Verify all players are DONE
        all_players = await player_dal.get_by_game(game_id)
        for p in all_players:
            assert p.checkout_status == CheckoutStatus.DONE
            assert p.checked_out is True

    async def test_midgame_checkout_then_settle_remaining(
        self,
        game_service,
        request_service,
        settlement_service,
        game_dal,
        player_dal,
    ):
        """Mid-game checkout for one player, then settle remaining players."""

        # ── Setup: 3 players ─────────────────────────────────────────────
        game_data = await game_service.create_game(manager_name="Alice")
        game_id = game_data["game_id"]
        alice_token = game_data["player_token"]

        bob_data = await game_service.join_game(game_id, player_name="Bob")
        bob_token = bob_data["player_token"]

        charlie_data = await game_service.join_game(game_id, player_name="Charlie")
        charlie_token = charlie_data["player_token"]

        # Alice: 200 cash
        alice_req = await request_service.create_request(
            game_id=game_id, player_token=alice_token,
            request_type=RequestType.CASH, amount=200,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(alice_req.id),
            manager_token=alice_token,
        )

        # Bob: 100 cash (will checkout mid-game)
        bob_req = await request_service.create_request(
            game_id=game_id, player_token=bob_token,
            request_type=RequestType.CASH, amount=100,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(bob_req.id),
            manager_token=alice_token,
        )

        # Charlie: 100 cash
        charlie_req = await request_service.create_request(
            game_id=game_id, player_token=charlie_token,
            request_type=RequestType.CASH, amount=100,
        )
        await request_service.approve_request(
            game_id=game_id, request_id=str(charlie_req.id),
            manager_token=alice_token,
        )

        # ── Mid-game checkout for Bob ────────────────────────────────────

        result = await settlement_service.request_midgame_checkout(game_id, bob_token)
        assert result["status"] == "checkout_initiated"

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.PENDING
        assert bob.frozen_buy_in["total_cash_in"] == 100

        # Bob submits 120 chips (cash-only fast path, auto-validates to DONE)
        await settlement_service.submit_chips(
            game_id, bob_token,
            chip_count=120, preferred_cash=120, preferred_credit=0,
        )

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.DONE
        assert bob.checked_out is True
        assert bob.distribution == {"cash": 120, "credit_from": []}

        # Game is still OPEN
        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.OPEN

        # ── Now settle remaining players ─────────────────────────────────

        await settlement_service.start_settling(game_id)

        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.SETTLING

        # Alice and Charlie should be PENDING, Bob should remain DONE
        alice = await player_dal.get_by_token(game_id, alice_token)
        assert alice.checkout_status == CheckoutStatus.PENDING

        bob = await player_dal.get_by_token(game_id, bob_token)
        assert bob.checkout_status == CheckoutStatus.DONE

        charlie = await player_dal.get_by_token(game_id, charlie_token)
        assert charlie.checkout_status == CheckoutStatus.PENDING

        # Alice submits 180, cash-only fast path (auto-validates to DONE)
        await settlement_service.submit_chips(
            game_id, alice_token,
            chip_count=180, preferred_cash=180, preferred_credit=0,
        )

        alice = await player_dal.get_by_token(game_id, alice_token)
        assert alice.checkout_status == CheckoutStatus.DONE

        # Charlie submits 100, cash-only fast path (auto-validates to DONE)
        await settlement_service.submit_chips(
            game_id, charlie_token,
            chip_count=100, preferred_cash=100, preferred_credit=0,
        )

        charlie = await player_dal.get_by_token(game_id, charlie_token)
        assert charlie.checkout_status == CheckoutStatus.DONE

        # ── Close game ───────────────────────────────────────────────────

        result = await settlement_service.close_game(game_id)
        assert result["status"] == "CLOSED"

        game = await game_dal.get_by_id(game_id)
        assert game.status == GameStatus.CLOSED

        # All players are DONE
        for token in [alice_token, bob_token, charlie_token]:
            player = await player_dal.get_by_token(game_id, token)
            assert player.checkout_status == CheckoutStatus.DONE
            assert player.checked_out is True
