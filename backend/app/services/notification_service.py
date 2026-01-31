"""Notification business logic service.

Provides helpers for creating, querying, and marking notifications as read.
Used by route handlers and by other services (request_service, checkout, etc.)
to generate player-facing notifications.
"""

import logging
from typing import Optional

from fastapi import HTTPException, status

from app.dal.notifications_dal import NotificationDAL
from app.models.common import NotificationType
from app.models.notification import Notification

logger = logging.getLogger("chipmate.services.notification")


# ---------------------------------------------------------------------------
# Message templates -- used by other services when creating notifications
# ---------------------------------------------------------------------------

MESSAGE_TEMPLATES = {
    "REQUEST_SUBMITTED_FOR_YOU": (
        "{requester_name} submitted a {type} buy-in of {amount} chips on your behalf"
    ),
    "REQUEST_APPROVED": (
        "Your {type} buy-in of {amount} chips was approved"
    ),
    "REQUEST_DECLINED": (
        "Your {type} buy-in of {amount} chips was declined"
    ),
    "REQUEST_EDITED": (
        "Your buy-in was edited to {new_amount} chips and approved "
        "(original: {original_amount})"
    ),
    "CHECKOUT_PROCESSED": (
        "You have been checked out. Final chips: {final_chips}. "
        "P/L: {profit_loss}"
    ),
}


def format_notification_message(template_key: str, **kwargs: object) -> str:
    """Render a notification message from a named template.

    Args:
        template_key: Key into MESSAGE_TEMPLATES.
        **kwargs: Values to interpolate into the template string.

    Returns:
        The formatted message string.

    Raises:
        KeyError: If template_key is not found or required kwargs are missing.
    """
    template = MESSAGE_TEMPLATES[template_key]
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class NotificationService:
    """Service layer for notification operations."""

    def __init__(self, notification_dal: NotificationDAL) -> None:
        self._dal = notification_dal

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_notification(
        self,
        game_id: str,
        player_token: str,
        notification_type: NotificationType,
        message: str,
        related_id: Optional[str] = None,
    ) -> Notification:
        """Create a single notification for a player.

        Args:
            game_id: The game this notification belongs to.
            player_token: Recipient player's UUID token.
            notification_type: The type enum value.
            message: Human-readable message text.
            related_id: Optional related entity ID (e.g. request_id).

        Returns:
            The created Notification with its id populated.
        """
        notification = Notification(
            game_id=game_id,
            player_token=player_token,
            notification_type=notification_type,
            message=message,
            related_id=related_id,
        )
        created = await self._dal.create(notification)
        logger.info(
            "Created notification type=%s for player_token=%s in game=%s",
            notification_type,
            player_token,
            game_id,
        )
        return created

    async def create_bulk_notifications(
        self,
        game_id: str,
        player_tokens: list[str],
        notification_type: NotificationType,
        message: str,
    ) -> list[Notification]:
        """Create notifications for multiple players at once.

        Useful for broadcast events such as game closing or settling.

        Args:
            game_id: The game this notification belongs to.
            player_tokens: List of recipient player UUID tokens.
            notification_type: The type enum value.
            message: Human-readable message text (same for all).

        Returns:
            List of created Notification objects with ids populated.
        """
        if not player_tokens:
            return []

        notifications = [
            Notification(
                game_id=game_id,
                player_token=token,
                notification_type=notification_type,
                message=message,
            )
            for token in player_tokens
        ]
        created = await self._dal.create_many(notifications)
        logger.info(
            "Created %d bulk notifications type=%s in game=%s",
            len(created),
            notification_type,
            game_id,
        )
        return created

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_player_notifications(
        self,
        game_id: str,
        player_token: str,
        unread_only: bool = True,
        limit: int = 20,
    ) -> list[Notification]:
        """Get notifications for a player.

        Args:
            game_id: The game to scope the query to.
            player_token: The player's UUID token.
            unread_only: If True, return only unread notifications.
            limit: Maximum number of results.

        Returns:
            A list of Notification objects, newest first.
        """
        if unread_only:
            return await self._dal.get_unread(player_token, game_id, limit=limit)
        return await self._dal.get_recent(player_token, game_id, limit=limit)

    async def get_unread_count(
        self,
        game_id: str,
        player_token: str,
    ) -> int:
        """Return the count of unread notifications for a player.

        Args:
            game_id: The game to scope the query to.
            player_token: The player's UUID token.

        Returns:
            Integer count of unread notifications.
        """
        return await self._dal.count_unread(player_token, game_id)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def mark_notification_read(
        self,
        notification_id: str,
        player_token: str,
    ) -> bool:
        """Mark a single notification as read, with ownership validation.

        Args:
            notification_id: The MongoDB ObjectId string of the notification.
            player_token: The requesting player's UUID token.

        Returns:
            True if the notification was marked as read.

        Raises:
            HTTPException 404: Notification not found.
            HTTPException 403: Player does not own this notification.
        """
        notification = await self._dal.get_by_id(notification_id)
        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )

        if notification.player_token != player_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this notification",
            )

        result = await self._dal.mark_read(notification_id)
        return result

    async def mark_all_read(
        self,
        game_id: str,
        player_token: str,
    ) -> int:
        """Mark all unread notifications as read for a player in a game.

        Args:
            game_id: The game to scope the update to.
            player_token: The player's UUID token.

        Returns:
            The number of notifications that were marked as read.
        """
        count = await self._dal.mark_all_read(player_token, game_id)
        logger.info(
            "Marked %d notifications as read for player_token=%s in game=%s",
            count,
            player_token,
            game_id,
        )
        return count
