"""
Data Access Layer for UnpaidCredits
"""
from src.models.unpaid_credit import UnpaidCredit
from typing import List, Optional
from bson import ObjectId


class UnpaidCreditsDAL:
    """Data Access Layer for unpaid credits operations"""

    def __init__(self, db):
        self.col = db.unpaid_credits

    def create(self, unpaid_credit: UnpaidCredit) -> str:
        """Create a new unpaid credit record"""
        result = self.col.insert_one(unpaid_credit.model_dump())
        return str(result.inserted_id)

    def get_by_game(self, game_id: str) -> List[UnpaidCredit]:
        """Get all unpaid credits for a game"""
        docs = self.col.find({"game_id": game_id})
        return [UnpaidCredit(**doc) for doc in docs]

    def get_available_by_game(self, game_id: str) -> List[UnpaidCredit]:
        """Get unpaid credits that still have available balance"""
        docs = self.col.find({
            "game_id": game_id,
            "$expr": {"$gt": ["$amount", "$amount_claimed"]}
        })
        unpaid_credits = []
        for doc in docs:
            uc = UnpaidCredit(**doc)
            if uc.amount_available > 0:
                unpaid_credits.append(uc)
        return unpaid_credits

    def update_claimed_amount(self, game_id: str, debtor_user_id: int, amount_claimed: int) -> bool:
        """Update the claimed amount for an unpaid credit"""
        result = self.col.update_one(
            {"game_id": game_id, "debtor_user_id": debtor_user_id},
            {"$inc": {"amount_claimed": amount_claimed}}
        )
        return result.modified_count > 0

    def get_by_debtor(self, game_id: str, debtor_user_id: int) -> Optional[UnpaidCredit]:
        """Get unpaid credit by debtor"""
        doc = self.col.find_one({"game_id": game_id, "debtor_user_id": debtor_user_id})
        if doc:
            return UnpaidCredit(**doc)
        return None

    def delete_by_game(self, game_id: str) -> int:
        """Delete all unpaid credits for a game"""
        result = self.col.delete_many({"game_id": game_id})
        return result.deleted_count
