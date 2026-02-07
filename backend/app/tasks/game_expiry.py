"""Background task for auto-closing expired games.

Games have an expires_at field (default 12 hours from creation).
This task periodically checks for expired games and closes them.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, NotificationType
from app.models.notification import Notification

logger = logging.getLogger("chipmate.tasks.game_expiry")

# Check for expired games every 5 minutes
CHECK_INTERVAL_SECONDS = 5 * 60

# Global task handle for cancellation
_expiry_task: Optional[asyncio.Task] = None


async def check_and_close_expired_games() -> int:
    """Check for expired games and close them.

    Returns:
        Number of games that were closed.
    """
    db = get_database()
    if db is None:
        logger.warning("Database not available, skipping expiry check")
        return 0

    game_dal = GameDAL(db)
    player_dal = PlayerDAL(db)
    notification_dal = NotificationDAL(db)

    now = datetime.now(timezone.utc)

    # Find games that are OPEN or SETTLING and have expired
    expired_games = await game_dal.get_expired_games(now)

    closed_count = 0
    for game in expired_games:
        game_id = str(game.id)

        try:
            # Close the game
            await game_dal.update_status(game_id, GameStatus.CLOSED, closed_at=now)

            # Notify all players
            players = await player_dal.get_by_game(game_id, include_inactive=False)
            for player in players:
                notification = Notification(
                    game_id=game_id,
                    player_token=player.player_token,
                    notification_type=NotificationType.GAME_CLOSED,
                    message="Game has been automatically closed due to expiry.",
                )
                await notification_dal.create(notification)

            logger.info(
                "Auto-closed expired game %s (code=%s, expired_at=%s)",
                game_id,
                game.code,
                game.expires_at.isoformat() if game.expires_at else "unknown",
            )
            closed_count += 1

        except Exception as e:
            logger.error(
                "Failed to auto-close expired game %s: %s",
                game_id,
                str(e),
            )

    if closed_count > 0:
        logger.info("Auto-closed %d expired game(s)", closed_count)

    return closed_count


async def _expiry_loop():
    """Background loop that periodically checks for expired games."""
    logger.info(
        "Game expiry checker started (interval=%ds)",
        CHECK_INTERVAL_SECONDS,
    )

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await check_and_close_expired_games()
        except asyncio.CancelledError:
            logger.info("Game expiry checker stopped")
            break
        except Exception as e:
            logger.error("Error in game expiry checker: %s", str(e))
            # Continue running despite errors
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start_expiry_checker():
    """Start the background game expiry checker task."""
    global _expiry_task

    if _expiry_task is not None and not _expiry_task.done():
        logger.warning("Game expiry checker already running")
        return

    _expiry_task = asyncio.create_task(_expiry_loop())
    logger.info("Game expiry checker task created")


def stop_expiry_checker():
    """Stop the background game expiry checker task."""
    global _expiry_task

    if _expiry_task is not None and not _expiry_task.done():
        _expiry_task.cancel()
        logger.info("Game expiry checker task cancelled")
    _expiry_task = None
