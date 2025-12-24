import pytest
from src.models.game import Game


class TestGameId:
    """Test suite for Game ID/Code functionality"""

    def test_game_code_length(self):
        """Test game code length is correct"""
        game = Game(host_id=5, host_name="Frank", code="ABCDE")
        assert len(game.code) == 5
