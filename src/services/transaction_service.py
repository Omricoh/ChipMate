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
        """Process cashout with automatic debt settlement and transfers
        Order: 1) Pay own debt, 2) Take cash, 3) Take other players' debt"""
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

            remaining_chips = chip_count

            # STEP 1: Pay own debt first (from credit buy-ins)
            player_debts = self.debt_dal.get_player_debts(game_id, user_id)
            player_pending_debts = [d for d in player_debts if d["status"] == "pending"]

            player_debts_to_settle = []
            for debt in player_pending_debts:
                if remaining_chips <= 0:
                    break

                debt_amount = debt["amount"]
                settle_amount = min(remaining_chips, debt_amount)

                if settle_amount > 0:
                    player_debts_to_settle.append({
                        "debt_id": str(debt["_id"]),
                        "amount": settle_amount,
                        "original_debt": debt_amount
                    })
                    remaining_chips -= settle_amount

            # STEP 2: Calculate available cash from cashier
            # Total cash in cashier = all cash buy-ins from all players
            all_cash_buyins = self.transactions_dal.col.find({
                "game_id": game_id,
                "confirmed": True,
                "rejected": False,
                "type": "buyin_cash"
            })
            total_cash_in_cashier = sum(tx["amount"] for tx in all_cash_buyins)

            # Total cash already paid out = sum of all previous cashouts
            previous_cashouts = self.transactions_dal.col.find({
                "game_id": game_id,
                "confirmed": True,
                "type": "cashout"
            })
            total_cash_paid_out = 0
            for cashout_tx in previous_cashouts:
                debt_proc = cashout_tx.get("debt_processing", {})
                total_cash_paid_out += debt_proc.get("final_cash_amount", 0)

            # Available cash in cashier
            cashier_available_cash = total_cash_in_cashier - total_cash_paid_out

            # Final cash = min of (remaining chips, cashier available)
            # Cashier is a shared pool - any player can take cash from it
            final_cash = min(remaining_chips, cashier_available_cash)
            remaining_chips -= final_cash

            # STEP 3: Take debts from other players (inactive players)
            available_debts = self._get_available_debt_transfers(game_id, user_id)

            debt_transfers = []
            for debt in available_debts:
                if remaining_chips <= 0:
                    break

                debt_transfer_amount = min(debt["amount"], remaining_chips)
                if debt_transfer_amount > 0:
                    debt_transfers.append({
                        "debt_id": debt["debt_id"],
                        "amount": debt_transfer_amount,
                        "debtor_name": debt["debtor_name"]
                    })
                    remaining_chips -= debt_transfer_amount

            # Store debt processing information in transaction
            total_debt_settlement = sum(d["amount"] for d in player_debts_to_settle)
            debt_processing = {
                "player_debt_settlement": total_debt_settlement,
                "player_debts_to_settle": player_debts_to_settle,
                "debt_transfers": debt_transfers,
                "final_cash_amount": final_cash,
                "cashier_info": {
                    "total_cash_in": total_cash_in_cashier,
                    "total_paid_out": total_cash_paid_out,
                    "available_cash": cashier_available_cash,
                    "cash_paid_this_transaction": final_cash
                }
            }

            self.transactions_dal.col.update_one(
                {"_id": self.transactions_dal.col.database.ObjectId(tx_id)},
                {"$set": {"debt_processing": debt_processing}}
            )

            logger.info(f"Cashout processed: chip_count={chip_count}, debt_paid={total_debt_settlement}, "
                       f"cash_paid={final_cash}, cashier_before={cashier_available_cash}, "
                       f"cashier_after={cashier_available_cash - final_cash}")

            return {
                "success": True,
                "chip_count": chip_count,
                "player_debt_settlement": total_debt_settlement,
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

            # STEP 1: Settle player's own debts
            settlement_notifications = []
            for debt_settlement in debt_processing.get("player_debts_to_settle", []):
                debt_id = debt_settlement["debt_id"]
                settle_amount = debt_settlement["amount"]
                original_debt = debt_settlement["original_debt"]

                if settle_amount >= original_debt:
                    # Fully settle the debt
                    success = self.debt_dal.settle_debt(debt_id)
                    if success:
                        settlement_notifications.append(debt_settlement)
                else:
                    # Partially settle the debt - reduce the amount
                    self.debt_dal.col.update_one(
                        {"_id": self.debt_dal.col.database.ObjectId(debt_id)},
                        {"$inc": {"amount": -settle_amount}}
                    )
                    settlement_notifications.append(debt_settlement)

            # STEP 2: Transfer debts from other players to this player
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
                "settlement_notifications": settlement_notifications,
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