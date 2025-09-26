from bson import ObjectId
from src.models.player import Player

class PlayersDAL:
    def __init__(self, db):
        self.col = db.players

    def upsert(self, player: Player):
        # Players are unique per game - each game has separate player data
        self.col.update_one(
            {"game_id": player.game_id, "user_id": player.user_id},
            {"$set": player.model_dump()},
            upsert=True
        )

    def add_player(self, player: Player):
        """Add a player to the game"""
        self.upsert(player)

    def get_active(self, user_id: int):
        return self.col.find_one({"user_id": user_id, "active": True, "quit": False})

    def get_player(self, game_id, user_id: int):
        """Get specific player in a game"""
        # game_id is stored as string in the player document
        doc = self.col.find_one({"game_id": str(game_id), "user_id": user_id})
        if doc:
            return Player(**doc)
        return None

    def get_players(self, game_id):
        """Get all players in a game"""
        # game_id is stored as string in the player document
        players = []
        for doc in self.col.find({"game_id": str(game_id)}):
            players.append(Player(**doc))
        return players

    def remove_player(self, game_id, user_id: int):
        """Remove player from game - completely delete from collection"""
        # game_id is stored as string in the player document
        self.col.delete_one(
            {"game_id": str(game_id), "user_id": user_id}
        )
