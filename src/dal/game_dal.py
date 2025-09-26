from pymongo import MongoClient
from src.models.game import Game

class GameDAL:
    def __init__(self, db: MongoClient):
        self.col = db.games

    def create(self, game: Game):
        res = self.col.insert_one(game.model_dump())
        return str(res.inserted_id)

    def get_by_code(self, code: str):
        return self.col.find_one({"code": code, "status": "active"})

    def add_player(self, game_id, user_id: int):
        self.col.update_one({"_id": game_id}, {"$addToSet": {"players": user_id}})

    def get_host_id(self, game_id):
        g = self.col.find_one({"_id": game_id})
        return g.get("host_id") if g else None
