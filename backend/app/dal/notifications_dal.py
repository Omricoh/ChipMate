"""Notification Data Access Layer -- MongoDB operations for the notifications collection.

Provides async CRUD and query methods for Notification documents.
All ObjectId handling is transparent.
"""

import logging
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.notification import Notification

logger = logging.getLogger("chipmate.dal.notifications")

COLLECTION = "notifications"


class NotificationDAL:
    """Data access layer for the notifications collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, notification: Notification) -> Notification:
        """Insert a new notification document.

        Args:
            notification: A Notification model instance (id may be None).

        Returns:
            The Notification with its ``id`` populated.
        """
        doc = notification.to_mongo_dict()
        result = await self._collection.insert_one(doc)
        notification.id = str(result.inserted_id)
        logger.info(
            "Created notification %s (type=%s) for player_token=%s in game=%s",
            notification.id,
            notification.notification_type,
            notification.player_token,
            notification.game_id,
        )
        return notification

    async def create_many(self, notifications: list[Notification]) -> list[Notification]:
        """Insert multiple notification documents at once.

        Useful for broadcasting (e.g., GAME_SETTLING to all players).

        Args:
            notifications: A list of Notification model instances.

        Returns:
            The same list with their ``id`` fields populated.
        """
        if not notifications:
            return notifications

        docs = [n.to_mongo_dict() for n in notifications]
        result = await self._collection.insert_many(docs)
        for notification, inserted_id in zip(notifications, result.inserted_ids):
            notification.id = str(inserted_id)
        logger.info("Created %d notifications in bulk", len(notifications))
        return notifications

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, notification_id: str) -> Optional[Notification]:
        """Find a notification by its MongoDB ``_id``.

        Args:
            notification_id: String representation of the ObjectId.

        Returns:
            A Notification instance, or None if not found.
        """
        if not ObjectId.is_valid(notification_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(notification_id)})
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Notification(**doc)

    async def get_unread(
        self,
        player_token: str,
        game_id: str,
        limit: int = 50,
    ) -> list[Notification]:
        """Get unread notifications for a player in a game, newest first.

        Uses the ``idx_player_game_unread`` index.

        Args:
            player_token: The player's UUID token.
            game_id: String representation of the game's ObjectId.
            limit: Maximum number of results.

        Returns:
            A list of unread Notification instances sorted by created_at descending.
        """
        cursor = (
            self._collection.find(
                {
                    "player_token": player_token,
                    "game_id": game_id,
                    "is_read": False,
                }
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        notifications: list[Notification] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            notifications.append(Notification(**doc))
        return notifications

    async def get_recent(
        self,
        player_token: str,
        game_id: str,
        limit: int = 50,
    ) -> list[Notification]:
        """Get recent notifications for a player (read and unread), newest first.

        Args:
            player_token: The player's UUID token.
            game_id: String representation of the game's ObjectId.
            limit: Maximum number of results.

        Returns:
            A list of Notification instances sorted by created_at descending.
        """
        cursor = (
            self._collection.find(
                {"player_token": player_token, "game_id": game_id}
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        notifications: list[Notification] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            notifications.append(Notification(**doc))
        return notifications

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def mark_read(self, notification_id: str) -> bool:
        """Mark a single notification as read.

        Args:
            notification_id: String ObjectId of the notification.

        Returns:
            True if a document was modified, False otherwise.
        """
        if not ObjectId.is_valid(notification_id):
            return False

        result = await self._collection.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"is_read": True}},
        )
        return result.modified_count > 0

    async def mark_all_read(self, player_token: str, game_id: str) -> int:
        """Mark all unread notifications for a player in a game as read.

        Args:
            player_token: The player's UUID token.
            game_id: String representation of the game's ObjectId.

        Returns:
            The number of notifications that were marked as read.
        """
        result = await self._collection.update_many(
            {
                "player_token": player_token,
                "game_id": game_id,
                "is_read": False,
            },
            {"$set": {"is_read": True}},
        )
        if result.modified_count > 0:
            logger.info(
                "Marked %d notifications as read for player_token=%s in game=%s",
                result.modified_count,
                player_token,
                game_id,
            )
        return result.modified_count

    async def count_unread(self, player_token: str, game_id: str) -> int:
        """Count unread notifications for a player in a game.

        Args:
            player_token: The player's UUID token.
            game_id: String representation of the game's ObjectId.

        Returns:
            The number of unread notifications.
        """
        return await self._collection.count_documents(
            {
                "player_token": player_token,
                "game_id": game_id,
                "is_read": False,
            }
        )
