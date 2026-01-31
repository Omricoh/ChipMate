"""Game and Bank domain models for ChipMate v2.

Based on T2 MongoDB schema: games collection with embedded bank sub-document.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.models.common import GameStatus, PyObjectId


class Bank(BaseModel):
    """Embedded bank sub-document within a Game.

    Tracks all cash and credit flows for a poker session.
    All values are integers representing chip counts.
    """

    cash_balance: int = 0
    total_cash_in: int = 0
    total_cash_out: int = 0
    total_credits_issued: int = 0
    total_credits_repaid: int = 0
    total_chips_issued: int = 0
    total_chips_returned: int = 0
    chips_in_play: int = 0


class Game(BaseModel):
    """Represents a poker session (game) stored in the games collection.

    The game document includes an embedded Bank sub-document
    that tracks all cash and credit flows.
    """

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    code: str
    status: GameStatus = GameStatus.OPEN
    manager_player_token: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: Optional[datetime] = None
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    bank: Bank = Field(default_factory=Bank)

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at", "closed_at", "expires_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()

    def to_mongo_dict(self) -> dict:
        """Convert model to a MongoDB-insertable dict, excluding None id."""
        data = self.model_dump(by_alias=True, mode="python")
        # Remove _id if None so MongoDB generates one
        if data.get("_id") is None:
            data.pop("_id", None)
        return data


class GameResponse(BaseModel):
    """Response model for Game data returned via API."""

    model_config = {"populate_by_name": True}

    id: str = Field(alias="_id")
    code: str
    status: GameStatus
    manager_player_token: str
    created_at: str
    closed_at: Optional[str] = None
    expires_at: str
    bank: Bank
