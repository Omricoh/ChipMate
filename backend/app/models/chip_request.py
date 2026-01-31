"""Chip Request domain model for ChipMate v2.

Based on T2 MongoDB schema: chip_requests collection.
Represents a buy-in request (cash or credit) from a player.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, model_validator

from app.models.common import PyObjectId, RequestStatus, RequestType


class ChipRequest(BaseModel):
    """Represents a buy-in request (cash or credit) from a player.

    Replaces v1's Transaction model. Uses an explicit status enum
    instead of boolean confirmed/rejected fields.
    """

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    requested_by: str
    request_type: RequestType
    amount: int = Field(gt=0)
    status: RequestStatus = RequestStatus.PENDING
    edited_amount: Optional[int] = Field(default=None, gt=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    @model_validator(mode="after")
    def validate_edited_amount(self) -> "ChipRequest":
        """Ensure edited_amount is provided when status is EDITED."""
        if (
            self.status == RequestStatus.EDITED
            and self.edited_amount is None
        ):
            raise ValueError(
                "edited_amount is required when status is EDITED"
            )
        return self

    @property
    def effective_amount(self) -> int:
        """The actual chip amount after manager resolution.

        Returns 0 for DECLINED or PENDING requests.
        """
        if self.status == RequestStatus.EDITED:
            return self.edited_amount  # type: ignore[return-value]
        if self.status == RequestStatus.APPROVED:
            return self.amount
        return 0

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at", "resolved_at")
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


class ChipRequestResponse(BaseModel):
    """Response model for ChipRequest data returned via API."""

    model_config = {"populate_by_name": True}

    id: str = Field(alias="_id")
    game_id: str
    player_token: str
    requested_by: str
    request_type: RequestType
    amount: int
    status: RequestStatus
    edited_amount: Optional[int] = None
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
