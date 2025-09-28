"""
Admin Service - Business Logic Layer
Handles all admin-related business operations
"""
import logging
import os
from pymongo import MongoClient
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL
from src.models.game import Game

logger = logging.getLogger("chipbot")

class AdminService:
    """Service for admin-related business operations"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.games_dal = GamesDAL(self.db)
        self.players_dal = PlayersDAL(self.db)
        self.transactions_dal = TransactionsDAL(self.db)
        self.debt_dal = DebtDAL(self.db)

        # Admin credentials
        self.admin_user = os.getenv("ADMIN_USER")
        self.admin_pass = os.getenv("ADMIN_PASS")

    def authenticate_admin(self, username: str, password: str) -> bool:
        """Authenticate admin user"""
        if not self.admin_user or not self.admin_pass:
            logger.warning("Admin credentials not configured")
            return False

        return username == self.admin_user and password == self.admin_pass

    def get_all_games(self) -> List[Game]:
        """Get all games - admin only"""
        try:
            return self.games_dal.list_games(self.admin_user, self.admin_pass)
        except Exception as e:
            logger.error(f"Error getting all games: {e}")
            return []

    def get_active_games(self) -> List[Game]:
        """Get active games only"""
        try:
            all_games = self.get_all_games()
            return [game for game in all_games if game.status == "active"]
        except Exception as e:
            logger.error(f"Error getting active games: {e}")
            return []

    def get_expired_games(self) -> List[Game]:
        """Get expired games"""
        try:
            return self.games_dal.get_expired_games()
        except Exception as e:
            logger.error(f"Error getting expired games: {e}")
            return []

    def expire_old_games(self) -> int:
        """Expire games older than 12 hours"""
        try:
            count = self.games_dal.expire_old_games()
            logger.info(f"Expired {count} old games")
            return count
        except Exception as e:
            logger.error(f"Error expiring old games: {e}")
            return 0

    async def expire_old_games_job(self, context):
        """Job queue function to expire old games"""
        try:
            count = self.expire_old_games()
            if count > 0:
                logger.info(f"Auto-expired {count} old games")
        except Exception as e:
            logger.error(f"Error in expire old games job: {e}")

    def delete_expired_games(self, game_ids: List[str]) -> int:
        """Delete multiple expired games and all related data"""
        deleted_count = 0
        try:
            for game_id in game_ids:
                if self.destroy_game_completely(game_id):
                    deleted_count += 1

            logger.info(f"Deleted {deleted_count} expired games")
            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting expired games: {e}")
            return deleted_count

    def destroy_game_completely(self, game_id: str) -> bool:
        """Completely destroy a game and all related data"""
        try:
            # Delete in order: debts, transactions, players, then game

            # Delete debts
            debt_result = self.debt_dal.col.delete_many({"game_id": game_id})

            # Delete transactions
            tx_result = self.transactions_dal.col.delete_many({"game_id": game_id})

            # Delete players
            player_result = self.players_dal.col.delete_many({"game_id": game_id})

            # Delete game
            game_result = self.games_dal.col.delete_one(
                {"_id": self.games_dal.col.database.ObjectId(game_id)}
            )

            if game_result.deleted_count > 0:
                logger.info(
                    f"Destroyed game {game_id}: "
                    f"{game_result.deleted_count} game, "
                    f"{player_result.deleted_count} players, "
                    f"{tx_result.deleted_count} transactions, "
                    f"{debt_result.deleted_count} debts"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error destroying game {game_id}: {e}")
            return False

    def generate_comprehensive_game_report(self, game_id: str) -> Dict[str, Any]:
        """Generate comprehensive game report"""
        try:
            # Get game data
            game = self.games_dal.get_game(game_id)
            if not game:
                return {"error": "Game not found"}

            # Get all players (including inactive ones for history)
            all_players = self.players_dal.get_players(game_id)

            # Get all transactions
            all_transactions = list(self.db.transactions.find({"game_id": game_id}))

            # Calculate game statistics
            total_cash_buyins = 0
            total_credit_buyins = 0
            total_cashouts = 0

            for tx in all_transactions:
                if tx.get("confirmed") and not tx.get("rejected"):
                    if tx["type"] == "buyin_cash":
                        total_cash_buyins += tx["amount"]
                    elif tx["type"] == "buyin_register":
                        total_credit_buyins += tx["amount"]
                    elif tx["type"] == "cashout":
                        total_cashouts += tx["amount"]

            # Get debt information
            all_debts = list(self.debt_dal.col.find({"game_id": game_id}))

            # Calculate settlements
            settlements = []
            for player in all_players:
                if player.final_chips is not None:
                    player_buyins = 0
                    player_transactions = [tx for tx in all_transactions if tx["user_id"] == player.user_id]

                    for tx in player_transactions:
                        if tx.get("confirmed") and tx["type"] in ["buyin_cash", "buyin_register"]:
                            player_buyins += tx["amount"]

                    net_result = player.final_chips - player_buyins
                    settlements.append({
                        "player_name": player.name,
                        "buyins": player_buyins,
                        "final_chips": player.final_chips,
                        "net_result": net_result,
                        "status": "cashed_out" if player.cashed_out else "active"
                    })

            # Debt summary
            debt_summary = {
                "total_pending": sum(d["amount"] for d in all_debts if d["status"] == "pending"),
                "total_assigned": sum(d["amount"] for d in all_debts if d["status"] == "assigned"),
                "total_settled": sum(d["amount"] for d in all_debts if d["status"] == "settled")
            }

            # Who owes whom
            debt_relationships = []
            for debt in all_debts:
                if debt["status"] == "assigned" and debt.get("creditor_name"):
                    debt_relationships.append({
                        "debtor": debt["debtor_name"],
                        "creditor": debt["creditor_name"],
                        "amount": debt["amount"]
                    })

            # Game duration
            duration = None
            if game.status == "ended" and hasattr(game, 'ended_at') and game.ended_at:
                duration = game.ended_at - game.created_at
            elif game.status == "active":
                duration = datetime.now(timezone.utc) - game.created_at

            return {
                "game": {
                    "code": game.code,
                    "status": game.status,
                    "host_name": game.host_name,
                    "created_at": game.created_at,
                    "duration": duration
                },
                "statistics": {
                    "total_players": len(all_players),
                    "active_players": sum(1 for p in all_players if p.active and not p.quit),
                    "total_cash_buyins": total_cash_buyins,
                    "total_credit_buyins": total_credit_buyins,
                    "total_buyins": total_cash_buyins + total_credit_buyins,
                    "total_cashouts": total_cashouts
                },
                "settlements": settlements,
                "debt_summary": debt_summary,
                "debt_relationships": debt_relationships,
                "transactions": [
                    {
                        "user_id": tx["user_id"],
                        "type": tx["type"],
                        "amount": tx["amount"],
                        "confirmed": tx.get("confirmed", False),
                        "rejected": tx.get("rejected", False),
                        "created_at": tx.get("created_at")
                    }
                    for tx in all_transactions
                ]
            }

        except Exception as e:
            logger.error(f"Error generating game report: {e}")
            return {"error": str(e)}

    def end_game_and_settle(self, game_id: str) -> Dict[str, Any]:
        """End game and initiate settlement for all active players"""
        try:
            # Get active players
            players = self.players_dal.get_players(game_id)
            active_players = [p for p in players if p.active and not p.quit and not p.cashed_out]

            # Mark game as ended
            self.games_dal.update_status(game_id, "ended")

            # Set ended timestamp if not already set
            self.games_dal.col.update_one(
                {"_id": self.games_dal.col.database.ObjectId(game_id)},
                {"$set": {"ended_at": datetime.now(timezone.utc)}}
            )

            logger.info(f"Game {game_id} ended with {len(active_players)} active players")

            return {
                "success": True,
                "active_players": [{"user_id": p.user_id, "name": p.name} for p in active_players],
                "message": f"Game ended. Settlement needed for {len(active_players)} players."
            }

        except Exception as e:
            logger.error(f"Error ending game and settling: {e}")
            return {"success": False, "error": str(e)}