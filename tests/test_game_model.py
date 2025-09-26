import pytest
from datetime import datetime, timezone
from src.models.game import Game

def test_game_defaults():
    game = Game(host_id=1, host_name="Alice", code="ABCDE")
    assert game.status == "active"
    assert isinstance(game.created_at, datetime)
    assert game.created_at.tzinfo is None or game.created_at.tzinfo == timezone.utc
    assert game.players == [ ] or isinstance(game.players, list)
    assert game.code == "ABCDE"

def test_game_players_added():
    game = Game(host_id=2, host_name="Bob", code="XYZ12", players=[2, 3])
    assert len(game.players) == 2
    assert 3 in game.players
