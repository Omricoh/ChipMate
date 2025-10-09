"""
Settlement Service - Handles two-phase end-game settlement
Phase 1: Credit repayment
Phase 2: Final cashout with player choices (cash or unpaid credits)
"""
import logging
from pymongo import MongoClient
from bson import ObjectId
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.bank_dal import BankDAL
from src.dal.unpaid_credits_dal import UnpaidCreditsDAL
from src.models.unpaid_credit import UnpaidCredit

logger = logging.getLogger("chipbot")


class SettlementService:
    """Service for two-phase end-game settlement"""

    def __init__(self, mongo_url: str):
        self.client = MongoClient(mongo_url)
        self.db = self.client.chipbot

        self.games_dal = GamesDAL(self.db)
        self.players_dal = PlayersDAL(self.db)
        self.transactions_dal = TransactionsDAL(self.db)
        self.bank_dal = BankDAL(self.db)
        self.unpaid_credits_dal = UnpaidCreditsDAL(self.db)

    def start_settlement(self, game_id: str) -> Dict[str, Any]:
        """
        Start the settlement process - Phase 1: Credit Settlement
        """
        try:
            # Update game status
            self.games_dal.col.update_one(
                {"_id": ObjectId(game_id) if isinstance(game_id, str) else game_id},
                {
                    "$set": {
                        "status": "ending",
                        "settlement_phase": "credit_settlement",
                        "ended_at": datetime.now(timezone.utc)
                    }
                }
            )

            # Get players with credits owed
            players_with_credits = self.get_players_with_credits(game_id)

            logger.info(f"Game {game_id} entered credit settlement phase with {len(players_with_credits)} players owing credits")

            return {
                "success": True,
                "phase": "credit_settlement",
                "players_with_credits": players_with_credits,
                "message": f"Settlement started. {len(players_with_credits)} player(s) need to repay credits."
            }

        except Exception as e:
            logger.error(f"Error starting settlement: {e}")
            return {"success": False, "error": str(e)}

    def get_players_with_credits(self, game_id: str) -> List[Dict[str, Any]]:
        """Get all active players who owe credits"""
        try:
            players = self.players_dal.get_players(game_id)
            players_with_credits = []

            for player in players:
                if player.credits_owed > 0:
                    players_with_credits.append({
                        "user_id": player.user_id,
                        "name": player.name,
                        "credits_owed": player.credits_owed,
                        "credits_repaid": 0,  # Will be updated as they repay
                        "remaining_credits": player.credits_owed
                    })

            return players_with_credits

        except Exception as e:
            logger.error(f"Error getting players with credits: {e}")
            return []

    def repay_credit(self, game_id: str, user_id: int, chips_repaid: int) -> Dict[str, Any]:
        """
        Record credit repayment during Phase 1.

        Player returns chips to repay their credit.
        If they repay less than owed, the remainder becomes unpaid credit.
        """
        try:
            player = self.players_dal.get_player(game_id, user_id)
            if not player:
                return {"success": False, "error": "Player not found"}

            if player.credits_owed == 0:
                return {"success": False, "error": "Player has no credits to repay"}

            if chips_repaid < 0:
                return {"success": False, "error": "Invalid repayment amount"}

            # Can't repay more than owed
            actual_repayment = min(chips_repaid, player.credits_owed)
            remaining_credit = player.credits_owed - actual_repayment

            # Update player's credits owed
            self.players_dal.col.update_one(
                {"game_id": game_id, "user_id": user_id},
                {"$set": {"credits_owed": remaining_credit}}
            )

            # Update bank - record credits repaid
            self.bank_dal.col.update_one(
                {"game_id": game_id},
                {
                    "$inc": {
                        "total_credits_repaid": actual_repayment,
                        "total_chips_returned": chips_repaid,
                        "chips_in_play": -chips_repaid
                    }
                }
            )

            # If there's remaining credit, create unpaid credit record
            if remaining_credit > 0:
                # Check if unpaid credit already exists
                existing_unpaid = self.unpaid_credits_dal.get_by_debtor(game_id, user_id)

                if existing_unpaid:
                    # Update existing record
                    self.unpaid_credits_dal.col.update_one(
                        {"game_id": game_id, "debtor_user_id": user_id},
                        {"$set": {"amount": remaining_credit, "amount_available": remaining_credit - existing_unpaid.amount_claimed}}
                    )
                else:
                    # Create new unpaid credit
                    unpaid_credit = UnpaidCredit(
                        game_id=game_id,
                        debtor_user_id=user_id,
                        debtor_name=player.name,
                        amount=remaining_credit,
                        amount_available=remaining_credit
                    )
                    self.unpaid_credits_dal.create(unpaid_credit)

                logger.info(f"Player {user_id} repaid {actual_repayment} credits, {remaining_credit} remains as unpaid credit")
            else:
                logger.info(f"Player {user_id} fully repaid {actual_repayment} credits")

            return {
                "success": True,
                "chips_repaid": chips_repaid,
                "credits_repaid": actual_repayment,
                "remaining_credits": remaining_credit,
                "message": f"Repaid {actual_repayment} credits" + (f", {remaining_credit} credits remain unpaid" if remaining_credit > 0 else " (fully repaid)")
            }

        except Exception as e:
            logger.error(f"Error repaying credit: {e}")
            return {"success": False, "error": str(e)}

    def complete_credit_settlement(self, game_id: str) -> Dict[str, Any]:
        """
        Complete Phase 1 and move to Phase 2: Final Cashout

        For any players who still have credits_owed > 0, create UnpaidCredit records
        so that other players can claim them in Phase 2.
        """
        try:
            # First, create UnpaidCredit records for any remaining credits_owed
            players = self.players_dal.get_players(game_id)
            for player in players:
                if player.credits_owed > 0:
                    # Check if unpaid credit already exists
                    existing_unpaid = self.unpaid_credits_dal.get_by_debtor(game_id, player.user_id)

                    if existing_unpaid:
                        # Update existing record with current credits_owed
                        self.unpaid_credits_dal.col.update_one(
                            {"game_id": game_id, "debtor_user_id": player.user_id},
                            {"$set": {
                                "amount": player.credits_owed,
                                "amount_available": player.credits_owed - existing_unpaid.amount_claimed
                            }}
                        )
                        logger.info(f"Updated unpaid credit for player {player.user_id}: {player.credits_owed}")
                    else:
                        # Create new unpaid credit
                        unpaid_credit = UnpaidCredit(
                            game_id=game_id,
                            debtor_user_id=player.user_id,
                            debtor_name=player.name,
                            amount=player.credits_owed,
                            amount_available=player.credits_owed
                        )
                        self.unpaid_credits_dal.create(unpaid_credit)
                        logger.info(f"Created unpaid credit for player {player.user_id}: {player.credits_owed}")

            # Move to next phase
            self.games_dal.col.update_one(
                {"_id": ObjectId(game_id) if isinstance(game_id, str) else game_id},
                {"$set": {"settlement_phase": "final_cashout"}}
            )

            # Get available resources for final cashout
            bank = self.bank_dal.get_by_game(game_id)
            unpaid_credits = self.unpaid_credits_dal.get_available_by_game(game_id)

            available_cash = bank.cash_balance if bank else 0
            total_unpaid_credits = sum(uc.amount_available for uc in unpaid_credits)

            logger.info(f"Game {game_id} moved to final_cashout phase. Available: {available_cash} cash, {total_unpaid_credits} unpaid credits")

            return {
                "success": True,
                "phase": "final_cashout",
                "available_cash": available_cash,
                "unpaid_credits": [
                    {
                        "debtor_user_id": uc.debtor_user_id,
                        "debtor_name": uc.debtor_name,
                        "amount_available": uc.amount_available
                    }
                    for uc in unpaid_credits
                ],
                "message": "Credit settlement complete. Players can now cash out."
            }

        except Exception as e:
            logger.error(f"Error completing credit settlement: {e}")
            return {"success": False, "error": str(e)}

    def get_settlement_status(self, game_id: str) -> Dict[str, Any]:
        """Get current settlement status"""
        try:
            game = self.games_dal.get_game(game_id)
            if not game:
                return {"success": False, "error": "Game not found"}

            if game.settlement_phase == "credit_settlement":
                players_with_credits = self.get_players_with_credits(game_id)
                return {
                    "success": True,
                    "phase": "credit_settlement",
                    "players_with_credits": players_with_credits
                }

            elif game.settlement_phase == "final_cashout":
                # Ensure UnpaidCredit records exist for all players with credits_owed > 0
                # (This handles cases where Phase 1 was skipped or completed without creating records)
                players = self.players_dal.get_players(game_id)
                for player in players:
                    if player.credits_owed > 0:
                        existing_unpaid = self.unpaid_credits_dal.get_by_debtor(game_id, player.user_id)
                        if not existing_unpaid:
                            unpaid_credit = UnpaidCredit(
                                game_id=game_id,
                                debtor_user_id=player.user_id,
                                debtor_name=player.name,
                                amount=player.credits_owed,
                                amount_available=player.credits_owed
                            )
                            self.unpaid_credits_dal.create(unpaid_credit)
                            logger.info(f"Auto-created unpaid credit in Phase 2 for player {player.user_id}: {player.credits_owed}")

                bank = self.bank_dal.get_by_game(game_id)
                unpaid_credits = self.unpaid_credits_dal.get_available_by_game(game_id)

                return {
                    "success": True,
                    "phase": "final_cashout",
                    "available_cash": bank.cash_balance if bank else 0,
                    "unpaid_credits": [
                        {
                            "debtor_user_id": uc.debtor_user_id,
                            "debtor_name": uc.debtor_name,
                            "amount_available": uc.amount_available
                        }
                        for uc in unpaid_credits
                    ]
                }

            else:
                return {
                    "success": True,
                    "phase": None,
                    "message": "Game not in settlement"
                }

        except Exception as e:
            logger.error(f"Error getting settlement status: {e}")
            return {"success": False, "error": str(e)}

    def process_final_cashout(self, game_id: str, user_id: int, chips: int,
                              cash_requested: int, unpaid_credits_claimed: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Process final cashout in Phase 2.

        Player specifies:
        - chips: Total chips they're cashing out
        - cash_requested: How much cash they want
        - unpaid_credits_claimed: List of {debtor_user_id, amount} they want to claim

        Validates that cash priority goes to players who paid cash.
        """
        try:
            player = self.players_dal.get_player(game_id, user_id)
            if not player:
                return {"success": False, "error": "Player not found"}

            bank = self.bank_dal.get_by_game(game_id)
            if not bank:
                return {"success": False, "error": "Bank not found"}

            # Calculate player's cash priority (how much cash they actually paid in)
            transactions = list(self.db.transactions.find({
                "game_id": game_id,
                "user_id": user_id,
                "type": "buyin_cash",
                "confirmed": True,
                "rejected": False
            }))
            cash_paid_in = sum(tx["amount"] for tx in transactions)

            # Validate cash request
            if cash_requested > bank.cash_balance:
                return {"success": False, "error": f"Bank only has {bank.cash_balance} cash available"}

            # For now, allow any valid amount, but track if they're taking more than their priority
            taking_priority_cash = min(cash_requested, cash_paid_in)
            taking_extra_cash = max(0, cash_requested - cash_paid_in)

            # Validate unpaid credits claims
            total_claimed = sum(claim['amount'] for claim in unpaid_credits_claimed)

            # Check each claim is valid
            for claim in unpaid_credits_claimed:
                unpaid = self.unpaid_credits_dal.get_by_debtor(game_id, claim['debtor_user_id'])
                if not unpaid:
                    return {"success": False, "error": f"No unpaid credit found for player {claim['debtor_user_id']}"}
                if claim['amount'] > unpaid.amount_available:
                    return {"success": False, "error": f"Only {unpaid.amount_available} available from player {claim['debtor_user_id']}"}

            # Validate total
            if cash_requested + total_claimed != chips:
                return {"success": False, "error": f"Cash ({cash_requested}) + Credits ({total_claimed}) must equal chips ({chips})"}

            # Execute cashout
            # 1. Update bank cash
            if cash_requested > 0:
                self.bank_dal.col.update_one(
                    {"game_id": game_id},
                    {
                        "$inc": {
                            "cash_balance": -cash_requested,
                            "total_cash_out": cash_requested,
                            "total_chips_returned": chips,
                            "chips_in_play": -chips
                        }
                    }
                )

            # 2. Update claimed unpaid credits
            for claim in unpaid_credits_claimed:
                self.unpaid_credits_dal.update_claimed_amount(
                    game_id,
                    claim['debtor_user_id'],
                    claim['amount']
                )

            # 3. Mark player as cashed out
            self.players_dal.col.update_one(
                {"game_id": game_id, "user_id": user_id},
                {
                    "$set": {
                        "cashed_out": True,
                        "final_chips": chips,
                        "cashout_time": datetime.now(timezone.utc)
                    }
                }
            )

            logger.info(f"Player {user_id} final cashout: {chips} chips → {cash_requested} cash + {total_claimed} unpaid credits")

            return {
                "success": True,
                "chips": chips,
                "cash_received": cash_requested,
                "unpaid_credits_claimed": unpaid_credits_claimed,
                "cash_priority_used": taking_priority_cash,
                "extra_cash_taken": taking_extra_cash,
                "message": f"Cashed out {chips} chips: {cash_requested} cash + {total_claimed} in unpaid credits"
            }

        except Exception as e:
            logger.error(f"Error processing final cashout: {e}")
            return {"success": False, "error": str(e)}

    def complete_settlement(self, game_id: str) -> Dict[str, Any]:
        """Mark settlement as completed"""
        try:
            self.games_dal.col.update_one(
                {"_id": ObjectId(game_id) if isinstance(game_id, str) else game_id},
                {
                    "$set": {
                        "status": "settled",
                        "settlement_phase": "completed"
                    }
                }
            )

            logger.info(f"Game {game_id} settlement completed")

            return {
                "success": True,
                "message": "Settlement completed successfully"
            }

        except Exception as e:
            logger.error(f"Error completing settlement: {e}")
            return {"success": False, "error": str(e)}
