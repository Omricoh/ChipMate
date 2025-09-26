import os
from pymongo import MongoClient
from bson import ObjectId
from src.models.game import Game

class GamesDAL:
    def __init__(self, db: MongoClient):
        self.col = db.games

    def create(self, game: Game):
        res = self.col.insert_one(game.model_dump())
        return str(res.inserted_id)

    def create_game(self, game: Game):
        """Alias for create method to match test expectations"""
        return self.create(game)

    def get_by_code(self, code: str):
        doc = self.col.find_one({"code": code, "status": "active"})
        if doc:
            return Game(**doc)
        return None

    def get_game(self, game_id):
        """Get game by ID"""
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        doc = self.col.find_one({"_id": game_id})
        if doc:
            return Game(**doc)
        return None

    def add_player(self, game_id, user_id: int):
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        self.col.update_one({"_id": game_id}, {"$addToSet": {"players": user_id}})

    def get_host_id(self, game_id):
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        g = self.col.find_one({"_id": game_id})
        return g.get("host_id") if g else None

    def list_games(self, user=None, password=None):
        """List all games - admin only"""
        admin_user = os.getenv("ADMIN_USER")
        admin_pass = os.getenv("ADMIN_PASS")

        if admin_user and admin_pass:
            if user != admin_user or password != admin_pass:
                raise PermissionError("Unauthorized: Admin credentials required")

        games = []
        for doc in self.col.find():
            games.append(Game(**doc))
        return games

    def update_status(self, game_id, status: str):
        """Update game status"""
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        self.col.update_one({"_id": game_id}, {"$set": {"status": status}})
