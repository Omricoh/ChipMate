from src.models.debt import Debt
from pymongo.collection import Collection
from bson import ObjectId
from datetime import datetime, timezone
from typing import List, Optional

class DebtDAL:
    def __init__(self, db):
        self.col: Collection = db.debts

    def create_debt(self, game_id: str, debtor_user_id: int, debtor_name: str,
                   amount: int, transaction_id: str) -> str:
        """Create a new debt record"""
        debt = Debt(
            game_id=game_id,
            debtor_user_id=debtor_user_id,
            debtor_name=debtor_name,
            amount=amount,
            original_transaction_id=transaction_id
        )
        result = self.col.insert_one(debt.model_dump())
        return str(result.inserted_id)

    def get_pending_debts(self, game_id: str) -> List[dict]:
        """Get all pending debts for a game"""
        return list(self.col.find({
            "game_id": game_id,
            "status": "pending"
        }).sort("created_at", 1))

    def get_player_debts(self, game_id: str, user_id: int) -> List[dict]:
        """Get all debts for a specific player (as debtor)"""
        return list(self.col.find({
            "game_id": game_id,
            "debtor_user_id": user_id
        }))

    def get_player_credits(self, game_id: str, user_id: int) -> List[dict]:
        """Get all debts owed to a specific player (as creditor)"""
        return list(self.col.find({
            "game_id": game_id,
            "creditor_user_id": user_id
        }))

    def assign_debt_to_creditor(self, debt_id: str, creditor_user_id: int,
                               creditor_name: str) -> bool:
        """Assign a debt to a creditor (when they cash out)"""
        result = self.col.update_one(
            {"_id": ObjectId(debt_id)},
            {"$set": {
                "creditor_user_id": creditor_user_id,
                "creditor_name": creditor_name,
                "status": "assigned",
                "transferred_at": datetime.now(timezone.utc)
            }}
        )
        return result.modified_count > 0

    def get_total_pending_debt_amount(self, game_id: str) -> int:
        """Get total amount of pending debts in a game"""
        pipeline = [
            {"$match": {"game_id": game_id, "status": "pending"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        result = list(self.col.aggregate(pipeline))
        return result[0]["total"] if result else 0

    def settle_debt(self, debt_id: str) -> bool:
        """Mark a debt as settled"""
        result = self.col.update_one(
            {"_id": ObjectId(debt_id)},
            {"$set": {"status": "settled"}}
        )
        return result.modified_count > 0