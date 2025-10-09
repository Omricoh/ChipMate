"""
Transaction Service - Business Logic Layer
Handles all transaction and debt-related business operations
"""
import logging
from pymongo import MongoClient
from bson import ObjectId
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from src.dal.transactions_dal import TransactionsDAL
from src.dal.players_dal import PlayersDAL
from src.dal.bank_dal import BankDAL
from src.bl.transaction_bl import create_buyin, create_cashout
from src.models.transaction import Transaction

logger = logging.getLogger("chipbot")

class TransactionService:
    """Service for transaction and debt-related business operations"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.transactions_dal = TransactionsDAL(self.db)
        self.players_dal = PlayersDAL(self.db)
        self.bank_dal = BankDAL(self.db)

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
                    {"_id": ObjectId(tx_id) if isinstance(tx_id, str) else tx_id},
                    {"$set": {"former_host_cashout": True}}
                )

            logger.info(f"Created cashout of {amount} for user {user_id}")
            return tx_id

        except Exception as e:
            logger.error(f"Error creating cashout transaction: {e}")
            raise

    def approve_transaction(self, tx_id: str) -> bool:
        """
        Approve a transaction and execute bank operations.

        *** HOST APPROVAL REQUIRED ***
        This method should ONLY be called when the host approves a transaction.
        The bank will ONLY accept/pay money when this is called.

        Flow:
        1. HOST approves the transaction (by calling this method)
        2. Transaction marked as approved in database
        3. Bank executes the operation:
           - CASH BUY-IN: Bank takes player's cash, issues chips
           - CREDIT BUY-IN: Bank issues chips on credit, records debt
        4. Money enters bank ONLY here for buy-ins

        Returns:
            bool: True if approved successfully, False otherwise
        """
        try:
            # Get transaction details
            tx = self.transactions_dal.get(tx_id)
            if not tx:
                logger.error(f"Transaction {tx_id} not found")
                return False

            # Check if already processed
            if tx.get("confirmed"):
                logger.warning(f"Transaction {tx_id} already approved")
                return True

            # Approve the transaction in database
            self.transactions_dal.update_status(tx_id, True, False)

            # CASH BUY-IN: Player gives cash → Bank takes it → Issues chips
            if tx["type"] == "buyin_cash":
                self.bank_dal.record_cash_buyin(tx["game_id"], tx["amount"])
                logger.info(f"✓ HOST APPROVED: Bank received {tx['amount']} cash, issued {tx['amount']} chips")

            # CREDIT BUY-IN: Bank issues chips on credit → Player owes credit
            if tx["type"] == "buyin_register":
                player = self.players_dal.get_player(tx["game_id"], tx["user_id"])
                if player:
                    # Update player's credit owed
                    self.players_dal.col.update_one(
                        {"game_id": tx["game_id"], "user_id": tx["user_id"]},
                        {"$inc": {"credits_owed": tx["amount"]}}
                    )
                    # Bank issues chips on credit
                    self.bank_dal.record_credit_buyin(tx["game_id"], tx["amount"])
                    logger.info(f"✓ HOST APPROVED: Bank issued {tx['amount']} chips on credit, player now owes {player.credits_owed + tx['amount']}")

            # CASHOUT: Player returns chips → Repays credits → Gets cash
            if tx["type"] == "cashout":
                # Process cashout settlement
                cashout_result = self.process_cashout_with_debt_settlement(tx_id)

                if cashout_result.get("success"):
                    # Execute cashout operations (update player credits and bank)
                    self.execute_cashout_debt_operations(tx_id)

                    # Mark player as cashed out
                    self.players_dal.col.update_one(
                        {"game_id": tx["game_id"], "user_id": tx["user_id"]},
                        {"$set": {
                            "cashed_out": True,
                            "final_chips": tx["amount"],
                            "cashout_time": datetime.now(timezone.utc)
                        }}
                    )

                    logger.info(f"✓ HOST APPROVED CASHOUT: Player {tx['user_id']} cashed out {tx['amount']} chips")
                else:
                    logger.error(f"Failed to process cashout settlement: {cashout_result.get('error')}")
                    return False

            logger.info(f"Transaction {tx_id} approved by host")
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
        """
        SIMPLIFIED CASHOUT PROCESSING

        Flow:
        1. Player returns chips to bank
        2. Chips used to repay player's own credits
        3. Remaining chips converted to cash (if bank has it)
        4. No automatic debt transfers - player chooses what to take
        """
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

            # Get player's credits owed
            credits_owed = player.credits_owed
            remaining_chips = chip_count

            # STEP 1: Repay own credits first
            credits_repaid = min(remaining_chips, credits_owed)
            remaining_chips -= credits_repaid

            # STEP 2: Get available cash from bank
            cashier_available_cash = self.bank_dal.get_available_cash(game_id)

            # Final cash = min of (remaining chips, cashier available)
            final_cash = min(remaining_chips, cashier_available_cash)
            remaining_chips -= final_cash

            # Store processing information in transaction
            cashout_processing = {
                "credits_repaid": credits_repaid,
                "final_cash_amount": final_cash,
                "chips_not_covered": remaining_chips,  # Chips that can't be converted
                "bank_info": {
                    "available_cash": cashier_available_cash,
                    "cash_paid": final_cash
                }
            }

            self.transactions_dal.col.update_one(
                {"_id": ObjectId(tx_id) if isinstance(tx_id, str) else tx_id},
                {"$set": {"cashout_processing": cashout_processing}}
            )

            logger.info(f"Cashout calculated: chips={chip_count}, credits_repaid={credits_repaid}, "
                       f"cash={final_cash}, uncovered={remaining_chips}")

            return {
                "success": True,
                "chip_count": chip_count,
                "credits_repaid": credits_repaid,
                "final_cash": final_cash,
                "chips_not_covered": remaining_chips,
                "cashout_processing": cashout_processing
            }

        except Exception as e:
            logger.error(f"Error processing cashout: {e}")
            return {"success": False, "error": str(e)}

    def execute_cashout_debt_operations(self, tx_id: str) -> Dict[str, Any]:
        """
        SIMPLIFIED: Execute cashout - update player credits and bank

        *** HOST APPROVAL REQUIRED ***
        This method should ONLY be called after host approves the cashout.

        Flow:
        1. Player returns CHIPS to bank
        2. Reduce player's credits_owed
        3. Bank pays CASH (if available)
        4. Done - no debt transfers

        Returns:
            Dict with success status
        """
        try:
            tx = self.transactions_dal.get(tx_id)
            if not tx:
                return {"success": False, "error": "Transaction not found"}

            # Verify transaction is approved (host approved it)
            if not tx.get("confirmed"):
                return {"success": False, "error": "Transaction not approved by host"}

            cashout_processing = tx.get("cashout_processing", {})
            game_id = tx["game_id"]
            user_id = tx["user_id"]
            player = self.players_dal.get_player(game_id, user_id)

            # Verify chips are being returned
            chips_returned = tx["amount"]
            if chips_returned <= 0:
                return {"success": False, "error": "Cannot cashout without returning chips"}

            # Get values from processing
            credits_repaid = cashout_processing.get("credits_repaid", 0)
            cash_paid = cashout_processing.get("final_cash_amount", 0)

            # STEP 1: Reduce player's credits owed
            if credits_repaid > 0:
                self.players_dal.col.update_one(
                    {"game_id": game_id, "user_id": user_id},
                    {"$inc": {"credits_owed": -credits_repaid}}
                )
                logger.info(f"Player repaid {credits_repaid} credits, now owes {max(0, player.credits_owed - credits_repaid)}")

            # STEP 2: Record in bank (chips returned, cash paid, credits repaid)
            self.bank_dal.record_cashout(game_id, chips_returned, cash_paid, credits_repaid)
            logger.info(f"✓ HOST APPROVED CASHOUT: Player returned {chips_returned} chips → "
                       f"Repaid {credits_repaid} credits, received {cash_paid} cash")

            return {
                "success": True,
                "credits_repaid": credits_repaid,
                "cash_paid": cash_paid
            }

        except Exception as e:
            logger.error(f"Error executing cashout: {e}")
            return {"success": False, "error": str(e)}

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

            # Get player's credits owed
            player = self.players_dal.get_player(game_id, user_id)
            credits_owed = player.credits_owed if player else 0

            return {
                "cash_buyins": cash_buyins,
                "credit_buyins": credit_buyins,
                "total_buyins": total_buyins,
                "credits_owed": credits_owed,
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

    def get_pending_transactions_formatted(self, game_id: str) -> List[Dict[str, Any]]:
        """Get pending transactions formatted for API response"""
        try:
            pending_txs = list(self.transactions_dal.col.find({
                'game_id': game_id,
                'confirmed': False,
                'rejected': False
            }).sort('created_at', 1))

            result = []
            for tx in pending_txs:
                result.append({
                    'id': str(tx['_id']),
                    'game_id': tx['game_id'],
                    'user_id': tx['user_id'],
                    'type': tx['type'],
                    'amount': tx['amount'],
                    'confirmed': tx.get('confirmed', False),
                    'rejected': tx.get('rejected', False),
                    'created_at': tx.get('created_at').isoformat() if tx.get('created_at') else None
                })

            return result

        except Exception as e:
            logger.error(f"Error getting pending transactions: {e}")
            raise

    def get_game_credits_formatted(self, game_id: str) -> List[Dict[str, Any]]:
        """Get all player credits formatted for API response"""
        try:
            players = self.players_dal.get_players(game_id)

            result = []
            for player in players:
                if player.credits_owed > 0:
                    result.append({
                        'user_id': player.user_id,
                        'name': player.name,
                        'credits_owed': player.credits_owed,
                        'is_host': player.is_host,
                        'active': player.active,
                        'cashed_out': player.cashed_out
                    })

            return result

        except Exception as e:
            logger.error(f"Error getting game credits: {e}")
            raise

    def process_host_cashout(self, game_id: str, user_id: int, amount: int) -> Dict[str, Any]:
        """
        SIMPLIFIED: Process complete host cashout flow

        Host can approve their own cashout immediately
        """
        try:
            # Create cashout transaction
            tx_id = self.create_cashout_transaction(game_id, user_id, amount)

            # Calculate cashout (credits repaid, cash paid)
            cashout_result = self.process_cashout_with_debt_settlement(tx_id)

            # Auto-approve for host transactions
            self.approve_transaction(tx_id)

            # Execute cashout operations
            self.execute_cashout_debt_operations(tx_id)

            # Get player info
            player = self.players_dal.get_player(game_id, user_id)
            player_name = player.name if player else "Player"

            # Get cashout details
            credits_repaid = cashout_result.get('credits_repaid', 0)
            cash_received = cashout_result.get('final_cash', 0)
            chips_not_covered = cashout_result.get('chips_not_covered', 0)

            # Get player's remaining credits owed
            player = self.players_dal.get_player(game_id, user_id)
            remaining_credits = player.credits_owed if player else 0

            # Build detailed message
            message_parts = [f"{player_name} cashed out {amount} chips"]

            if credits_repaid > 0:
                message_parts.append(f"✓ Repaid credits: {credits_repaid} chips")

            if remaining_credits > 0:
                message_parts.append(f"⚠ Still owes bank: {remaining_credits} credits")

            if cash_received > 0:
                message_parts.append(f"✓ Cash received: ${cash_received}")

            if chips_not_covered > 0:
                message_parts.append(f"⚠ {chips_not_covered} chips could not be converted (bank out of cash)")

            detailed_message = "\n".join(message_parts)

            logger.info(f"Host processed cashout of {amount} for user {user_id}")

            return {
                'success': True,
                'transaction_id': tx_id,
                'message': detailed_message,
                'cashout_breakdown': {
                    'total_chips': amount,
                    'credits_repaid': credits_repaid,
                    'remaining_credits': remaining_credits,
                    'cash_received': cash_received,
                    'chips_not_covered': chips_not_covered
                }
            }

        except Exception as e:
            logger.error(f"Error processing host cashout: {e}")
            return {
                'success': False,
                'error': str(e)
            }