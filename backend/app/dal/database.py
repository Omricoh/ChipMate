"""MongoDB database connection management using Motor async driver.

Includes connection lifecycle and index management for all collections
as defined in the T2 MongoDB schema design.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING

from app.config import settings

logger = logging.getLogger("chipmate.dal.database")

# Global database client and database instances
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """Establish connection to MongoDB.

    Called during FastAPI application startup.
    """
    global _client, _database

    _client = AsyncIOMotorClient(
        settings.MONGO_URL,
        serverSelectionTimeoutMS=5000  # 5 second timeout
    )
    _database = _client[settings.DATABASE_NAME]

    # Verify connection by pinging the database
    await _client.admin.command("ping")
    logger.info("Connected to MongoDB: %s", settings.DATABASE_NAME)


async def close_mongo_connection() -> None:
    """Close MongoDB connection.

    Called during FastAPI application shutdown.
    """
    global _client

    if _client:
        _client.close()
        logger.info("Closed MongoDB connection")


def get_database() -> AsyncIOMotorDatabase:
    """Get the MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The database instance.

    Raises:
        RuntimeError: If database is not initialized.
    """
    if _database is None:
        raise RuntimeError(
            "Database not initialized. Call connect_to_mongo() first."
        )
    return _database


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all indexes defined in the T2 schema design.

    This is idempotent -- MongoDB silently ignores indexes that already exist.
    Should be called on application startup after the connection is established.

    Args:
        db: The Motor database instance to create indexes on.
    """
    logger.info("Ensuring indexes for all collections...")

    # --- games indexes ---
    games = db.games

    # 1. Unique game code among non-closed games (partial filter).
    # Motor/PyMongo does not support partial filter in IndexModel directly
    # through create_indexes, so we use create_index for partial indexes.
    await games.create_index(
        [("code", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["OPEN", "SETTLING"]}},
        name="uq_code_active_games",
    )

    # 2. Auto-close: find OPEN games past their expiration.
    await games.create_index(
        [("expires_at", ASCENDING)],
        partialFilterExpression={"status": "OPEN"},
        name="idx_expires_at_open_games",
    )

    # 3. Status filter for listing queries.
    await games.create_index(
        [("status", ASCENDING), ("created_at", DESCENDING)],
        name="idx_status_created",
    )

    # --- players indexes ---
    players = db.players

    # 1. Primary lookup: find a specific player in a game (unique).
    await players.create_index(
        [("game_id", ASCENDING), ("player_token", ASCENDING)],
        unique=True,
        name="uq_game_player_token",
    )

    # 2. Token-only lookup: find which game(s) a token belongs to.
    await players.create_index(
        [("player_token", ASCENDING)],
        name="idx_player_token",
    )

    # --- chip_requests indexes ---
    chip_requests = db.chip_requests

    # 1. Manager polls pending requests for a game.
    await chip_requests.create_index(
        [("game_id", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)],
        name="idx_game_status_created",
    )

    # 2. Player fetches own activity.
    await chip_requests.create_index(
        [("game_id", ASCENDING), ("player_token", ASCENDING), ("created_at", DESCENDING)],
        name="idx_game_player_created",
    )

    # --- notifications indexes ---
    notifications = db.notifications

    # 1. Player polls unread notifications.
    await notifications.create_index(
        [
            ("player_token", ASCENDING),
            ("game_id", ASCENDING),
            ("is_read", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="idx_player_game_unread",
    )

    # 2. TTL: auto-delete old notifications after 48 hours.
    await notifications.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=172800,  # 48 hours
        name="ttl_notifications_48h",
    )

    logger.info("All indexes ensured successfully.")
