"""Notification domain model for ChipMate v2.

Based on T2 MongoDB schema: notifications collection.
Poll-based notifications for players, auto-deleted after 48 hours via TTL index.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.models.common import NotificationType, PyObjectId


class Notification(BaseModel):
    """Poll-based notification for a player.

    Created by backend events (request approval, checkout, etc.).
    Consumed by player clients polling for unread notifications.
    Auto-deleted after 48 hours via MongoDB TTL index.
    """

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    notification_type: NotificationType
    message: str
    related_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at")
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


class NotificationResponse(BaseModel):
    """Response model for Notification data returned via API."""

    model_config = {"populate_by_name": True}

    id: str = Field(alias="_id")
    game_id: str
    player_token: str
    notification_type: NotificationType
    message: str
    related_id: Optional[str] = None
    is_read: bool
    created_at: str
