"""
Game Service - Business Logic Layer
Handles all game-related business operations
"""
import logging
from pymongo import MongoClient
from typing import Optional, List, Dict, Any

from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL
from src.bl.game_bl import create_game as create_game_bl
from src.models.game import Game

logger = logging.getLogger("chipbot")

class GameService:
    """Service for game-related business operations"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.games_dal = GamesDAL(self.db)
        self.players_dal = PlayersDAL(self.db)
        self.transactions_dal = TransactionsDAL(self.db)
        self.debt_dal = DebtDAL(self.db)

    def create_game(self, host_id: int, host_name: str) -> tuple[str, str]:
        """Create a new game and return game_id and code"""
        try:
            # Use existing BL to create game and host player
            game, host_player = create_game_bl(host_id, host_name)

            # Save to database
            game_id = self.games_dal.create(game)
            host_player.game_id = game_id
            self.players_dal.add_player(host_player)

            logger.info(f"Created game {game.code} with ID {game_id}")
            return game_id, game.code

        except Exception as e:
            logger.error(f"Error creating game: {e}")
            raise

    def join_game(self, code: str, user_id: int, user_name: str) -> Optional[str]:
        """Join a game by code"""
        try:
            game = self.games_dal.get_by_code(code)
            if not game:
                return None

            # Check if user already in game
            existing_player = self.players_dal.get_player(game.id, user_id)
            if existing_player:
                if existing_player.quit:
                    # Rejoin - reactivate player
                    self.players_dal.col.update_one(
                        {"game_id": game.id, "user_id": user_id},
                        {"$set": {"active": True, "quit": False}}
                    )
                return game.id

            # Add new player
            from src.bl.player_bl import join_game as join_game_bl
            player = join_game_bl(game.id, user_id, user_name)
            self.players_dal.add_player(player)

            logger.info(f"User {user_id} joined game {code}")
            return game.id

        except Exception as e:
            logger.error(f"Error joining game: {e}")
            raise

    def get_game(self, game_id: str) -> Optional[Game]:
        """Get game by ID"""
        return self.games_dal.get_game(game_id)

    def get_game_by_code(self, code: str) -> Optional[Game]:
        """Get game by code"""
        return self.games_dal.get_by_code(code)

    def end_game(self, game_id: str) -> bool:
        """End a game"""
        try:
            self.games_dal.update_status(game_id, "ended")

            # Exit all players from the game
            result = self.players_dal.col.update_many(
                {"game_id": game_id},
                {"$set": {"active": False, "game_exited": True}}
            )

            logger.info(f"Game {game_id} ended, {result.modified_count} players exited")
            return True
        except Exception as e:
            logger.error(f"Error ending game: {e}")
            return False

    def get_game_status(self, game_id: str) -> Dict[str, Any]:
        """Get comprehensive game status"""
        try:
            game = self.games_dal.get_game(game_id)
            players = self.players_dal.get_players(game_id)

            # Count active players
            active_players = sum(1 for p in players if p.active and not p.quit)

            # Calculate money in play
            active_player_ids = [p.user_id for p in players if p.active and not p.quit]

            # Support both old and new transaction type formats
            all_buyins = self.db.transactions.find({
                "game_id": game_id,
                "user_id": {"$in": active_player_ids},
                "type": {"$in": ["buyin_cash", "buyin_register", "buyin_buyin_cash", "buyin_buyin_register"]},
                "confirmed": True,
                "rejected": False
            })

            total_cash = 0
            total_credit = 0
            for tx in all_buyins:
                if tx["type"] in ["buyin_cash", "buyin_buyin_cash"]:
                    total_cash += tx["amount"]
                elif tx["type"] in ["buyin_register", "buyin_buyin_register"]:
                    total_credit += tx["amount"]

            # Calculate cashed out amounts
            cashouts = self.db.transactions.find({
                "game_id": game_id,
                "type": "cashout",
                "confirmed": True,
                "rejected": False
            })
            total_cashed_out = sum(tx["amount"] for tx in cashouts)

            # Calculate settled debt
            settled_debts = self.debt_dal.col.find({
                "game_id": game_id,
                "status": "settled"
            })
            total_debt_settled = sum(debt["amount"] for debt in settled_debts)

            return {
                "game": game,
                "active_players": active_players,
                "total_cash": total_cash,
                "total_credit": total_credit,
                "total_buyins": total_cash + total_credit,
                "total_cashed_out": total_cashed_out,
                "total_debt_settled": total_debt_settled
            }

        except Exception as e:
            logger.error(f"Error getting game status: {e}")
            raise

    def get_settlement_data(self, game_id: str) -> Dict[str, Any]:
        """Get settlement data for a game"""
        try:
            players = self.players_dal.get_players(game_id)
            settlements = []

            for p in players:
                if p.final_chips is not None:
                    # Calculate buyins (support both old and new transaction formats)
                    transactions = self.db.transactions.find({
                        "game_id": game_id,
                        "user_id": p.user_id,
                        "type": {"$in": ["buyin_cash", "buyin_register", "buyin_buyin_cash", "buyin_buyin_register"]},
                        "confirmed": True,
                        "rejected": False
                    })

                    total_buyins = sum(tx["amount"] for tx in transactions)
                    net = p.final_chips - total_buyins

                    settlements.append({
                        "name": p.name,
                        "buyins": total_buyins,
                        "chips": p.final_chips,
                        "net": net
                    })

            # Get debt information
            all_debts = self.debt_dal.col.find({"game_id": game_id})
            debt_info = []

            for debt in all_debts:
                if debt["status"] == "assigned":
                    debt_info.append({
                        "debtor": debt["debtor_name"],
                        "creditor": debt["creditor_name"],
                        "amount": debt["amount"]
                    })

            return {
                "settlements": settlements,
                "debts": debt_info
            }

        except Exception as e:
            logger.error(f"Error getting settlement data: {e}")
            raise

    def generate_game_link_with_qr(self, game_code: str, base_url: str) -> Dict[str, str]:
        """Generate game link with QR code as base64 data URL for web API"""
        try:
            import qrcode
            import io
            import base64

            # Build join URL
            join_url = f"{base_url}/join/{game_code}"

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(join_url)
            qr.make(fit=True)

            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64 data URL
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            img_data = base64.b64encode(img_buffer.getvalue()).decode()
            qr_code_data_url = f"data:image/png;base64,{img_data}"

            return {
                'url': join_url,
                'qr_code_data_url': qr_code_data_url
            }

        except ImportError:
            logger.warning("QR code libraries not available")
            raise ImportError("QR code libraries not available")
        except Exception as e:
            logger.error(f"Error generating game link with QR: {e}")
            raise