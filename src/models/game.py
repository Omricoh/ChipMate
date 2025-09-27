from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List

class Game(BaseModel):
    host_id: int
    host_name: str
    status: str = "active"   # active | ending | settled | expired
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    players: List[int] = []
    code: str  # Required field - no legacy support
