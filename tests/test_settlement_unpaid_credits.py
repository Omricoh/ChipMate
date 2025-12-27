"""
Test settlement with unpaid credits scenario
Tests the bug where partial credit repayment doesn't show remaining credits as available

Scenario (matching user's bug report):
- PlayerA: buys in 100 cash + 200 credit (300 total), cashes out 0
  -> Owes full 200 credit
- PlayerB: buys in 300 cash + 400 credit (700 total), cashes out 0
  -> Owes full 400 credit
- PlayerC: buys in 100 cash
- Settlement Phase 1: PlayerA repays 100 credit (partial - still owes 100)
- Expected in Phase 2:
  - 500 cash available (100+300+100 in, 0 out)
  - PlayerA has 100 unpaid credit (200 - 100 repaid)
  - PlayerB has 400 unpaid credit

Uses mongomock for in-memory testing without requiring MongoDB
"""
import os
import sys
# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock
from datetime import datetime, timezone

# Create a single shared mock client that all services will use
shared_mock_client = mongomock.MongoClient()

# Mock pymongo.MongoClient before importing services to always return the same instance
import pymongo
original_client = pymongo.MongoClient
pymongo.MongoClient = lambda *args, **kwargs: shared_mock_client

from src.services.transaction_service import TransactionService
from src.services.player_service import PlayerService
from src.services.game_service import GameService
from src.services.settlement_service import SettlementService
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.bank_dal import BankDAL
from src.dal.unpaid_credits_dal import UnpaidCreditsDAL

# Use mongomock instead of real MongoDB
MONGO_URL = "mongodb://localhost:27017/"
client = shared_mock_client
db = client.chipbot

# Initialize services with mock MongoDB
transaction_service = TransactionService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
game_service = GameService(MONGO_URL)
settlement_service = SettlementService(MONGO_URL)
games_dal = GamesDAL(db)
players_dal = PlayersDAL(db)
transactions_dal = TransactionsDAL(db)
bank_dal = BankDAL(db)
unpaid_credits_dal = UnpaidCreditsDAL(db)

def setup_test_game():
    """Create test game with players A, B, C and their transactions"""
    # Clear database
    db.games.delete_many({})
    db.players.delete_many({})
    db.transactions.delete_many({})
    db.bank.delete_many({})
    db.unpaid_credits.delete_many({})

    # Create game with host (Player A)
    player_a_id = 1001
    game_id, game_code = game_service.create_game(player_a_id, "PlayerA")

    # Player B joins
    player_b_id = 1002
    game_service.join_game(game_code, player_b_id, "PlayerB")

    # Player C joins
    player_c_id = 1003
    game_service.join_game(game_code, player_c_id, "PlayerC")

    print(f"\n{'='*60}")
    print(f"Created game {game_code} (ID: {game_id})")
    print(f"{'='*60}\n")

    return game_id, player_a_id, player_b_id, player_c_id

def test_settlement_unpaid_credits():
    """Test the settlement unpaid credits scenario"""

    game_id, player_a_id, player_b_id, player_c_id = setup_test_game()

    print("STEP 1: Buy-ins")
    print("-" * 60)

    # PlayerA: 100 cash + 200 credit
    print("PlayerA buys in 100 cash...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerA cash buy-in approved")

    print("PlayerA buys in 200 credit...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "register", 200)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerA credit buy-in approved")

    # PlayerB: 300 cash + 400 credit
    print("\nPlayerB buys in 300 cash...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "cash", 300)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerB cash buy-in approved")

    print("PlayerB buys in 400 credit...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "register", 400)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerB credit buy-in approved")

    # PlayerC: 100 cash
    print("\nPlayerC buys in 100 cash...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_c_id, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerC cash buy-in approved")

    print("\n" + "STEP 2: Cashouts")
    print("-" * 60)

    # PlayerB cashes out for 0
    print("PlayerB cashes out 0 chips...")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_b_id, 0)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerB cashout approved")

    # PlayerA cashes out for 0
    print("\nPlayerA cashes out 0 chips...")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 0)
    transaction_service.approve_transaction(tx_id)
    print("[OK] PlayerA cashout approved")

    print("\n" + "STEP 3: Check Credits Owed")
    print("-" * 60)

    player_a = players_dal.get_player(game_id, player_a_id)
    player_b = players_dal.get_player(game_id, player_b_id)
    player_c = players_dal.get_player(game_id, player_c_id)

    print(f"PlayerA credits_owed: {player_a.credits_owed}")
    print(f"PlayerB credits_owed: {player_b.credits_owed}")
    print(f"PlayerC credits_owed: {player_c.credits_owed}")

    bank = bank_dal.get_by_game(game_id)
    print(f"\nBank cash_balance: {bank.cash_balance}")
    print(f"Bank outstanding credits: {bank.total_credits_issued - bank.total_credits_repaid}")

    print("\n" + "STEP 4: Start Settlement")
    print("-" * 60)

    result = settlement_service.start_settlement(game_id)
    print(f"Settlement started: {result['message']}")
    print(f"Players with credits: {len(result['players_with_credits'])}")
    for p in result['players_with_credits']:
        print(f"  - {p['name']}: {p['credits_owed']} owed")

    print("\n" + "STEP 5: PlayerA Repays 100 Credit")
    print("-" * 60)

    result = settlement_service.repay_credit(game_id, player_a_id, 100)
    print(f"Repayment result: {result['message']}")
    print(f"Credits repaid: {result['credits_repaid']}")
    print(f"Remaining credits: {result['remaining_credits']}")

    # Check unpaid credit was created
    unpaid_a = unpaid_credits_dal.get_by_debtor(game_id, player_a_id)
    if unpaid_a:
        print(f"[OK] UnpaidCredit created for PlayerA: {unpaid_a.amount} (available: {unpaid_a.amount_available})")
    else:
        print("[ERROR] No UnpaidCredit found for PlayerA!")

    print("\n" + "STEP 6: Complete Credit Settlement (Move to Phase 2)")
    print("-" * 60)

    result = settlement_service.complete_credit_settlement(game_id)
    print(f"Phase 2 started: {result['message']}")
    print(f"Available cash: {result['available_cash']}")
    print(f"Unpaid credits: {len(result['unpaid_credits'])}")
    for uc in result['unpaid_credits']:
        print(f"  - {uc['debtor_name']}: {uc['amount_available']} available")

    print("\n" + "STEP 7: Verify Final State")
    print("-" * 60)

    # Get settlement status
    status = settlement_service.get_settlement_status(game_id)

    print(f"Settlement phase: {status['phase']}")
    print(f"Available cash: {status['available_cash']}")

    # Expected: 500 cash (100+300+100 in, 0 out)
    expected_cash = 500

    # Expected unpaid credits:
    # - PlayerA: 100 (200 owed - 100 repaid = 100 remaining) <- THIS IS THE BUG TEST
    # - PlayerB: 400 (400 credit buyin, cashed out 0)
    expected_unpaid_credits = {
        'PlayerA': 100,
        'PlayerB': 400
    }

    print(f"\n{'='*60}")
    print("TEST RESULTS")
    print(f"{'='*60}")

    # Verify cash
    actual_cash = status['available_cash']
    if actual_cash == expected_cash:
        print(f"[PASS] Cash available: {actual_cash} (expected {expected_cash})")
    else:
        print(f"[FAIL] Cash available: {actual_cash} (expected {expected_cash})")

    # Verify unpaid credits
    actual_unpaid = {uc['debtor_name']: uc['amount_available'] for uc in status['unpaid_credits']}

    all_passed = True
    for name, expected_amount in expected_unpaid_credits.items():
        actual_amount = actual_unpaid.get(name, 0)
        if actual_amount == expected_amount:
            print(f"[PASS] {name} unpaid credit: {actual_amount} (expected {expected_amount})")
        else:
            print(f"[FAIL] {name} unpaid credit: {actual_amount} (expected {expected_amount})")
            all_passed = False

    # Check for unexpected unpaid credits
    for name, amount in actual_unpaid.items():
        if name not in expected_unpaid_credits:
            print(f"[FAIL] Unexpected unpaid credit for {name}: {amount}")
            all_passed = False

    print(f"{'='*60}\n")

    if all_passed and actual_cash == expected_cash:
        print("ALL TESTS PASSED!")
        return True
    else:
        print("SOME TESTS FAILED!")
        return False

if __name__ == "__main__":
    success = test_settlement_unpaid_credits()
    sys.exit(0 if success else 1)
