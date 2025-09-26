import random, string
from src.models.game import Game
from src.models.player import Player

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def create_game(host_id: int, host_name: str):
    code = generate_code()
    # Ensure code is always set for new games
    game = Game(host_id=host_id, host_name=host_name, code=code, players=[host_id])
    host_player = Player(game_id="pending", user_id=host_id, name=host_name, is_host=True)
    return game, host_player
