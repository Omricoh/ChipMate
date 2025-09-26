from src.models.player import Player

def join_game(game_id: str, user_id: int, name: str):
    return Player(game_id=game_id, user_id=user_id, name=name)
