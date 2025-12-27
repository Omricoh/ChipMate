"""
VERIFICATION TEST: Settlement Phase Credit Repayment - chips_in_play Update

This test demonstrates that during settlement phase credit repayment,
the bank's chips_in_play is correctly decremented ONLY after the repayment is processed.

Requirement: When a player repays X credits during settlement phase,
the bank must:
1. Decrement chips_in_play by X
2. Increment total_chips_returned by X
3. Increment total_credits_repaid by X

This matches the behavior of regular cashout flow in bank_dal.record_cashout()
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mongomock

# Mock pymongo before importing services
import pymongo
shared_mock_client = mongomock.MongoClient()
pymongo.MongoClient = lambda *args, **kwargs: shared_mock_client

from src.services.transaction_service import TransactionService
from src.services.player_service import PlayerService
from src.services.game_service import GameService
from src.services.settlement_service import SettlementService
from src.dal.bank_dal import BankDAL

# Use mongomock
MONGO_URL = "mongodb://localhost:27017/"
client = shared_mock_client
db = client.chipbot

# Initialize services
transaction_service = TransactionService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
game_service = GameService(MONGO_URL)
settlement_service = SettlementService(MONGO_URL)
bank_dal = BankDAL(db)


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_bank_status(bank, title="Bank Status"):
    """Print detailed bank status"""
    print(f"\n{title}:")
    print("-" * 70)
    print(f"  chips_in_play:         {bank.chips_in_play:>6} chips")
    print(f"  total_chips_issued:    {bank.total_chips_issued:>6} chips")
    print(f"  total_chips_returned:  {bank.total_chips_returned:>6} chips")
    print(f"  total_credits_issued:  {bank.total_credits_issued:>6} credits")
    print(f"  total_credits_repaid:  {bank.total_credits_repaid:>6} credits")
    print(f"  cash_balance:          ${bank.cash_balance:>6}")
    print("-" * 70)


def print_player_status(player_name, credits_owed):
    """Print player credit status"""
    print(f"\n{player_name}'s Credit Status:")
    print("-" * 70)
    print(f"  credits_owed:          {credits_owed:>6} credits")
    print("-" * 70)


def verify_chips_in_play_update():
    """
    VERIFICATION: chips_in_play is correctly decremented during settlement credit repayment
    
    Test Scenario:
    1. Player A: 100 cash + 200 credit buy-in = 300 chips
    2. Player A: Cashes out 0 chips (still owes 200 credits)
    3. Settlement Phase 1: Player A repays 150 credits
    4. VERIFY: chips_in_play decreases by 150
    5. VERIFY: total_chips_returned increases by 150
    6. VERIFY: total_credits_repaid increases by 150
    """
    
    print_section("SETTLEMENT PHASE CREDIT REPAYMENT VERIFICATION")
    print("\nThis test verifies that chips_in_play is correctly decremented")
    print("during settlement phase credit repayment.\n")
    
    # Clear database
    db.games.delete_many({})
    db.players.delete_many({})
    db.transactions.delete_many({})
    db.banks.delete_many({})
    db.unpaid_credits.delete_many({})
    
    # Step 1: Create game and player
    print_section("STEP 1: Setup Game and Player")
    player_a_id = 1001
    game_id, game_code = game_service.create_game(player_a_id, "PlayerA")
    print(f"✓ Created game {game_code} (ID: {game_id})")
    print(f"✓ Player A joined as host")
    
    # Step 2: Buy-ins
    print_section("STEP 2: Player A Buy-ins")
    
    # Cash buy-in
    print("\n[Action] Player A buys in 100 cash...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    print("✓ Cash buy-in approved by host")
    
    # Credit buy-in
    print("\n[Action] Player A buys in 200 credit...")
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "register", 200)
    transaction_service.approve_transaction(tx_id)
    print("✓ Credit buy-in approved by host")
    
    bank = bank_dal.get_by_game(game_id)
    print_bank_status(bank, "Bank After Buy-ins")
    
    player = player_service.get_player(game_id, player_a_id)
    print_player_status("Player A", player.credits_owed)
    
    # Step 3: Cashout with 0 chips
    print_section("STEP 3: Player A Cashes Out 0 Chips")
    print("\n[Action] Player A cashes out 0 chips (keeps all credits owed)...")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 0)
    transaction_service.approve_transaction(tx_id)
    print("✓ Cashout approved by host")
    
    bank = bank_dal.get_by_game(game_id)
    print_bank_status(bank, "Bank After Cashout")
    
    player = player_service.get_player(game_id, player_a_id)
    print_player_status("Player A", player.credits_owed)
    
    # Step 4: Start Settlement
    print_section("STEP 4: Start Settlement Phase")
    result = settlement_service.start_settlement(game_id)
    print(f"✓ {result['message']}")
    print(f"✓ Players with credits: {len(result['players_with_credits'])}")
    
    # Step 5: BEFORE Credit Repayment
    print_section("STEP 5: BEFORE Credit Repayment")
    bank_before = bank_dal.get_by_game(game_id)
    player_before = player_service.get_player(game_id, player_a_id)
    
    print_bank_status(bank_before, "Bank BEFORE Repayment")
    print_player_status("Player A", player_before.credits_owed)
    
    # Store values for comparison
    chips_in_play_before = bank_before.chips_in_play
    total_chips_returned_before = bank_before.total_chips_returned
    total_credits_repaid_before = bank_before.total_credits_repaid
    player_credits_owed_before = player_before.credits_owed
    
    print("\n📋 Recording state BEFORE repayment:")
    print(f"   chips_in_play = {chips_in_play_before}")
    print(f"   total_chips_returned = {total_chips_returned_before}")
    print(f"   total_credits_repaid = {total_credits_repaid_before}")
    print(f"   Player A credits_owed = {player_credits_owed_before}")
    
    # Step 6: Credit Repayment
    print_section("STEP 6: Player A Repays 150 Credits")
    REPAYMENT_AMOUNT = 150
    print(f"\n[Action] Player A repays {REPAYMENT_AMOUNT} credits...")
    result = settlement_service.repay_credit(game_id, player_a_id, REPAYMENT_AMOUNT)
    print(f"✓ {result['message']}")
    print(f"✓ Credits repaid: {result['credits_repaid']}")
    print(f"✓ Remaining credits: {result['remaining_credits']}")
    
    # Step 7: AFTER Credit Repayment
    print_section("STEP 7: AFTER Credit Repayment")
    bank_after = bank_dal.get_by_game(game_id)
    player_after = player_service.get_player(game_id, player_a_id)
    
    print_bank_status(bank_after, "Bank AFTER Repayment")
    print_player_status("Player A", player_after.credits_owed)
    
    # Store values for verification
    chips_in_play_after = bank_after.chips_in_play
    total_chips_returned_after = bank_after.total_chips_returned
    total_credits_repaid_after = bank_after.total_credits_repaid
    player_credits_owed_after = player_after.credits_owed
    
    print("\n📋 Recording state AFTER repayment:")
    print(f"   chips_in_play = {chips_in_play_after}")
    print(f"   total_chips_returned = {total_chips_returned_after}")
    print(f"   total_credits_repaid = {total_credits_repaid_after}")
    print(f"   Player A credits_owed = {player_credits_owed_after}")
    
    # Step 8: Verification
    print_section("STEP 8: VERIFICATION RESULTS")
    
    all_passed = True
    
    # Calculate changes
    chips_in_play_change = chips_in_play_after - chips_in_play_before
    total_chips_returned_change = total_chips_returned_after - total_chips_returned_before
    total_credits_repaid_change = total_credits_repaid_after - total_credits_repaid_before
    player_credits_change = player_credits_owed_after - player_credits_owed_before
    
    print("\n📊 Changes After Repayment:")
    print("-" * 70)
    
    # Test 1: chips_in_play decremented
    expected_chips_in_play_change = -REPAYMENT_AMOUNT
    if chips_in_play_change == expected_chips_in_play_change:
        print(f"✅ PASS: chips_in_play decreased by {abs(chips_in_play_change)}")
        print(f"         (Expected: {expected_chips_in_play_change}, Actual: {chips_in_play_change})")
    else:
        print(f"❌ FAIL: chips_in_play change incorrect")
        print(f"         (Expected: {expected_chips_in_play_change}, Actual: {chips_in_play_change})")
        all_passed = False
    
    # Test 2: total_chips_returned incremented
    expected_chips_returned_change = REPAYMENT_AMOUNT
    if total_chips_returned_change == expected_chips_returned_change:
        print(f"✅ PASS: total_chips_returned increased by {total_chips_returned_change}")
        print(f"         (Expected: {expected_chips_returned_change}, Actual: {total_chips_returned_change})")
    else:
        print(f"❌ FAIL: total_chips_returned change incorrect")
        print(f"         (Expected: {expected_chips_returned_change}, Actual: {total_chips_returned_change})")
        all_passed = False
    
    # Test 3: total_credits_repaid incremented
    expected_credits_repaid_change = REPAYMENT_AMOUNT
    if total_credits_repaid_change == expected_credits_repaid_change:
        print(f"✅ PASS: total_credits_repaid increased by {total_credits_repaid_change}")
        print(f"         (Expected: {expected_credits_repaid_change}, Actual: {total_credits_repaid_change})")
    else:
        print(f"❌ FAIL: total_credits_repaid change incorrect")
        print(f"         (Expected: {expected_credits_repaid_change}, Actual: {total_credits_repaid_change})")
        all_passed = False
    
    # Test 4: player credits_owed decremented
    expected_player_credits_change = -REPAYMENT_AMOUNT
    if player_credits_change == expected_player_credits_change:
        print(f"✅ PASS: Player A credits_owed decreased by {abs(player_credits_change)}")
        print(f"         (Expected: {expected_player_credits_change}, Actual: {player_credits_change})")
    else:
        print(f"❌ FAIL: Player A credits_owed change incorrect")
        print(f"         (Expected: {expected_player_credits_change}, Actual: {player_credits_change})")
        all_passed = False
    
    # Test 5: Consistency check - chips_in_play equation
    print("\n🔍 Consistency Check:")
    print("-" * 70)
    expected_chips_in_play = bank_after.total_chips_issued - bank_after.total_chips_returned
    actual_chips_in_play = bank_after.chips_in_play
    if expected_chips_in_play == actual_chips_in_play:
        print(f"✅ PASS: chips_in_play = total_chips_issued - total_chips_returned")
        print(f"         {actual_chips_in_play} = {bank_after.total_chips_issued} - {bank_after.total_chips_returned}")
    else:
        print(f"❌ FAIL: chips_in_play equation doesn't match")
        print(f"         Expected: {expected_chips_in_play}, Actual: {actual_chips_in_play}")
        all_passed = False
    
    # Final Summary
    print_section("FINAL SUMMARY")
    
    print("\n📝 Test Scenario Summary:")
    print(f"  Initial state: 300 chips in play (100 cash + 200 credit)")
    print(f"  After 0-chip cashout: 300 chips in play (200 credits owed)")
    print(f"  After {REPAYMENT_AMOUNT} credit repayment: {chips_in_play_after} chips in play")
    print(f"  Expected final: {300 - REPAYMENT_AMOUNT} chips in play")
    
    print("\n" + "=" * 70)
    if all_passed:
        print("  ✅ ALL VERIFICATION TESTS PASSED!")
        print("=" * 70)
        print("\n✓ Settlement phase credit repayment correctly updates:")
        print("  • chips_in_play (decremented)")
        print("  • total_chips_returned (incremented)")
        print("  • total_credits_repaid (incremented)")
        print("  • player credits_owed (decremented)")
        print("\n✓ This matches the behavior of regular cashout flow.")
        return True
    else:
        print("  ❌ SOME VERIFICATION TESTS FAILED!")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = verify_chips_in_play_update()
    sys.exit(0 if success else 1)
