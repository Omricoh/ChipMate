"""
Transaction Service - Business Logic Layer
Handles all transaction and debt-related business operations
"""
import logging
from pymongo import MongoClient
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL
from src.dal.players_dal import PlayersDAL
from src.bl.transaction_bl import create_buyin, create_cashout
from src.models.transaction import Transaction

logger = logging.getLogger("chipbot")

class TransactionService:
    """Service for transaction and debt-related business operations"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.transactions_dal = TransactionsDAL(self.db)
        self.debt_dal = DebtDAL(self.db)
        self.players_dal = PlayersDAL(self.db)

    def create_buyin_transaction(self, game_id: str, user_id: int, buyin_type: str, amount: int) -> str:
        """Create a new buyin transaction"""
        try:
            # Use existing BL to create transaction
            tx = create_buyin(game_id, user_id, buyin_type, amount)
            tx_id = self.transactions_dal.create(tx)

            logger.info(f"Created {buyin_type} buyin of {amount} for user {user_id}")
            return tx_id

        except Exception as e:
            logger.error(f"Error creating buyin transaction: {e}")
            raise

    def create_cashout_transaction(self, game_id: str, user_id: int, amount: int, is_former_host: bool = False) -> str:
        """Create a new cashout transaction"""
        try:
            # Use existing BL to create transaction
            tx = create_cashout(game_id, user_id, amount)
            tx_id = self.transactions_dal.create(tx)

            # Mark as former host cashout if applicable
            if is_former_host:
                self.transactions_dal.col.update_one(
                    {"_id": self.transactions_dal.col.database.ObjectId(tx_id)},
                    {"$set": {"former_host_cashout": True}}
                )

            logger.info(f"Created cashout of {amount} for user {user_id}")
            return tx_id

        except Exception as e:
            logger.error(f"Error creating cashout transaction: {e}")
            raise

    def approve_transaction(self, tx_id: str) -> bool:
        """Approve a transaction and handle side effects"""
        try:
            # Get transaction details
            tx = self.transactions_dal.get(tx_id)
            if not tx:
                return False

            # Approve the transaction
            self.transactions_dal.update_status(tx_id, True, False)

            # Handle register buyin - create debt
            if tx["type"] == "buyin_register":
                player = self.players_dal.get_player(tx["game_id"], tx["user_id"])
                if player:
                    self.debt_dal.create_debt(
                        game_id=tx["game_id"],
                        debtor_user_id=tx["user_id"],
                        debtor_name=player.name,
                        amount=tx["amount"],
                        transaction_id=tx_id
                    )

            logger.info(f"Approved transaction {tx_id}")
            return True

        except Exception as e:
            logger.error(f"Error approving transaction: {e}")
            return False

    def reject_transaction(self, tx_id: str) -> bool:
        """Reject a transaction"""
        try:
            self.transactions_dal.update_status(tx_id, False, True)
            logger.info(f"Rejected transaction {tx_id}")
            return True

        except Exception as e:
            logger.error(f"Error rejecting transaction: {e}")
            return False

    def process_cashout_with_debt_settlement(self, tx_id: str) -> Dict[str, Any]:
        """Process cashout with automatic debt settlement and transfers"""
        try:
            tx = self.transactions_dal.get(tx_id)
            if not tx or tx["type"] != "cashout":
                return {"success": False, "error": "Invalid cashout transaction"}

            game_id = tx["game_id"]
            user_id = tx["user_id"]
            chip_count = tx["amount"]

            player = self.players_dal.get_player(game_id, user_id)
            if not player:
                return {"success": False, "error": "Player not found"}

            # STEP 1: Calculate debt transfers from inactive players
            available_debts = self._get_available_debt_transfers(game_id, user_id)
            transfer_amount = min(chip_count, sum(d["amount"] for d in available_debts))

            debt_transfers = []
            remaining_transfer = transfer_amount
            for debt in available_debts:
                if remaining_transfer <= 0:
                    break

                debt_transfer_amount = min(debt["amount"], remaining_transfer)
                if debt_transfer_amount > 0:
                    debt_transfers.append({
                        "debt_id": debt["debt_id"],
                        "amount": debt_transfer_amount,
                        "debtor_name": debt["debtor_name"]
                    })
                    remaining_transfer -= debt_transfer_amount

            # STEP 2: Calculate final cash amount - only based on cash buy-ins
            # Get cash buyins for this player
            cash_transactions = self.transactions_dal.col.find({
                "game_id": game_id,
                "user_id": user_id,
                "confirmed": True,
                "rejected": False,
                "type": "buyin_cash"
            })
            cash_buyins = sum(tx["amount"] for tx in cash_transactions)
            final_cash = min(chip_count, cash_buyins)

            # Store debt processing information in transaction
            debt_processing = {
                "player_debt_settlement": 0,  # No debt settlement
                "player_debts_to_settle": [],  # No debts settled
                "debt_transfers": debt_transfers,
                "final_cash_amount": final_cash
            }

            self.transactions_dal.col.update_one(
                {"_id": self.transactions_dal.col.database.ObjectId(tx_id)},
                {"$set": {"debt_processing": debt_processing}}
            )

            return {
                "success": True,
                "chip_count": chip_count,
                "player_debt_settlement": 0,  # No debt settlement
                "debt_transfers": debt_transfers,
                "final_cash": final_cash,
                "debt_processing": debt_processing
            }

        except Exception as e:
            logger.error(f"Error processing cashout with debt settlement: {e}")
            return {"success": False, "error": str(e)}

    def execute_cashout_debt_operations(self, tx_id: str) -> Dict[str, Any]:
        """Execute the actual debt settlement and transfer operations"""
        try:
            tx = self.transactions_dal.get(tx_id)
            debt_processing = tx.get("debt_processing", {})

            game_id = tx["game_id"]
            user_id = tx["user_id"]
            player = self.players_dal.get_player(game_id, user_id)

            # Execute debt transfers (no debt settlement anymore)
            transfer_notifications = []
            for transfer in debt_processing.get("debt_transfers", []):
                success = self.debt_dal.assign_debt_to_creditor(
                    transfer["debt_id"],
                    user_id,
                    player.name if player else "Unknown"
                )
                if success:
                    transfer_notifications.append(transfer)

            return {
                "success": True,
                "settlement_notifications": [],  # No settlements anymore
                "transfer_notifications": transfer_notifications
            }

        except Exception as e:
            logger.error(f"Error executing debt operations: {e}")
            return {"success": False, "error": str(e)}

    def _get_available_debt_transfers(self, game_id: str, requesting_user_id: int) -> List[Dict]:
        """Get available debt transfers from inactive players"""
        try:
            # Get all pending debts
            pending_debts = self.debt_dal.get_pending_debts(game_id)

            # Filter for debts from inactive/cashed out players
            available_transfers = []
            for debt in pending_debts:
                debtor = self.players_dal.get_player(game_id, debt["debtor_user_id"])
                # Only allow transfers from inactive players or cashed out players
                if debtor and (not debtor.active or debtor.cashed_out):
                    available_transfers.append({
                        "debt_id": str(debt["_id"]),
                        "amount": debt["amount"],
                        "debtor_name": debt["debtor_name"]
                    })

            return available_transfers

        except Exception as e:
            logger.error(f"Error getting available debt transfers: {e}")
            return []

    def get_player_transaction_summary(self, game_id: str, user_id: int) -> Dict[str, Any]:
        """Get transaction summary for a player"""
        try:
            # Get all transactions
            transactions = list(self.db.transactions.find({
                "game_id": game_id,
                "user_id": user_id,
                "confirmed": True,
                "rejected": False
            }))

            # Convert ObjectId to string for JSON serialization
            for tx in transactions:
                if '_id' in tx:
                    tx['_id'] = str(tx['_id'])

            # Support both old and new transaction type formats
            cash_buyins = sum(tx["amount"] for tx in transactions if tx["type"] in ["buyin_cash", "buyin_buyin_cash"])
            credit_buyins = sum(tx["amount"] for tx in transactions if tx["type"] in ["buyin_register", "buyin_buyin_register"])
            total_buyins = cash_buyins + credit_buyins

            # Get player's debt (both pending and assigned debts)
            player_debts = self.debt_dal.get_player_debts(game_id, user_id)
            pending_debt = sum(debt["amount"] for debt in player_debts if debt["status"] in ["pending", "assigned"])

            return {
                "cash_buyins": cash_buyins,
                "credit_buyins": credit_buyins,
                "total_buyins": total_buyins,
                "pending_debt": pending_debt,
                "transactions": transactions
            }

        except Exception as e:
            logger.error(f"Error getting player transaction summary: {e}")
            raise

    def generate_cashout_rejection_suggestions(self, game_id: str, user_id: int, requested_amount: int) -> List[str]:
        """Generate suggestions for rejected cashout"""
        try:
            summary = self.get_player_transaction_summary(game_id, user_id)
            suggestions = []

            # Analyze the rejection and provide suggestions
            total_investment = summary["total_buyins"]

            if requested_amount > total_investment * 2:
                suggestions.append(f"💡 Consider a more modest amount (you invested {total_investment})")

            if requested_amount < total_investment:
                suggestions.append(f"🎯 Your buyins total {total_investment} - consider playing longer")

            suggestions.append("⏰ Try cashing out at a different time")
            suggestions.append("🗣️ Talk to the host about the best cashout amount")
            suggestions.append("♻️ You can request a new cashout anytime")

            return suggestions[:4]  # Limit to 4 suggestions

        except Exception as e:
            logger.error(f"Error generating cashout suggestions: {e}")
            return ["🗣️ Talk to the host about your cashout request"]