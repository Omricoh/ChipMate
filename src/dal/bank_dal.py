from src.models.bank import Bank
from typing import Optional
from datetime import datetime, timezone


class BankDAL:
    """Data Access Layer for Bank operations"""

    def __init__(self, db):
        self.col = db.banks

    def create(self, bank: Bank) -> str:
        """Create a new bank for a game"""
        result = self.col.insert_one(bank.model_dump())
        return str(result.inserted_id)

    def get_by_game(self, game_id: str) -> Optional[Bank]:
        """Get bank by game_id"""
        doc = self.col.find_one({"game_id": game_id})
        if doc:
            return Bank(**doc)
        return None

    def update(self, game_id: str, bank: Bank) -> bool:
        """Update bank record"""
        bank.updated_at = datetime.now(timezone.utc)
        result = self.col.update_one(
            {"game_id": game_id},
            {"$set": bank.model_dump()}
        )
        return result.modified_count > 0

    def record_cash_buyin(self, game_id: str, amount: int) -> bool:
        """Record a cash buy-in in the bank"""
        result = self.col.update_one(
            {"game_id": game_id},
            {
                "$inc": {
                    "cash_balance": amount,
                    "total_cash_in": amount,
                    "total_chips_issued": amount,
                    "chips_in_play": amount
                },
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0

    def record_credit_buyin(self, game_id: str, amount: int) -> bool:
        """Record a credit buy-in in the bank"""
        result = self.col.update_one(
            {"game_id": game_id},
            {
                "$inc": {
                    "total_credits_issued": amount,
                    "total_chips_issued": amount,
                    "chips_in_play": amount
                },
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0

    def record_cashout(self, game_id: str, chips_returned: int, cash_paid: int, credits_repaid: int) -> bool:
        """Record a cashout in the bank"""
        update_fields = {
            "$inc": {
                "total_chips_returned": chips_returned,
                "chips_in_play": -chips_returned
            },
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }

        if cash_paid > 0:
            update_fields["$inc"]["cash_balance"] = -cash_paid
            update_fields["$inc"]["total_cash_out"] = cash_paid

        if credits_repaid > 0:
            update_fields["$inc"]["total_credits_repaid"] = credits_repaid

        result = self.col.update_one(
            {"game_id": game_id},
            update_fields
        )
        return result.modified_count > 0

    def get_available_cash(self, game_id: str) -> int:
        """Get available cash in bank for cashouts"""
        bank = self.get_by_game(game_id)
        if bank:
            return bank.get_available_cash()
        return 0

    def delete_by_game(self, game_id: str) -> bool:
        """Delete bank record for a game"""
        result = self.col.delete_one({"game_id": game_id})
        return result.deleted_count > 0
