"""Game Data Access Layer -- MongoDB operations for the games collection.

Provides async CRUD and query methods for Game documents with
embedded Bank sub-documents. All ObjectId handling is transparent:
callers pass/receive strings, the DAL converts as needed.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.common import GameStatus
from app.models.game import Game

logger = logging.getLogger("chipmate.dal.games")

COLLECTION = "games"


class GameDAL:
    """Data access layer for the games collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, game: Game) -> Game:
        """Insert a new game document and return it with its generated id.

        Args:
            game: A Game model instance (id may be None).

        Returns:
            The Game with its ``id`` populated from the inserted ObjectId.
        """
        doc = game.to_mongo_dict()
        result = await self._collection.insert_one(doc)
        game.id = str(result.inserted_id)
        logger.info("Created game %s with code %s", game.id, game.code)
        return game

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, game_id: str) -> Optional[Game]:
        """Find a game by its MongoDB ``_id``.

        Args:
            game_id: String representation of the ObjectId.

        Returns:
            A Game instance, or None if not found.
        """
        if not ObjectId.is_valid(game_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(game_id)})
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Game(**doc)

    async def get_by_code(self, code: str) -> Optional[Game]:
        """Find an active game by its 6-character join code.

        Only searches games with status OPEN or SETTLING (matching
        the partial unique index).

        Args:
            code: The 6-character uppercase game code.

        Returns:
            A Game instance, or None if not found.
        """
        doc = await self._collection.find_one(
            {"code": code, "status": {"$in": ["OPEN", "SETTLING"]}}
        )
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Game(**doc)

    async def list_by_status(
        self,
        status: GameStatus,
        limit: int = 50,
        skip: int = 0,
    ) -> list[Game]:
        """List games filtered by status, sorted by created_at descending.

        Uses the ``idx_status_created`` index.

        Args:
            status: The GameStatus to filter on.
            limit: Maximum number of results (default 50).
            skip: Number of documents to skip (for pagination).

        Returns:
            A list of Game instances.
        """
        cursor = (
            self._collection.find({"status": str(status)})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        games: list[Game] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            games.append(Game(**doc))
        return games

    async def list_all(
        self,
        limit: int = 50,
        skip: int = 0,
    ) -> list[Game]:
        """List all games sorted by created_at descending.

        Args:
            limit: Maximum number of results (default 50).
            skip: Number of documents to skip (for pagination).

        Returns:
            A list of Game instances.
        """
        cursor = (
            self._collection.find()
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        games: list[Game] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            games.append(Game(**doc))
        return games

    async def count_all(self) -> int:
        """Count all games in the collection.

        Returns:
            The total number of game documents.
        """
        return await self._collection.count_documents({})

    async def count_by_status(self, status: GameStatus) -> int:
        """Count games with a specific status.

        Args:
            status: The GameStatus to filter on.

        Returns:
            The number of games with the given status.
        """
        return await self._collection.count_documents(
            {"status": str(status)}
        )

    async def find_expired(self) -> list[Game]:
        """Find all OPEN games whose expires_at has passed.

        Uses the ``idx_expires_at_open_games`` partial index.

        Returns:
            A list of expired Game instances.
        """
        now = datetime.now(timezone.utc)
        cursor = self._collection.find(
            {"status": "OPEN", "expires_at": {"$lte": now}}
        )
        games: list[Game] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            games.append(Game(**doc))
        return games

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_status(
        self,
        game_id: str,
        new_status: GameStatus,
        closed_at: Optional[datetime] = None,
    ) -> bool:
        """Update a game's status (and optionally set closed_at).

        Args:
            game_id: String ObjectId of the game.
            new_status: The target GameStatus.
            closed_at: Optional datetime to record when the game was closed.

        Returns:
            True if a document was modified, False otherwise.
        """
        if not ObjectId.is_valid(game_id):
            return False

        update_fields: dict = {"status": str(new_status)}
        if closed_at is not None:
            update_fields["closed_at"] = closed_at

        result = await self._collection.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": update_fields},
        )
        if result.modified_count > 0:
            logger.info("Game %s status updated to %s", game_id, new_status)
        return result.modified_count > 0

    async def update_bank(self, game_id: str, increments: dict) -> bool:
        """Atomically increment bank fields on a game document.

        Args:
            game_id: String ObjectId of the game.
            increments: A dict of bank field paths to increment values,
                e.g. ``{"bank.total_cash_in": 100, "bank.chips_in_play": 100}``.

        Returns:
            True if a document was modified, False otherwise.
        """
        if not ObjectId.is_valid(game_id):
            return False

        result = await self._collection.update_one(
            {"_id": ObjectId(game_id)},
            {"$inc": increments},
        )
        return result.modified_count > 0

    async def close_expired_games(self) -> int:
        """Bulk-close all OPEN games past their expires_at.

        Uses the ``idx_expires_at_open_games`` partial index.

        Returns:
            The number of games that were closed.
        """
        now = datetime.now(timezone.utc)
        result = await self._collection.update_many(
            {"status": "OPEN", "expires_at": {"$lte": now}},
            {"$set": {"status": "CLOSED", "closed_at": now}},
        )
        if result.modified_count > 0:
            logger.info("Auto-closed %d expired games", result.modified_count)
        return result.modified_count

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, game_id: str) -> bool:
        """Delete a game document by its MongoDB ``_id``.

        Args:
            game_id: String representation of the ObjectId.

        Returns:
            True if a document was deleted, False otherwise.
        """
        if not ObjectId.is_valid(game_id):
            return False

        result = await self._collection.delete_one({"_id": ObjectId(game_id)})
        if result.deleted_count > 0:
            logger.info("Deleted game %s", game_id)
        return result.deleted_count > 0
