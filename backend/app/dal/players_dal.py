"""Player Data Access Layer -- MongoDB operations for the players collection.

Provides async CRUD and query methods for Player documents.
All ObjectId handling is transparent.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.player import Player

logger = logging.getLogger("chipmate.dal.players")

COLLECTION = "players"


class PlayerDAL:
    """Data access layer for the players collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, player: Player) -> Player:
        """Insert a new player document and return it with its generated id.

        Args:
            player: A Player model instance (id may be None).

        Returns:
            The Player with its ``id`` populated from the inserted ObjectId.
        """
        doc = player.to_mongo_dict()
        result = await self._collection.insert_one(doc)
        player.id = str(result.inserted_id)
        logger.info(
            "Created player %s (display_name=%s) in game %s",
            player.id,
            player.display_name,
            player.game_id,
        )
        return player

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        """Find a player by its MongoDB ``_id``.

        Args:
            player_id: String representation of the ObjectId.

        Returns:
            A Player instance, or None if not found.
        """
        if not ObjectId.is_valid(player_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(player_id)})
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Player(**doc)

    async def get_by_token(
        self, game_id: str, player_token: str
    ) -> Optional[Player]:
        """Find a player by game_id and player_token.

        Uses the ``uq_game_player_token`` unique compound index.

        Args:
            game_id: String representation of the game's ObjectId.
            player_token: The player's UUID token.

        Returns:
            A Player instance, or None if not found.
        """
        doc = await self._collection.find_one(
            {"game_id": game_id, "player_token": player_token}
        )
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Player(**doc)

    async def get_by_token_only(self, player_token: str) -> Optional[Player]:
        """Find the most recent player document for a given token.

        Uses the ``idx_player_token`` index. Useful for the reconnect flow
        where the client only has a stored token.

        Args:
            player_token: The player's UUID token.

        Returns:
            A Player instance, or None if not found.
        """
        doc = await self._collection.find_one(
            {"player_token": player_token},
            sort=[("joined_at", -1)],
        )
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return Player(**doc)

    async def get_by_game(
        self,
        game_id: str,
        include_inactive: bool = False,
    ) -> list[Player]:
        """List all players in a game.

        Uses the left prefix of the ``uq_game_player_token`` index.

        Args:
            game_id: String representation of the game's ObjectId.
            include_inactive: If False, only return active players.

        Returns:
            A list of Player instances.
        """
        query: dict[str, Any] = {"game_id": game_id}
        if not include_inactive:
            query["is_active"] = True

        cursor = self._collection.find(query).sort("joined_at", 1)
        players: list[Player] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            players.append(Player(**doc))
        return players

    async def count_all(self) -> int:
        """Count all players in the collection.

        Returns:
            The total number of player documents.
        """
        return await self._collection.count_documents({})

    async def get_checked_out_count(self, game_id: str) -> int:
        """Count how many players in a game have been checked out.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            The number of checked-out players.
        """
        return await self._collection.count_documents(
            {"game_id": game_id, "checked_out": True}
        )

    async def get_credit_players_ordered(self, game_id: str) -> list[Player]:
        """Get players with outstanding credits, ordered by credits_owed desc.

        Used during settlement to determine checkout priority.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            A list of Player instances with credits_owed > 0,
            ordered from highest to lowest debt.
        """
        cursor = self._collection.find(
            {"game_id": game_id, "credits_owed": {"$gt": 0}}
        ).sort("credits_owed", -1)
        players: list[Player] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            players.append(Player(**doc))
        return players

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(self, player_id: str, fields: dict) -> bool:
        """Update arbitrary fields on a player document.

        Args:
            player_id: String representation of the player's ObjectId.
            fields: A dict of field names to new values.

        Returns:
            True if a document was modified, False otherwise.
        """
        if not ObjectId.is_valid(player_id):
            return False

        result = await self._collection.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": fields},
        )
        return result.modified_count > 0

    async def update_by_token(
        self, game_id: str, player_token: str, fields: dict
    ) -> bool:
        """Update a player identified by game_id + player_token.

        Uses the ``uq_game_player_token`` index for an efficient targeted update.

        Args:
            game_id: String representation of the game's ObjectId.
            player_token: The player's UUID token.
            fields: A dict of field names to new values.

        Returns:
            True if a document was modified, False otherwise.
        """
        result = await self._collection.update_one(
            {"game_id": game_id, "player_token": player_token},
            {"$set": fields},
        )
        return result.modified_count > 0

    async def increment_credits(
        self, game_id: str, player_token: str, amount: int
    ) -> bool:
        """Atomically increment a player's credits_owed.

        Args:
            game_id: String representation of the game's ObjectId.
            player_token: The player's UUID token.
            amount: The value to add (can be negative for repayment).

        Returns:
            True if a document was modified, False otherwise.
        """
        result = await self._collection.update_one(
            {"game_id": game_id, "player_token": player_token},
            {"$inc": {"credits_owed": amount}},
        )
        return result.modified_count > 0

    # ------------------------------------------------------------------
    # Checkout queries
    # ------------------------------------------------------------------

    async def checkout_player(
        self,
        game_id: str,
        player_token: str,
        final_chip_count: int,
        profit_loss: int,
        checked_out_at: datetime,
    ) -> bool:
        """Set checkout fields on a player document.

        Args:
            game_id: String representation of the game's ObjectId.
            player_token: The player's UUID token.
            final_chip_count: The player's final chip count at checkout.
            profit_loss: The player's profit or loss for the session.
            checked_out_at: The timestamp when checkout occurred.

        Returns:
            True if a document was modified, False otherwise.
        """
        result = await self._collection.update_one(
            {"game_id": game_id, "player_token": player_token},
            {
                "$set": {
                    "checked_out": True,
                    "checked_out_at": checked_out_at,
                    "final_chip_count": final_chip_count,
                    "profit_loss": profit_loss,
                }
            },
        )
        if result.modified_count > 0:
            logger.info(
                "Checked out player_token=%s in game=%s (final=%d, p/l=%d)",
                player_token,
                game_id,
                final_chip_count,
                profit_loss,
            )
        return result.modified_count > 0

    async def get_checked_out_players(self, game_id: str) -> list[Player]:
        """Return all checked-out players in a game.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            A list of Player instances that have been checked out.
        """
        cursor = self._collection.find(
            {"game_id": game_id, "checked_out": True}
        ).sort("checked_out_at", -1)
        players: list[Player] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            players.append(Player(**doc))
        return players

    async def get_active_players(self, game_id: str) -> list[Player]:
        """Return all active, non-checked-out players in a game.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            A list of Player instances that are active and not checked out.
        """
        cursor = self._collection.find(
            {"game_id": game_id, "is_active": True, "checked_out": False}
        ).sort("joined_at", 1)
        players: list[Player] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            players.append(Player(**doc))
        return players

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_by_game(self, game_id: str) -> int:
        """Delete all player documents for a given game.

        Args:
            game_id: String representation of the game's ObjectId.

        Returns:
            The number of player documents deleted.
        """
        result = await self._collection.delete_many({"game_id": game_id})
        if result.deleted_count > 0:
            logger.info(
                "Deleted %d players for game %s", result.deleted_count, game_id
            )
        return result.deleted_count
