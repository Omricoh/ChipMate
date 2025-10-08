"""
Test cashout scenarios with debt settlement
Background: Player A: 200 cash + 100 credit, Player B: 200 cash + 500 credit
"""
import os
import sys
# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from datetime import datetime, timezone
from src.services.transaction_service import TransactionService
from src.services.player_service import PlayerService
from src.services.game_service import GameService
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL

MONGO_URL = os.getenv('MONGO_URL')
if not MONGO_URL:
    print("ERROR: MONGO_URL environment variable not set")
    exit(1)

client = MongoClient(MONGO_URL)
db = client.chipbot

# Initialize services
transaction_service = TransactionService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
game_service = GameService(MONGO_URL)
games_dal = GamesDAL(db)
players_dal = PlayersDAL(db)
transactions_dal = TransactionsDAL(db)
debt_dal = DebtDAL(db)

def setup_test_game():
    """Create test game with players A and B and their buy-ins"""
    # Create game with host (Player A)
    player_a_id = int(datetime.now().timestamp() * 1000)
    game_id, game_code = game_service.create_game(player_a_id, "Player A")
    print(f"Created test game: {game_id} (code: {game_code})")

    # Add Player B
    player_b_id = int(datetime.now().timestamp() * 1000) + 1
    players_dal.add_player(game_id, player_b_id, "Player B", is_host=False)
    print(f"Added Player B (id={player_b_id})")

    return game_id, player_a_id, player_b_id

def create_buyins(game_id, player_a_id, player_b_id):
    """Create buy-ins: A: 200 cash + 100 credit, B: 200 cash + 500 credit"""
    # Player A: 200 cash
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "buyin_cash", 200)
    transaction_service.approve_transaction(tx_id)
    print(f"Player A: 200 cash buy-in approved")

    # Player A: 100 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "buyin_register", 100)
    transaction_service.approve_transaction(tx_id)
    print(f"Player A: 100 credit buy-in approved (creates 100 debt)")

    # Player B: 200 cash
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "buyin_cash", 200)
    transaction_service.approve_transaction(tx_id)
    print(f"Player B: 200 cash buy-in approved")

    # Player B: 500 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "buyin_register", 500)
    transaction_service.approve_transaction(tx_id)
    print(f"Player B: 500 credit buy-in approved (creates 500 debt)")

def print_game_state(game_id, title):
    """Print current game state"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")

    # Cash in cashier
    cash_buyins = list(transactions_dal.col.find({
        "game_id": game_id,
        "confirmed": True,
        "type": "buyin_cash"
    }))
    total_cash = sum(tx["amount"] for tx in cash_buyins)

    # Cash paid out
    cashouts = list(transactions_dal.col.find({
        "game_id": game_id,
        "confirmed": True,
        "type": "cashout"
    }))
    cash_paid = sum(tx.get("debt_processing", {}).get("final_cash_amount", 0) for tx in cashouts)

    print(f"Cashier: {total_cash - cash_paid} cash available (total in: {total_cash}, paid out: {cash_paid})")

    # Debts
    debts = list(debt_dal.col.find({"game_id": game_id}))
    for debt in debts:
        status = debt.get('status', 'unknown')
        creditor = debt.get('creditor_name', 'unassigned')
        print(f"Debt: {debt['debtor_name']} owes {debt['amount']} (status: {status}, creditor: {creditor})")

def test_scenario_a():
    """
    Test A:
    - B cashes out for 0 -> still in debt of 500, cashier has 400 cash
    - A cashes out for 1000 -> B owes him 500 + receives 400 cash
    """
    print("\n" + "="*60)
    print("TEST SCENARIO A")
    print("="*60)

    game_id, player_a_id, player_b_id = setup_test_game()
    create_buyins(game_id, player_a_id, player_b_id)
    print_game_state(game_id, "Initial State")

    # B cashes out for 0
    print("\n--- Player B cashes out for 0 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_b_id, 0)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by B: {result['player_debt_settlement']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B still in debt of 500")

    # Check B's remaining debt
    b_debts = debt_dal.get_player_debts(game_id, player_b_id)
    b_pending_debt = sum(d['amount'] for d in b_debts if d['status'] == 'pending')
    print(f"✓ B's remaining debt: {b_pending_debt} (expected: 500)")

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 0, is_host_cashout=False)

    print_game_state(game_id, "After B cashout")

    # A cashes out for 1000
    print("\n--- Player A cashes out for 1000 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 1000)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by A: {result['player_debt_settlement']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Debts transferred to A: {result['debt_transfers']}")
    print(f"Expected: A gets 400 cash + B owes him 500")

    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert len(result['debt_transfers']) == 1, f"Expected 1 debt transfer"
    assert result['debt_transfers'][0]['amount'] == 500, f"Expected 500 debt transfer"

    print("✓ TEST A PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    debt_dal.col.delete_many({"game_id": game_id})

def test_scenario_b():
    """
    Test B:
    - B cashes out for 100 -> still in 400 debt
    - A cashes out for 900 -> B owes him 400 + 400 cash
    """
    print("\n" + "="*60)
    print("TEST SCENARIO B")
    print("="*60)

    game_id, player_a_id, player_b_id = setup_test_game()
    create_buyins(game_id, player_a_id, player_b_id)
    print_game_state(game_id, "Initial State")

    # B cashes out for 100
    print("\n--- Player B cashes out for 100 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_b_id, 100)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by B: {result['player_debt_settlement']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B pays 100 debt, still in 400 debt")

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 100, is_host_cashout=False)

    # Check B's remaining debt
    b_debts = debt_dal.get_player_debts(game_id, player_b_id)
    b_pending_debt = sum(d['amount'] for d in b_debts if d['status'] == 'pending')
    print(f"✓ B's remaining debt: {b_pending_debt} (expected: 400)")

    print_game_state(game_id, "After B cashout")

    # A cashes out for 900
    print("\n--- Player A cashes out for 900 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 900)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by A: {result['player_debt_settlement']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Debts transferred to A: {result['debt_transfers']}")
    print(f"Expected: A gets 400 cash + B owes him 400")

    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert len(result['debt_transfers']) == 1, f"Expected 1 debt transfer"
    assert result['debt_transfers'][0]['amount'] == 400, f"Expected 400 debt transfer"

    print("✓ TEST B PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    debt_dal.col.delete_many({"game_id": game_id})

def test_scenario_c():
    """
    Test C:
    - B cashes out for 500 -> no debt
    - A cashes out for 500 -> 400 cash
    """
    print("\n" + "="*60)
    print("TEST SCENARIO C")
    print("="*60)

    game_id, player_a_id, player_b_id = setup_test_game()
    create_buyins(game_id, player_a_id, player_b_id)
    print_game_state(game_id, "Initial State")

    # B cashes out for 500
    print("\n--- Player B cashes out for 500 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_b_id, 500)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by B: {result['player_debt_settlement']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B pays all 500 debt, no remaining debt")

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 500, is_host_cashout=False)

    # Check B's remaining debt
    b_debts = debt_dal.get_player_debts(game_id, player_b_id)
    b_pending_debt = sum(d['amount'] for d in b_debts if d['status'] in ['pending', 'assigned'])
    print(f"✓ B's remaining debt: {b_pending_debt} (expected: 0)")

    print_game_state(game_id, "After B cashout")

    # A cashes out for 500
    print("\n--- Player A cashes out for 500 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 500)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by A: {result['player_debt_settlement']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Debts transferred to A: {result['debt_transfers']}")
    print(f"Expected: A gets 400 cash, no debt transfers")

    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert len(result['debt_transfers']) == 0, f"Expected 0 debt transfers"

    print("✓ TEST C PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    debt_dal.col.delete_many({"game_id": game_id})

def test_scenario_d():
    """
    Test D:
    - B cashes out for 600 -> no debt + 100 cash
    - A cashes out for 400 -> 300 cash
    """
    print("\n" + "="*60)
    print("TEST SCENARIO D")
    print("="*60)

    game_id, player_a_id, player_b_id = setup_test_game()
    create_buyins(game_id, player_a_id, player_b_id)
    print_game_state(game_id, "Initial State")

    # B cashes out for 600
    print("\n--- Player B cashes out for 600 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_b_id, 600)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by B: {result['player_debt_settlement']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B pays all 500 debt + gets 100 cash")

    assert result['player_debt_settlement'] == 500, f"Expected 500 debt paid, got {result['player_debt_settlement']}"
    assert result['final_cash'] == 100, f"Expected 100 cash, got {result['final_cash']}"

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 600, is_host_cashout=False)

    # Check B's remaining debt
    b_debts = debt_dal.get_player_debts(game_id, player_b_id)
    b_pending_debt = sum(d['amount'] for d in b_debts if d['status'] in ['pending', 'assigned'])
    print(f"B's remaining debt: {b_pending_debt} (expected: 0)")

    print_game_state(game_id, "After B cashout")

    # A cashes out for 400
    print("\n--- Player A cashes out for 400 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 400)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Debt paid by A: {result['player_debt_settlement']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Debts transferred to A: {result['debt_transfers']}")
    print(f"Expected: A pays 100 debt + gets 300 cash")

    assert result['player_debt_settlement'] == 100, f"Expected 100 debt paid, got {result['player_debt_settlement']}"
    assert result['final_cash'] == 300, f"Expected 300 cash, got {result['final_cash']}"
    assert len(result['debt_transfers']) == 0, f"Expected 0 debt transfers"

    print("TEST D PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    debt_dal.col.delete_many({"game_id": game_id})

if __name__ == "__main__":
    try:
        test_scenario_a()
        test_scenario_b()
        test_scenario_c()
        test_scenario_d()

        print("\n" + "="*60)
        print("ALL TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
