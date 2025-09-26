from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class Game(BaseModel):
    host_id: int
    host_name: str
    status: str = "active"   # active | ending | settled | expired
    created_at: datetime = Field(default_factory=datetime.utcnow)
    players: List[int] = []
    code: str  # Required field - no legacy support
