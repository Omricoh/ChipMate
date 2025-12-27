"""
Test the specific bug: Players who cash out BEFORE settlement starts
should have their unpaid credits show up in Phase 2

Scenario (matching production bug):
- Rendy: buys in 100 cash + 200 credit, cashes out 100 chips BEFORE settlement
  -> Cashout repays 100 credit, Rendy still owes 100 credit
- שולי: buys in 300 cash + 400 credit, hasn't cashed out yet
- omri: buys in 100 cash

Settlement starts:
- Phase 1: Rendy's 100 remaining credit should already be in UnpaidCredit
- Phase 2: Both Rendy's 100 and שולי's 400 should show as unpaid credits

Uses mongomock for in-memory testing without requiring MongoDB
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock
from datetime import datetime, timezone

shared_mock_client = mongomock.MongoClient()

import pymongo
original_client = pymongo.MongoClient
pymongo.MongoClient = lambda *args, **kwargs: shared_mock_client

from src.services.transaction_service import TransactionService
from src.services.game_service import GameService
from src.services.settlement_service import SettlementService
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.bank_dal import BankDAL
from src.dal.unpaid_credits_dal import UnpaidCreditsDAL

MONGO_URL = "mongodb://localhost:27017/"
client = shared_mock_client
db = client.chipbot

transaction_service = TransactionService(MONGO_URL)
game_service = GameService(MONGO_URL)
settlement_service = SettlementService(MONGO_URL)
games_dal = GamesDAL(db)
players_dal = PlayersDAL(db)
bank_dal = BankDAL(db)
unpaid_credits_dal = UnpaidCreditsDAL(db)

def setup_test_game():
    """Create test game matching production scenario"""
    db.games.delete_many({})
    db.players.delete_many({})
    db.transactions.delete_many({})
    db.bank.delete_many({})
    db.unpaid_credits.delete_many({})

    omri_id = 1001
    game_id, game_code = game_service.create_game(omri_id, "omri")

    shuli_id = 1002
    game_service.join_game(game_code, shuli_id, "shuli")

    rendy_id = 1003
    game_service.join_game(game_code, rendy_id, "Rendy")

    print(f"\n{'='*60}")
    print(f"Created game {game_code} (ID: {game_id})")
    print(f"{'='*60}\n")

    return game_id, omri_id, shuli_id, rendy_id

def test_settlement_prior_cashout():
    """Test that players who cashed out before settlement have unpaid credits visible"""

    game_id, omri_id, shuli_id, rendy_id = setup_test_game()

    print("STEP 1: Buy-ins")
    print("-" * 60)

    # omri: 100 cash
    tx_id = transaction_service.create_buyin_transaction(game_id, omri_id, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    print("[OK] omri: 100 cash")

    # shuli: 300 cash + 400 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, shuli_id, "cash", 300)
    transaction_service.approve_transaction(tx_id)
    print("[OK] shuli: 300 cash")

    tx_id = transaction_service.create_buyin_transaction(game_id, shuli_id, "register", 400)
    transaction_service.approve_transaction(tx_id)
    print("[OK] shuli: 400 credit")

    # Rendy: 100 cash + 200 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, rendy_id, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    print("[OK] Rendy: 100 cash")

    tx_id = transaction_service.create_buyin_transaction(game_id, rendy_id, "register", 200)
    transaction_service.approve_transaction(tx_id)
    print("[OK] Rendy: 200 credit")

    print("\n" + "STEP 2: Rendy cashes out BEFORE settlement")
    print("-" * 60)

    # Rendy cashes out 100 chips - should repay 100 credit, still owe 100
    tx_id = transaction_service.create_cashout_transaction(game_id, rendy_id, 100)
    transaction_service.approve_transaction(tx_id)
    print("[OK] Rendy cashed out 100 chips")

    rendy = players_dal.get_player(game_id, rendy_id)
    print(f"Rendy now owes: {rendy.credits_owed} credits")

    # Verify no UnpaidCredit exists yet (before settlement)
    unpaid = unpaid_credits_dal.get_by_debtor(game_id, rendy_id)
    if unpaid:
        print(f"[UNEXPECTED] UnpaidCredit exists before settlement: {unpaid.amount}")
    else:
        print("[OK] No UnpaidCredit record yet (expected before settlement)")

    print("\n" + "STEP 3: Start Settlement")
    print("-" * 60)

    result = settlement_service.start_settlement(game_id)
    print(f"Settlement started: {result['message']}")

    # NOW check if Rendy's UnpaidCredit was created
    unpaid = unpaid_credits_dal.get_by_debtor(game_id, rendy_id)
    if unpaid:
        print(f"[OK] UnpaidCredit created for Rendy during start_settlement: {unpaid.amount} available")
    else:
        print("[FAIL] UnpaidCredit NOT created for Rendy!")

    print("\n" + "STEP 4: Move to Phase 2 (Complete Credit Settlement)")
    print("-" * 60)

    result = settlement_service.complete_credit_settlement(game_id)
    print(f"Phase 2: {result['message']}")
    print(f"Unpaid credits available: {len(result['unpaid_credits'])}")
    for uc in result['unpaid_credits']:
        print(f"  - {uc['debtor_name']}: {uc['amount_available']}")

    print("\n" + "STEP 5: Verify Final State")
    print("-" * 60)

    status = settlement_service.get_settlement_status(game_id)

    expected_unpaid = {
        'Rendy': 100,  # 200 credit - 100 repaid at cashout
        'shuli': 400   # 400 credit - 0 repaid
    }

    actual_unpaid = {uc['debtor_name']: uc['amount_available'] for uc in status['unpaid_credits']}

    print(f"\n{'='*60}")
    print("TEST RESULTS")
    print(f"{'='*60}")

    all_passed = True
    for name, expected_amount in expected_unpaid.items():
        actual_amount = actual_unpaid.get(name, 0)
        if actual_amount == expected_amount:
            print(f"[PASS] {name} unpaid credit: {actual_amount} (expected {expected_amount})")
        else:
            print(f"[FAIL] {name} unpaid credit: {actual_amount} (expected {expected_amount})")
            all_passed = False

    for name, amount in actual_unpaid.items():
        if name not in expected_unpaid:
            print(f"[FAIL] Unexpected unpaid credit for {name}: {amount}")
            all_passed = False

    print(f"{'='*60}\n")

    if all_passed:
        print("ALL TESTS PASSED - Bug is fixed!")
        return True
    else:
        print("TESTS FAILED - Bug still exists!")
        return False

if __name__ == "__main__":
    success = test_settlement_prior_cashout()
    sys.exit(0 if success else 1)
