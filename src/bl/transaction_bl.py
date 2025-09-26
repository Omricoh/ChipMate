from src.models.transaction import Transaction

def create_buyin(game_id: str, user_id: int, buy_type: str, amount: int):
    return Transaction(game_id=game_id, user_id=user_id, type=f"buyin_{buy_type}", amount=amount)

def create_cashout(game_id: str, user_id: int, amount: int):
    return Transaction(game_id=game_id, user_id=user_id, type="cashout", amount=amount)
