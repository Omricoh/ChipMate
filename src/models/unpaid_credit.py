"""
UnpaidCredit Model - Tracks credits that players still owe after partial repayment during settlement
"""
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class UnpaidCredit(BaseModel):
    """
    Represents unpaid credit from a player that can be claimed by other players.

    Example: Player A owed 200 credits, but only repaid 100 chips during settlement.
    The remaining 100 becomes an unpaid credit that other players can claim.
    They will collect this 100 from Player A externally (outside the app).
    """
    game_id: str
    debtor_user_id: int  # Player who owes the money
    debtor_name: str
    amount: int  # Amount of unpaid credit
    amount_claimed: int = 0  # How much has been claimed by other players
    amount_available: int = 0  # amount - amount_claimed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data):
        super().__init__(**data)
        # Calculate available amount
        if 'amount_available' not in data:
            self.amount_available = self.amount - self.amount_claimed

    def claim(self, amount: int) -> bool:
        """Claim some of this unpaid credit"""
        if amount > self.amount_available:
            return False
        self.amount_claimed += amount
        self.amount_available = self.amount - self.amount_claimed
        return True

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
