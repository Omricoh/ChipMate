from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId

class Game(BaseModel):
    host_id: int
    host_user_id: Optional[int] = None  # Alias for host_id for backwards compatibility
    host_name: str
    status: str = "active"   # active | ending | settled | expired
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    players: List[int] = []
    code: str  # Required field - no legacy support
    id: Optional[str] = Field(default=None, alias='_id')

    def __init__(self, **data):
        # Ensure host_user_id mirrors host_id
        if 'host_id' in data and 'host_user_id' not in data:
            data['host_user_id'] = data['host_id']
        elif 'host_user_id' in data and 'host_id' not in data:
            data['host_id'] = data['host_user_id']
        super().__init__(**data)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
