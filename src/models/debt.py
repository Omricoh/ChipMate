from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

class Debt(BaseModel):
    game_id: str
    debtor_user_id: int  # Who owes the money
    debtor_name: str
    creditor_user_id: Optional[int] = None  # Who is owed the money (None if not assigned)
    creditor_name: Optional[str] = None
    amount: int
    original_transaction_id: str  # Reference to the original buyin_register transaction
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transferred_at: Optional[datetime] = None
    status: str = "pending"  # pending, assigned, settled