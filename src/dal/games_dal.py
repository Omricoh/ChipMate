import os
from datetime import datetime, timedelta
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
            # Convert ObjectId to string for id field
            doc['_id'] = str(doc['_id'])
            # Check if game should be expired
            game = Game(**doc)
            if (datetime.utcnow() - game.created_at) > timedelta(hours=12):
                # Auto-expire the game
                self.update_status(doc["_id"], "expired")
                return None
            return game
        return None

    def get_game(self, game_id):
        """Get game by ID"""
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        doc = self.col.find_one({"_id": game_id})
        if doc:
            # Convert ObjectId to string for id field
            doc['_id'] = str(doc['_id'])
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
            # Convert ObjectId to string for id field
            doc['_id'] = str(doc['_id'])
            games.append(Game(**doc))
        return games

    def update_status(self, game_id, status: str):
        """Update game status"""
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)
        self.col.update_one({"_id": game_id}, {"$set": {"status": status}})

    def expire_old_games(self):
        """Mark games older than 12 hours as expired"""
        cutoff_time = datetime.utcnow() - timedelta(hours=12)
        result = self.col.update_many(
            {
                "created_at": {"$lt": cutoff_time},
                "status": "active"
            },
            {"$set": {"status": "expired"}}
        )
        return result.modified_count

    def get_expired_games(self):
        """Get all expired games"""
        games = []
        for doc in self.col.find({"status": "expired"}):
            games.append(Game(**doc))
        return games

    def get_game_report(self, game_id):
        """Generate comprehensive game report"""
        if isinstance(game_id, str):
            game_id = ObjectId(game_id)

        game_doc = self.col.find_one({"_id": game_id})
        if not game_doc:
            return None

        # Get all players
        players = list(self.col.database.players.find({"game_id": str(game_id)}))

        # Get all transactions
        transactions = list(self.col.database.transactions.find({"game_id": str(game_id)}))

        return {
            "game": Game(**game_doc),
            "players": players,
            "transactions": transactions
        }
