"""Player domain model for ChipMate v2.

Based on T2 MongoDB schema: players collection.
One document per player per game, identified by UUID player_token.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.models.common import PyObjectId


class Player(BaseModel):
    """Represents a player's participation in a specific game.

    Players are identified by a UUID token (no registration required).
    One document per player per game.
    """

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    display_name: str
    is_manager: bool = False
    is_active: bool = True
    credits_owed: int = 0
    checked_out: bool = False
    final_chip_count: Optional[int] = None
    profit_loss: Optional[int] = None
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    checked_out_at: Optional[datetime] = None

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("joined_at", "checked_out_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()

    def to_mongo_dict(self) -> dict:
        """Convert model to a MongoDB-insertable dict, excluding None id."""
        data = self.model_dump(by_alias=True, mode="python")
        if data.get("_id") is None:
            data.pop("_id", None)
        return data


class PlayerResponse(BaseModel):
    """Response model for Player data returned via API."""

    model_config = {"populate_by_name": True}

    id: str = Field(alias="_id")
    game_id: str
    player_token: str
    display_name: str
    is_manager: bool
    is_active: bool
    credits_owed: int
    checked_out: bool
    final_chip_count: Optional[int] = None
    profit_loss: Optional[int] = None
    joined_at: str
    checked_out_at: Optional[str] = None
