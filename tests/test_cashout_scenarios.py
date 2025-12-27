"""
Test cashout scenarios with simplified credit system
Background: Player A: 200 cash + 100 credit, Player B: 200 cash + 500 credit

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
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.bank_dal import BankDAL
from src.models.player import Player

# Use mongomock instead of real MongoDB
MONGO_URL = "mongodb://localhost:27017/"
client = shared_mock_client
db = client.chipbot

# Initialize services with mock MongoDB
transaction_service = TransactionService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
game_service = GameService(MONGO_URL)
games_dal = GamesDAL(db)
players_dal = PlayersDAL(db)
transactions_dal = TransactionsDAL(db)
bank_dal = BankDAL(db)

def setup_test_game():
    """Create test game with players A and B and their buy-ins"""
    # Create game with host (Player A)
    player_a_id = int(datetime.now().timestamp() * 1000)
    game_id, game_code = game_service.create_game(player_a_id, "Player A")
    print(f"Created test game: {game_id} (code: {game_code})")

    # Add Player B
    player_b_id = int(datetime.now().timestamp() * 1000) + 1
    player_b = Player(game_id=game_id, user_id=player_b_id, name="Player B", is_host=False)
    players_dal.add_player(player_b)
    print(f"Added Player B (id={player_b_id})")

    return game_id, player_a_id, player_b_id

def create_buyins(game_id, player_a_id, player_b_id):
    """Create buy-ins: A: 200 cash + 100 credit, B: 200 cash + 500 credit"""
    # Player A: 200 cash
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "cash", 200)
    transaction_service.approve_transaction(tx_id)
    print(f"Player A: 200 cash buy-in approved")

    # Player A: 100 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, player_a_id, "register", 100)
    transaction_service.approve_transaction(tx_id)
    print(f"Player A: 100 credit buy-in approved (A now owes 100 to bank)")

    # Player B: 200 cash
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "cash", 200)
    transaction_service.approve_transaction(tx_id)
    print(f"Player B: 200 cash buy-in approved")

    # Player B: 500 credit
    tx_id = transaction_service.create_buyin_transaction(game_id, player_b_id, "register", 500)
    transaction_service.approve_transaction(tx_id)
    print(f"Player B: 500 credit buy-in approved (B now owes 500 to bank)")

def print_game_state(game_id, title):
    """Print current game state"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")

    # Get bank status
    bank = bank_dal.get_by_game(game_id)
    if bank:
        print(f"Bank: {bank.cash_balance} cash available (total in: {bank.total_cash_in}, paid out: {bank.total_cash_out})")
        print(f"Bank: {bank.total_credits_issued} credits issued, {bank.total_credits_repaid} repaid")

    # Player credits
    players = players_dal.get_players(game_id)
    for player in players:
        if player.credits_owed > 0:
            print(f"Player {player.name} owes {player.credits_owed} credits to bank")

def test_scenario_a():
    """
    Test A (SIMPLIFIED):
    - B cashes out for 0 -> still owes 500 to bank, gets nothing
    - A cashes out for 1000 -> repays own 100 credits, gets 400 cash from bank

    NOTE: In new system, no automatic debt transfers. A does NOT get B's debt.
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

    print(f"Credits repaid by B: {result['credits_repaid']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B still owes 500 to bank")

    assert result['credits_repaid'] == 0, f"Expected 0 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 0, f"Expected 0 cash, got {result['final_cash']}"

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 0)

    # Check B's remaining credits owed
    player_b = players_dal.get_player(game_id, player_b_id)
    print(f"B's remaining credits owed: {player_b.credits_owed} (expected: 500)")
    assert player_b.credits_owed == 500, f"Expected 500 credits owed, got {player_b.credits_owed}"

    print_game_state(game_id, "After B cashout")

    # A cashes out for 1000
    print("\n--- Player A cashes out for 1000 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 1000)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Credits repaid by A: {result['credits_repaid']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Chips not covered: {result['chips_not_covered']}")
    print(f"Expected: A repays 100 credits, gets 400 cash, 500 chips uncovered")

    assert result['credits_repaid'] == 100, f"Expected 100 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert result['chips_not_covered'] == 500, f"Expected 500 uncovered chips, got {result['chips_not_covered']}"

    print("OK TEST A PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    bank_dal.col.delete_many({"game_id": game_id})

def test_scenario_b():
    """
    Test B (SIMPLIFIED):
    - B cashes out for 100 -> repays 100 credits, still owes 400
    - A cashes out for 900 -> repays own 100 credits, gets 400 cash, 400 chips uncovered
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

    print(f"Credits repaid by B: {result['credits_repaid']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B repays 100 credits, still owes 400")

    assert result['credits_repaid'] == 100, f"Expected 100 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 0, f"Expected 0 cash, got {result['final_cash']}"

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 100)

    # Check B's remaining credits
    player_b = players_dal.get_player(game_id, player_b_id)
    print(f"B's remaining credits owed: {player_b.credits_owed} (expected: 400)")
    assert player_b.credits_owed == 400, f"Expected 400 credits owed, got {player_b.credits_owed}"

    print_game_state(game_id, "After B cashout")

    # A cashes out for 900
    print("\n--- Player A cashes out for 900 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 900)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Credits repaid by A: {result['credits_repaid']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Chips not covered: {result['chips_not_covered']}")
    print(f"Expected: A repays 100 credits, gets 400 cash, 400 chips uncovered")

    assert result['credits_repaid'] == 100, f"Expected 100 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert result['chips_not_covered'] == 400, f"Expected 400 uncovered chips, got {result['chips_not_covered']}"

    print("OK TEST B PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    bank_dal.col.delete_many({"game_id": game_id})

def test_scenario_c():
    """
    Test C (SIMPLIFIED):
    - B cashes out for 500 -> repays all 500 credits
    - A cashes out for 500 -> repays 100 credits, gets 400 cash
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

    print(f"Credits repaid by B: {result['credits_repaid']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B repays all 500 credits")

    assert result['credits_repaid'] == 500, f"Expected 500 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 0, f"Expected 0 cash, got {result['final_cash']}"

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 500)

    # Check B's remaining credits
    player_b = players_dal.get_player(game_id, player_b_id)
    print(f"B's remaining credits owed: {player_b.credits_owed} (expected: 0)")
    assert player_b.credits_owed == 0, f"Expected 0 credits owed, got {player_b.credits_owed}"

    print_game_state(game_id, "After B cashout")

    # A cashes out for 500
    print("\n--- Player A cashes out for 500 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 500)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Credits repaid by A: {result['credits_repaid']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Expected: A repays 100 credits, gets 400 cash")

    assert result['credits_repaid'] == 100, f"Expected 100 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 400, f"Expected 400 cash, got {result['final_cash']}"
    assert result['chips_not_covered'] == 0, f"Expected 0 uncovered chips, got {result['chips_not_covered']}"

    print("OK TEST C PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    bank_dal.col.delete_many({"game_id": game_id})

def test_scenario_d():
    """
    Test D (SIMPLIFIED):
    - B cashes out for 600 -> repays 500 credits + gets 100 cash
    - A cashes out for 400 -> repays 100 credits + gets 300 cash
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

    print(f"Credits repaid by B: {result['credits_repaid']}")
    print(f"Cash received by B: {result['final_cash']}")
    print(f"Expected: B repays 500 credits + gets 100 cash")

    assert result['credits_repaid'] == 500, f"Expected 500 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 100, f"Expected 100 cash, got {result['final_cash']}"

    transaction_service.execute_cashout_debt_operations(tx_id)
    player_service.cashout_player(game_id, player_b_id, 600)

    # Check B's remaining credits
    player_b = players_dal.get_player(game_id, player_b_id)
    print(f"B's remaining credits owed: {player_b.credits_owed} (expected: 0)")
    assert player_b.credits_owed == 0, f"Expected 0 credits owed, got {player_b.credits_owed}"

    print_game_state(game_id, "After B cashout")

    # A cashes out for 400
    print("\n--- Player A cashes out for 400 chips ---")
    tx_id = transaction_service.create_cashout_transaction(game_id, player_a_id, 400)
    transaction_service.approve_transaction(tx_id)
    result = transaction_service.process_cashout_with_debt_settlement(tx_id)

    print(f"Credits repaid by A: {result['credits_repaid']}")
    print(f"Cash received by A: {result['final_cash']}")
    print(f"Expected: A repays 100 credits + gets 300 cash")

    assert result['credits_repaid'] == 100, f"Expected 100 credits repaid, got {result['credits_repaid']}"
    assert result['final_cash'] == 300, f"Expected 300 cash, got {result['final_cash']}"
    assert result['chips_not_covered'] == 0, f"Expected 0 uncovered chips, got {result['chips_not_covered']}"

    print("TEST D PASSED")

    # Cleanup
    games_dal.col.delete_one({"_id": game_id})
    players_dal.col.delete_many({"game_id": game_id})
    transactions_dal.col.delete_many({"game_id": game_id})
    bank_dal.col.delete_many({"game_id": game_id})

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
