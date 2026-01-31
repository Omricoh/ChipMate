"""Data Access Layer -- MongoDB repository classes and connection management."""

from app.dal.database import (
    connect_to_mongo,
    close_mongo_connection,
    ensure_indexes,
    get_database,
)
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.notifications_dal import NotificationDAL

__all__ = [
    # Connection management
    "connect_to_mongo",
    "close_mongo_connection",
    "ensure_indexes",
    "get_database",
    # DAL classes
    "GameDAL",
    "PlayerDAL",
    "ChipRequestDAL",
    "NotificationDAL",
]
