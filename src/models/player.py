from pydantic import BaseModel
from typing import List, Optional

class Player(BaseModel):
    game_id: str
    user_id: int
    name: str
    buyins: List[int] = []
    final_chips: Optional[int] = None
    quit: bool = False
    is_host: bool = False
    active: bool = True
