"""Common enums, shared types, and utilities for ChipMate v2 models."""

from enum import StrEnum
from typing import Annotated, Any

from bson import ObjectId
from pydantic import BeforeValidator, PlainSerializer


def _validate_object_id(value: Any) -> str:
    """Validate and convert ObjectId or string to string representation."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, str):
        if ObjectId.is_valid(value):
            return value
        return value
    raise ValueError(f"Invalid ObjectId value: {value}")


# Annotated type for MongoDB ObjectId fields.
# Accepts ObjectId or string on input, always serializes as string.
PyObjectId = Annotated[
    str,
    BeforeValidator(_validate_object_id),
    PlainSerializer(lambda v: str(v), return_type=str),
]


class GameStatus(StrEnum):
    """Game lifecycle states."""
    OPEN = "OPEN"
    SETTLING = "SETTLING"
    CLOSED = "CLOSED"


class RequestStatus(StrEnum):
    """Chip request lifecycle states."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    EDITED = "EDITED"


class RequestType(StrEnum):
    """Type of chip request (buy-in method)."""
    CASH = "CASH"
    CREDIT = "CREDIT"


class NotificationType(StrEnum):
    """Types of notifications sent to players."""
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_DECLINED = "REQUEST_DECLINED"
    REQUEST_EDITED = "REQUEST_EDITED"
    ON_BEHALF_SUBMITTED = "ON_BEHALF_SUBMITTED"
    CHECKOUT_COMPLETE = "CHECKOUT_COMPLETE"
    GAME_SETTLING = "GAME_SETTLING"
    GAME_CLOSED = "GAME_CLOSED"
    DEBT_SETTLED = "DEBT_SETTLED"


class CheckoutStatus(StrEnum):
    """Per-player checkout state machine states."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VALIDATED = "VALIDATED"
    CREDIT_DEDUCTED = "CREDIT_DEDUCTED"
    AWAITING_DISTRIBUTION = "AWAITING_DISTRIBUTION"
    DISTRIBUTED = "DISTRIBUTED"
    DONE = "DONE"
