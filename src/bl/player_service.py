"""
Player Service - Business Logic Layer
Handles all player-related business operations
"""
import logging
from pymongo import MongoClient
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from src.dal.players_dal import PlayersDAL
from src.dal.games_dal import GamesDAL
from src.dal.transactions_dal import TransactionsDAL
from src.models.player import Player

logger = logging.getLogger("chipbot")

class PlayerService:
    """Service for player-related business operations"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.players_dal = PlayersDAL(self.db)
        self.games_dal = GamesDAL(self.db)
        self.transactions_dal = TransactionsDAL(self.db)

    def get_active_player(self, user_id: int) -> Optional[dict]:
        """Get active player by user ID - only returns player if game is still active"""
        player = self.players_dal.get_active(user_id)
        if player:
            # Check if the game is still active
            game = self.games_dal.get_game(player["game_id"])
            if game and game.status == "active":
                return player
        return None

    def get_player(self, game_id: str, user_id: int) -> Optional[Player]:
        """Get specific player in game"""
        return self.players_dal.get_player(game_id, user_id)

    def get_players(self, game_id: str) -> List[Player]:
        """Get all players in game"""
        return self.players_dal.get_players(game_id)

    def add_manual_player(self, game_id: str, player_name: str, host_user_id: int) -> bool:
        """Add player manually by host"""
        try:
            # Verify host permission
            host = self.players_dal.get_player(game_id, host_user_id)
            if not host or not host.is_host:
                return False

            # Use a fake user ID for manual players (negative numbers)
            # Find the lowest unused negative ID
            existing_manual_players = [
                p for p in self.players_dal.get_players(game_id)
                if p.user_id < 0
            ]

            if existing_manual_players:
                fake_user_id = min(p.user_id for p in existing_manual_players) - 1
            else:
                fake_user_id = -1

            # Create manual player
            manual_player = Player(
                game_id=game_id,
                user_id=fake_user_id,
                name=player_name,
                is_host=False
            )

            self.players_dal.add_player(manual_player)
            logger.info(f"Manual player {player_name} added to game {game_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding manual player: {e}")
            return False

    def quit_game(self, user_id: int) -> bool:
        """Player quits the game"""
        try:
            player_doc = self.players_dal.get_active(user_id)
            if not player_doc:
                return False

            # Update player status
            self.players_dal.col.update_one(
                {"game_id": player_doc["game_id"], "user_id": user_id},
                {"$set": {"active": False, "quit": True}}
            )

            logger.info(f"Player {user_id} quit game {player_doc['game_id']}")
            return True

        except Exception as e:
            logger.error(f"Error quitting game: {e}")
            return False

    def cashout_player(self, game_id: str, user_id: int, chip_count: int, is_host_cashout: bool = False) -> bool:
        """Process player cashout - all cashed out players become inactive"""
        try:
            player = self.players_dal.get_player(game_id, user_id)
            if not player:
                return False

            # All cashed out players become inactive, including hosts
            # This makes their debts available for transfer
            update_fields = {
                "cashed_out": True,
                "cashout_time": datetime.now(timezone.utc),
                "active": False,  # All cashed out players become inactive
                "final_chips": chip_count
            }

            # If host is cashing out, they lose host status
            if is_host_cashout:
                update_fields["is_host"] = False

            self.players_dal.col.update_one(
                {"game_id": game_id, "user_id": user_id},
                {"$set": update_fields}
            )

            logger.info(f"Player {user_id} cashed out {chip_count} chips from game {game_id}")
            return True

        except Exception as e:
            logger.error(f"Error processing cashout: {e}")
            return False

    def assign_new_host(self, game_id: str, new_host_user_id: int) -> bool:
        """Assign new host to game"""
        try:
            # Update old host(s) - remove host status
            self.players_dal.col.update_many(
                {"game_id": game_id, "is_host": True},
                {"$set": {"is_host": False}}
            )

            # Set new host
            result = self.players_dal.col.update_one(
                {"game_id": game_id, "user_id": new_host_user_id},
                {"$set": {"is_host": True}}
            )

            if result.modified_count > 0:
                # Update game record
                new_host_player = self.players_dal.get_player(game_id, new_host_user_id)
                if new_host_player:
                    self.games_dal.col.update_one(
                        {"_id": self.games_dal.col.database.ObjectId(game_id)},
                        {"$set": {"host_id": new_host_user_id, "host_name": new_host_player.name}}
                    )

                logger.info(f"New host {new_host_user_id} assigned to game {game_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error assigning new host: {e}")
            return False

    def get_player_list_data(self, game_id: str) -> List[Dict[str, Any]]:
        """Get formatted player list data"""
        try:
            players = self.players_dal.get_players(game_id)
            player_data = []

            for p in players:
                # Determine status
                if p.quit:
                    status = "🚪 Quit"
                elif p.cashed_out:
                    if p.active:
                        status = "💰 Cashed Out (Active)"  # Former host
                    else:
                        status = "💰 Cashed Out"
                elif p.active:
                    status = "✅ Active"
                else:
                    status = "⚠️ Inactive"

                # Calculate buyins
                transactions = self.db.transactions.find({
                    "game_id": game_id,
                    "user_id": p.user_id,
                    "type": {"$in": ["buyin_cash", "buyin_register"]},
                    "confirmed": True,
                    "rejected": False
                })

                cash_buyins = 0
                credit_buyins = 0
                for tx in transactions:
                    if tx["type"] == "buyin_cash":
                        cash_buyins += tx["amount"]
                    elif tx["type"] == "buyin_register":
                        credit_buyins += tx["amount"]

                total_buyins = cash_buyins + credit_buyins

                # Cashout info
                cashout_info = ""
                if p.cashed_out and p.final_chips is not None:
                    cashout_info = f" (Cashed: {p.final_chips})"

                player_data.append({
                    "player": p,
                    "status": status,
                    "cash_buyins": cash_buyins,
                    "credit_buyins": credit_buyins,
                    "total_buyins": total_buyins,
                    "cashout_info": cashout_info,
                    "is_host": p.is_host
                })

            return player_data

        except Exception as e:
            logger.error(f"Error getting player list data: {e}")
            raise

    def get_host_id(self, game_id: str) -> Optional[int]:
        """Get current host ID for game"""
        return self.games_dal.get_host_id(game_id)

    def auto_assign_host_if_needed(self, game_id: str, exclude_user_id: int = None) -> Optional[int]:
        """Auto-assign new host if current host is unavailable"""
        try:
            # Find active players who can become host
            players = self.players_dal.get_players(game_id)
            eligible_players = [
                p for p in players
                if p.active and not p.quit and not p.cashed_out
                and (exclude_user_id is None or p.user_id != exclude_user_id)
            ]

            if eligible_players:
                new_host = eligible_players[0]  # Take first eligible player
                if self.assign_new_host(game_id, new_host.user_id):
                    return new_host.user_id

            return None

        except Exception as e:
            logger.error(f"Error auto-assigning host: {e}")
            return None