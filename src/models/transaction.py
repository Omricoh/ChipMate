from pydantic import BaseModel, Field
from datetime import datetime

class Transaction(BaseModel):
    game_id: str
    user_id: int
    type: str               # buyin_cash, buyin_register, cashout
    amount: int
    confirmed: bool = False
    rejected: bool = False
    at: datetime = Field(default_factory=datetime.utcnow)
