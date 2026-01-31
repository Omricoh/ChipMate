"""Chip Request Data Access Layer -- MongoDB operations for the chip_requests collection.

Provides async CRUD and query methods for ChipRequest documents.
All ObjectId handling is transparent.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.chip_request import ChipRequest
from app.models.common import RequestStatus

logger = logging.getLogger("chipmate.dal.chip_requests")

COLLECTION = "chip_requests"


class ChipRequestDAL:
    """Data access layer for the chip_requests collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, chip_request: ChipRequest) -> ChipRequest:
        """Insert a new chip request document.

        Args:
            chip_request: A ChipRequest model instance (id may be None).

        Returns:
            The ChipRequest with its ``id`` populated.
        """
        doc = chip_request.to_mongo_dict()
        result = await self._collection.insert_one(doc)
        chip_request.id = str(result.inserted_id)
        logger.info(
            "Created chip request %s for player_token=%s in game=%s (type=%s, amount=%d)",
            chip_request.id,
            chip_request.player_token,
            chip_request.game_id,
            chip_request.request_type,
            chip_request.amount,
        )
        return chip_request

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, request_id: str) -> Optional[ChipRequest]:
        """Find a chip request by its MongoDB ``_id``.

        Args:
            request_id: String representation of the ObjectId.

        Returns:
            A ChipRequest instance, or None if not found.
        """
        if not ObjectId.is_valid(request_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(request_id)})
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return ChipRequest(**doc)

    async def get_pending_by_game(
        self, game_id: str, limit: int = 100
    ) -> list[ChipRequest]:
        """Get all pending requests for a game, oldest first (FIFO).

        Uses the ``idx_game_status_created`` index.

        Args:
            game_id: String representation of the game's ObjectId.
            limit: Maximum number of results.

        Returns:
            A list of pending ChipRequest instances sorted by created_at ascending.
        """
        cursor = (
            self._collection.find(
                {"game_id": game_id, "status": "PENDING"}
            )
            .sort("created_at", 1)
            .limit(limit)
        )
        requests: list[ChipRequest] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            requests.append(ChipRequest(**doc))
        return requests

    async def get_by_player(
        self,
        game_id: str,
        player_token: str,
        limit: int = 100,
    ) -> list[ChipRequest]:
        """Get all requests for a specific player in a game, newest first.

        Uses the ``idx_game_player_created`` index.

        Args:
            game_id: String representation of the game's ObjectId.
            player_token: The player's UUID token.
            limit: Maximum number of results.

        Returns:
            A list of ChipRequest instances sorted by created_at descending.
        """
        cursor = (
            self._collection.find(
                {"game_id": game_id, "player_token": player_token}
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        requests: list[ChipRequest] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            requests.append(ChipRequest(**doc))
        return requests

    async def get_by_game(
        self,
        game_id: str,
        status: Optional[RequestStatus] = None,
        limit: int = 200,
        skip: int = 0,
    ) -> list[ChipRequest]:
        """Get requests for a game with optional status filter.

        Args:
            game_id: String representation of the game's ObjectId.
            status: Optional status to filter on.
            limit: Maximum number of results.
            skip: Number of documents to skip.

        Returns:
            A list of ChipRequest instances sorted by created_at descending.
        """
        query: dict = {"game_id": game_id}
        if status is not None:
            query["status"] = str(status)

        cursor = (
            self._collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        requests: list[ChipRequest] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            requests.append(ChipRequest(**doc))
        return requests

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_status(
        self,
        request_id: str,
        new_status: RequestStatus,
        resolved_by: str,
        edited_amount: Optional[int] = None,
    ) -> bool:
        """Update the status of a chip request (approve / decline / edit).

        Uses an optimistic lock on ``status: PENDING`` to prevent double-processing.

        Args:
            request_id: String ObjectId of the chip request.
            new_status: The target RequestStatus.
            resolved_by: The player_token of the manager who resolved it.
            edited_amount: If new_status is EDITED, the adjusted amount.

        Returns:
            True if the request was successfully updated, False if it was
            already resolved or not found.
        """
        if not ObjectId.is_valid(request_id):
            return False

        now = datetime.now(timezone.utc)
        update_fields: dict = {
            "status": str(new_status),
            "resolved_at": now,
            "resolved_by": resolved_by,
        }
        if edited_amount is not None:
            update_fields["edited_amount"] = edited_amount

        result = await self._collection.update_one(
            {"_id": ObjectId(request_id), "status": "PENDING"},
            {"$set": update_fields},
        )
        if result.modified_count > 0:
            logger.info(
                "Chip request %s updated to %s by %s",
                request_id,
                new_status,
                resolved_by,
            )
        return result.modified_count > 0

    async def count_pending_by_game(self, game_id: str) -> int:
        """Count pending chip requests for a game.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            The number of pending requests.
        """
        return await self._collection.count_documents(
            {"game_id": game_id, "status": "PENDING"}
        )
