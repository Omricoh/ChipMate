"""
Simplified settlement flow test - services only, no Flask
"""
import os
os.environ['MONGO_URL'] = 'mongodb://localhost:27017/'

from src.services.game_service import GameService
from src.services.transaction_service import TransactionService
from src.services.settlement_service import SettlementService
from src.dal.bank_dal import BankDAL
from src.dal.unpaid_credits_dal import UnpaidCreditsDAL
from pymongo import MongoClient

MONGO_URL = "mongodb://localhost:27017/"

print("\n" + "="*70)
print("SETTLEMENT FLOW TEST (Services Only)")
print("="*70)

try:
    # Initialize services
    game_service = GameService(MONGO_URL)
    transaction_service = TransactionService(MONGO_URL)
    settlement_service = SettlementService(MONGO_URL)

    client = MongoClient(MONGO_URL)
    db = client.chipbot
    bank_dal = BankDAL(db)
    unpaid_credits_dal = UnpaidCreditsDAL(db)

    print("\n[OK] Services initialized")

    # Create game
    print("\n[1] Creating game...")
    result = game_service.create_game(host_id=999, host_name="TestHost")
    game_id = result["game"]["id"]
    print(f"[OK] Game: {game_id}")

    # Add players
    print("\n[2] Adding players...")
    game_service.join_game(game_id, 101, "Alice")
    game_service.join_game(game_id, 102, "Bob")
    print("[OK] Players added")

    # Create buyins
    print("\n[3] Creating buyins...")

    # Alice: 200 cash
    transaction_service.create_buyin(game_id, 101, 200, "cash")
    tx_id = list(db.transactions.find({"game_id": game_id, "user_id": 101}).sort("_id", -1).limit(1))[0]["_id"]
    transaction_service.approve_transaction(str(tx_id))
    print("[OK] Alice: 200 cash")

    # Bob: 100 credit
    transaction_service.create_buyin(game_id, 102, 100, "credit")
    tx_id = list(db.transactions.find({"game_id": game_id, "user_id": 102}).sort("_id", -1).limit(1))[0]["_id"]
    transaction_service.approve_transaction(str(tx_id))
    print("[OK] Bob: 100 credit")

    bank = bank_dal.get_by_game(game_id)
    print(f"\nBank: cash={bank.cash_balance}, credits_issued={bank.total_credits_issued}")

    # Start settlement
    print("\n[4] Starting settlement...")
    result = settlement_service.start_settlement(game_id)
    print(f"[OK] Phase: {result['phase']}")
    print(f"  Players with credits: {result['players_with_credits']}")

    # Bob repays 60 (partial - 40 remains unpaid)
    print("\n[5] Bob repays 60 chips (partial)...")
    result = settlement_service.repay_credit(game_id, 102, 60)
    print(f"[OK] {result['message']}")

    # Check unpaid credits
    unpaid = unpaid_credits_dal.get_by_game(game_id)
    print(f"  Unpaid credits: {len(unpaid)}")
    for uc in unpaid:
        print(f"    - {uc.debtor_name}: {uc.amount_available} available")

    # Complete Phase 1
    print("\n[6] Completing Phase 1...")
    result = settlement_service.complete_credit_settlement(game_id)
    print(f"[OK] Phase: {result['phase']}")
    print(f"  Available cash: {result['available_cash']}")
    print(f"  Unpaid credits: {result['unpaid_credits']}")

    # Alice cashes out: 200 cash + 40 from Bob's unpaid credit
    print("\n[7] Alice cashes out 240 chips: 200 cash + 40 credit...")
    result = settlement_service.process_final_cashout(
        game_id,
        101,
        240,
        cash_requested=200,
        unpaid_credits_claimed=[{"debtor_user_id": 102, "amount": 40}]
    )
    print(f"[OK] {result['message']}")

    # Check final state
    bank = bank_dal.get_by_game(game_id)
    unpaid = unpaid_credits_dal.get_available_by_game(game_id)
    total_unpaid = sum(uc.amount_available for uc in unpaid)

    print(f"\n[8] Final state:")
    print(f"  Bank cash: {bank.cash_balance}")
    print(f"  Unpaid credits available: {total_unpaid}")
    print(f"  Can complete: {bank.cash_balance == 0 and total_unpaid == 0}")

    if bank.cash_balance == 0 and total_unpaid == 0:
        result = settlement_service.complete_settlement(game_id)
        print(f"[OK] Settlement completed: {result['message']}")

    print("\n" + "="*70)
    print("TEST PASSED [OK]")
    print("="*70 + "\n")

except Exception as e:
    print(f"\n[FAIL] TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
