from src.models.player import Player

class PlayerDAL:
    def __init__(self, db):
        self.col = db.players

    def upsert(self, player: Player):
        self.col.update_one(
            {"game_id": player.game_id, "user_id": player.user_id},
            {"$set": player.model_dump()},
            upsert=True
        )

    def get_active(self, user_id: int):
        return self.col.find_one({"user_id": user_id, "active": True, "quit": False})
