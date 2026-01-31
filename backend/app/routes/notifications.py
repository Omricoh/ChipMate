"""Notification route handlers.

Endpoints:
    GET  /api/games/{game_id}/notifications                        -- Get notifications.
    POST /api/games/{game_id}/notifications/{notification_id}/read -- Mark one read.
    POST /api/games/{game_id}/notifications/read-all               -- Mark all read.
"""

import logging

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_player
from app.dal.database import get_database
from app.dal.notifications_dal import NotificationDAL
from app.models.player import Player
from app.services.notification_service import NotificationService

logger = logging.getLogger("chipmate.routes.notifications")

router = APIRouter(prefix="/games/{game_id}/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> NotificationService:
    """Build a NotificationService wired to the current database."""
    db = get_database()
    return NotificationService(notification_dal=NotificationDAL(db))


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    """Response model for a single notification."""
    id: str
    game_id: str
    player_token: str
    notification_type: str
    message: str
    related_id: str | None = None
    is_read: bool
    created_at: str


class NotificationsListResponse(BaseModel):
    """Response for GET /api/games/{game_id}/notifications."""
    notifications: list[NotificationOut]
    unread_count: int


class MarkAllReadResponse(BaseModel):
    """Response for POST /api/games/{game_id}/notifications/read-all."""
    marked_count: int


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _to_notification_out(notification) -> NotificationOut:
    """Convert a Notification domain model to the route response model."""
    created_at_str = (
        notification.created_at.isoformat()
        if hasattr(notification.created_at, "isoformat")
        else str(notification.created_at)
    )
    return NotificationOut(
        id=str(notification.id),
        game_id=notification.game_id,
        player_token=notification.player_token,
        notification_type=str(notification.notification_type),
        message=notification.message,
        related_id=notification.related_id,
        is_read=notification.is_read,
        created_at=created_at_str,
    )


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/notifications
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=NotificationsListResponse,
    summary="Get notifications for the authenticated player",
)
async def get_notifications(
    game_id: str = Path(...),
    unread_only: bool = Query(True, description="If true, return only unread notifications."),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of notifications."),
    player: Player = Depends(get_current_player),
) -> NotificationsListResponse:
    """Get notifications for the authenticated player. Requires player token."""
    service = _get_service()
    notifications = await service.get_player_notifications(
        game_id=game_id,
        player_token=player.player_token,
        unread_only=unread_only,
        limit=limit,
    )
    unread_count = await service.get_unread_count(
        game_id=game_id,
        player_token=player.player_token,
    )
    return NotificationsListResponse(
        notifications=[_to_notification_out(n) for n in notifications],
        unread_count=unread_count,
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/notifications/{notification_id}/read
# ---------------------------------------------------------------------------

@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark a single notification as read",
)
async def mark_notification_read(
    game_id: str = Path(...),
    notification_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> dict:
    """Mark a notification as read. Requires player token (ownership validated)."""
    service = _get_service()
    await service.mark_notification_read(
        notification_id=notification_id,
        player_token=player.player_token,
    )
    return {"success": True}


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/notifications/read-all
# ---------------------------------------------------------------------------

@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    summary="Mark all notifications as read",
)
async def mark_all_read(
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> MarkAllReadResponse:
    """Mark all unread notifications as read for the player. Requires player token."""
    service = _get_service()
    count = await service.mark_all_read(
        game_id=game_id,
        player_token=player.player_token,
    )
    return MarkAllReadResponse(marked_count=count)
