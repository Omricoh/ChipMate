"""
Simple tests for user actions that don't require complex mocking
"""
import pytest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.game import Game
from src.models.player import Player
from src.models.transaction import Transaction
from datetime import datetime


class TestUserActionValidation:
    """Test validation logic used in user actions"""

    def test_game_creation_with_code(self):
        """Test game creation includes required code"""
        game = Game(
            host_id=12345,
            host_name="TestUser",
            code="ABC12",
            status="active"
        )
        assert game.code == "ABC12"
        assert game.host_id == 12345
        assert game.status == "active"

    def test_player_creation(self):
        """Test player model creation"""
        player = Player(
            game_id="game123",
            user_id=12345,
            name="TestUser",
            buyins=[100, 50],
            final_chips=200,
            is_host=False
        )
        assert player.game_id == "game123"
        assert player.user_id == 12345
        assert player.buyins == [100, 50]
        assert player.final_chips == 200
        assert not player.is_host

    def test_cash_transaction_creation(self):
        """Test cash buyin transaction creation"""
        tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="buyin_cash",
            amount=100,
            confirmed=False
        )
        assert tx.type == "buyin_cash"
        assert tx.amount == 100
        assert not tx.confirmed
        assert not tx.rejected

    def test_credit_transaction_creation(self):
        """Test credit buyin transaction creation"""
        tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="buyin_register",
            amount=150,
            confirmed=True
        )
        assert tx.type == "buyin_register"
        assert tx.amount == 150
        assert tx.confirmed

    def test_cashout_transaction_creation(self):
        """Test cashout transaction creation"""
        tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="cashout",
            amount=75,
            confirmed=False
        )
        assert tx.type == "cashout"
        assert tx.amount == 75
        assert not tx.confirmed

    def test_player_host_flag(self):
        """Test player with host flag"""
        host_player = Player(
            game_id="game123",
            user_id=67890,
            name="HostUser",
            is_host=True
        )
        assert host_player.is_host

        regular_player = Player(
            game_id="game123",
            user_id=12345,
            name="RegularUser",
            is_host=False
        )
        assert not regular_player.is_host

    def test_game_status_values(self):
        """Test valid game status values"""
        # Test active game
        active_game = Game(
            host_id=12345,
            host_name="Host",
            code="ABC12",
            status="active"
        )
        assert active_game.status == "active"

        # Test ended game
        ended_game = Game(
            host_id=12345,
            host_name="Host",
            code="XYZ99",
            status="ended"
        )
        assert ended_game.status == "ended"

        # Test expired game
        expired_game = Game(
            host_id=12345,
            host_name="Host",
            code="DEF34",
            status="expired"
        )
        assert expired_game.status == "expired"

    def test_player_quit_status(self):
        """Test player quit status"""
        # Active player
        active_player = Player(
            game_id="game123",
            user_id=12345,
            name="ActivePlayer",
            active=True,
            quit=False
        )
        assert active_player.active
        assert not active_player.quit

        # Quit player
        quit_player = Player(
            game_id="game123",
            user_id=54321,
            name="QuitPlayer",
            active=False,
            quit=True
        )
        assert not quit_player.active
        assert quit_player.quit

    def test_transaction_confirmation_states(self):
        """Test transaction confirmation states"""
        # Pending transaction
        pending_tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="buyin_cash",
            amount=100
        )
        assert not pending_tx.confirmed
        assert not pending_tx.rejected

        # Confirmed transaction
        confirmed_tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="buyin_cash",
            amount=100,
            confirmed=True
        )
        assert confirmed_tx.confirmed
        assert not confirmed_tx.rejected

        # Rejected transaction
        rejected_tx = Transaction(
            game_id="game123",
            user_id=12345,
            type="buyin_cash",
            amount=100,
            rejected=True
        )
        assert not rejected_tx.confirmed
        assert rejected_tx.rejected


class TestBusinessLogicHelpers:
    """Test helper functions used in business logic"""

    def test_buyin_amount_validation(self):
        """Test buyin amount validation logic"""
        def validate_buyin_amount(amount_str):
            try:
                amount = int(amount_str)
                return amount > 0, amount
            except ValueError:
                return False, 0

        # Valid amounts
        valid, amount = validate_buyin_amount("100")
        assert valid
        assert amount == 100

        valid, amount = validate_buyin_amount("50")
        assert valid
        assert amount == 50

        # Invalid amounts
        valid, amount = validate_buyin_amount("invalid")
        assert not valid
        assert amount == 0

        valid, amount = validate_buyin_amount("-50")
        assert not valid

        valid, amount = validate_buyin_amount("0")
        assert not valid

    def test_game_code_format(self):
        """Test game code format validation"""
        def is_valid_game_code(code):
            return len(code) == 5 and code.isalnum() and (code.isupper() or code.isdigit())

        # Valid codes
        assert is_valid_game_code("ABC12")
        assert is_valid_game_code("XYZ99")
        assert is_valid_game_code("12345")
        assert is_valid_game_code("ABCDE")

        # Invalid codes
        assert not is_valid_game_code("abc12")  # lowercase
        assert not is_valid_game_code("AB12")   # too short
        assert not is_valid_game_code("ABCD12") # too long
        assert not is_valid_game_code("AB-12")  # special chars

    def test_player_name_extraction(self):
        """Test extracting player names from user objects"""
        def get_player_name(user_first_name, user_last_name=None):
            if user_last_name:
                return f"{user_first_name} {user_last_name}"
            return user_first_name

        assert get_player_name("John") == "John"
        assert get_player_name("John", "Doe") == "John Doe"
        assert get_player_name("Alice", None) == "Alice"

    def test_transaction_type_validation(self):
        """Test transaction type validation"""
        valid_types = ["buyin_cash", "buyin_register", "cashout"]

        def is_valid_transaction_type(tx_type):
            return tx_type in valid_types

        # Valid types
        assert is_valid_transaction_type("buyin_cash")
        assert is_valid_transaction_type("buyin_register")
        assert is_valid_transaction_type("cashout")

        # Invalid types
        assert not is_valid_transaction_type("invalid")
        assert not is_valid_transaction_type("buyin")
        assert not is_valid_transaction_type("cash")

    def test_game_player_capacity(self):
        """Test game player capacity logic"""
        def can_join_game(current_players, max_players=10):
            return len(current_players) < max_players

        # Can join
        assert can_join_game([1, 2, 3])  # 3 players
        assert can_join_game([1, 2, 3, 4, 5])  # 5 players

        # Cannot join (at capacity)
        full_game = list(range(10))  # 10 players
        assert not can_join_game(full_game)

    def test_settlement_calculation(self):
        """Test settlement calculation logic"""
        def calculate_settlement(players_data):
            """Simple settlement calculation"""
            settlements = {}
            for player_id, data in players_data.items():
                buyins = sum(data.get('buyins', []))
                chips = data.get('final_chips', 0)
                settlements[player_id] = chips - buyins
            return settlements

        # Test data
        players = {
            12345: {'buyins': [100, 50], 'final_chips': 200},  # +50
            54321: {'buyins': [100], 'final_chips': 75},       # -25
            67890: {'buyins': [200], 'final_chips': 175}       # -25
        }

        settlements = calculate_settlement(players)

        assert settlements[12345] == 50   # Won 50
        assert settlements[54321] == -25  # Lost 25
        assert settlements[67890] == -25  # Lost 25

        # Verify total settlement is zero (money conservation)
        total = sum(settlements.values())
        assert total == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])