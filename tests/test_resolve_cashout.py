"""
Tests for the resolve cashout feature
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
from src.models.player import Player

# Use mongomock instead of real MongoDB
MONGO_URL = "mongodb://localhost:27017/"

# Initialize services with mock MongoDB
transaction_service = TransactionService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
game_service = GameService(MONGO_URL)


def setup_function():
    """Clean up database before each test"""
    shared_mock_client.drop_database('chipbot')


def test_resolve_cashout_credits_owed_greater_than_cashout():
    """
    Test Case 1: Player owes more credit than cashout amount
    - Player owes: 600 credits
    - Cashes out: 200 chips
    - Result: credits_owed = 400, player gets nothing
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player manually
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Give player credits (via credit buyin)
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "register", 600)
    transaction_service.approve_transaction(tx_id)
    
    # Player requests cashout
    cashout_tx_id = transaction_service.create_cashout_transaction(game_id, 2, 200)
    
    # Resolve cashout with 0 cash and 0 credit (all goes to repaying debt)
    result = transaction_service.resolve_cashout(cashout_tx_id, 0, 0)
    
    assert result["success"] is True
    assert result["breakdown"]["credits_repaid"] == 200
    assert result["breakdown"]["cash_paid"] == 0
    assert result["breakdown"]["credit_given"] == 0
    assert result["breakdown"]["new_credits_owed"] == 400
    
    # Verify player status
    player = player_service.players_dal.get_player(game_id, 2)
    assert player.credits_owed == 400
    assert player.cashed_out is True
    assert player.active is False


def test_resolve_cashout_with_default_allocation():
    """
    Test Case 2: Player covers their credit and has remainder
    - Player owes: 100 credits
    - Player bought in: 200 cash
    - Cashes out: 500 chips
    - Default allocation: 200 cash, 200 credit
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Cash buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 200)
    transaction_service.approve_transaction(tx_id)
    
    # Credit buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "register", 100)
    transaction_service.approve_transaction(tx_id)
    
    # Player requests cashout
    cashout_tx_id = transaction_service.create_cashout_transaction(game_id, 2, 500)
    
    # Resolve cashout: 200 cash, 200 credit
    result = transaction_service.resolve_cashout(cashout_tx_id, 200, 200)
    
    assert result["success"] is True
    assert result["breakdown"]["credits_repaid"] == 100
    assert result["breakdown"]["cash_paid"] == 200
    assert result["breakdown"]["credit_given"] == 200
    assert result["breakdown"]["new_credits_owed"] == 200  # 100 - 100 + 200
    
    # Verify player status
    player = player_service.players_dal.get_player(game_id, 2)
    assert player.credits_owed == 200
    assert player.cashed_out is True
    
    # Verify bank
    bank = game_service.bank_dal.get_by_game(game_id)
    assert bank.cash_balance == 0  # 200 in - 200 out
    assert bank.total_credits_issued == 300  # 100 + 200
    assert bank.total_credits_repaid == 100


def test_resolve_cashout_custom_allocation():
    """
    Test Case 3: Custom allocation
    - Player owes: 0 credits
    - Player bought in: 500 cash
    - Cashes out: 1000 chips
    - Custom: 300 cash, 700 credit
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Cash buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 500)
    transaction_service.approve_transaction(tx_id)
    
    # Player requests cashout
    cashout_tx_id = transaction_service.create_cashout_transaction(game_id, 2, 1000)
    
    # Resolve with custom allocation
    result = transaction_service.resolve_cashout(cashout_tx_id, 300, 700)
    
    assert result["success"] is True
    assert result["breakdown"]["credits_repaid"] == 0
    assert result["breakdown"]["cash_paid"] == 300
    assert result["breakdown"]["credit_given"] == 700
    assert result["breakdown"]["new_credits_owed"] == 700
    
    # Verify bank
    bank = game_service.bank_dal.get_by_game(game_id)
    assert bank.cash_balance == 200  # 500 in - 300 out
    assert bank.total_credits_issued == 700


def test_resolve_cashout_validation_sum_mismatch():
    """
    Test validation: Sum doesn't match amount to allocate
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Cash buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    
    # Player requests cashout
    cashout_tx_id = transaction_service.create_cashout_transaction(game_id, 2, 100)
    
    # Try to resolve with incorrect sum (should be 100, trying 50 + 30 = 80)
    result = transaction_service.resolve_cashout(cashout_tx_id, 50, 30)
    
    assert result["success"] is False
    assert "must equal amount to allocate" in result["error"]


def test_resolve_cashout_validation_cash_exceeds_bank():
    """
    Test validation: Cash exceeds bank balance
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Cash buyin (bank has only 100)
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    
    # Player requests cashout for more
    cashout_tx_id = transaction_service.create_cashout_transaction(game_id, 2, 200)
    
    # Try to resolve with more cash than available (200 cash, 0 credit)
    result = transaction_service.resolve_cashout(cashout_tx_id, 200, 0)
    
    assert result["success"] is False
    assert "exceeds bank balance" in result["error"]


def test_get_player_buyin_summary():
    """
    Test getting player buyin summary
    """
    # Create game
    game_id, _ = game_service.create_game(1, "Host")
    
    # Add player
    player = Player(game_id=game_id, user_id=2, name="Player1", is_host=False)
    player_service.players_dal.add_player(player)
    
    # Cash buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 200)
    transaction_service.approve_transaction(tx_id)
    
    # Credit buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "register", 150)
    transaction_service.approve_transaction(tx_id)
    
    # Another cash buyin
    tx_id = transaction_service.create_buyin_transaction(game_id, 2, "cash", 100)
    transaction_service.approve_transaction(tx_id)
    
    # Get summary
    summary = transaction_service.get_player_buyin_summary(game_id, 2)
    
    assert summary["cash_buyins"] == 300
    assert summary["credit_buyins"] == 150
    assert summary["total_buyins"] == 450


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

