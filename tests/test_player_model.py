import pytest
from src.models.player import Player

def test_player_defaults():
    player = Player(game_id="game123", user_id=42, name="Charlie")
    assert player.final_chips is None
    assert player.quit is False
    assert player.is_host is False
    assert player.active is True
    assert player.cashed_out is False
    assert player.cashout_time is None

def test_player_host_flag():
    host = Player(game_id="game123", user_id=1, name="Alice", is_host=True)
    assert host.is_host
