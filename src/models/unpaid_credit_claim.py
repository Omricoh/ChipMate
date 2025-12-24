"""
UnpaidCreditClaim Model - Tracks which players claimed which unpaid credits
"""
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class UnpaidCreditClaim(BaseModel):
    """
    Represents a claim made by one player on another player's unpaid credit.

    Example: Player A owes 100 credits. Player B claims 50 of it during final cashout.
    This creates a claim record: debtor=A, claimant=B, amount=50

    This allows us to show:
    - Player A what they owe: "50 to Player B"
    - Player B who owes them: "Player A owes 50"
    """
    game_id: str
    debtor_user_id: int  # Player who owes the money
    debtor_name: str
    claimant_user_id: int  # Player who is claiming the money
    claimant_name: str
    amount: int  # Amount claimed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
