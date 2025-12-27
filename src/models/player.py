from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Player(BaseModel):
    game_id: str
    user_id: int
    name: str
    credits_owed: int = 0  # How much credit this player owes to the bank
    final_chips: Optional[int] = None
    quit: bool = False
    is_host: bool = False
    active: bool = True
    cashed_out: bool = False
    cashout_time: Optional[datetime] = None
