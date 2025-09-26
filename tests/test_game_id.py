from src.models.game import Game

def test_game_code_length():
    game = Game(host_id=5, host_name="Frank", code="ABCDE")
    assert len(game.code) == 5
