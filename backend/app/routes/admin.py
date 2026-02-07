"""Admin route handlers.

Endpoints:
    GET    /api/admin/games                       -- List all games (admin).
    GET    /api/admin/games/{game_id}             -- Get detailed game info (admin).
    POST   /api/admin/games/{game_id}/force-close -- Force close a game (admin).
    POST   /api/admin/games/{game_id}/impersonate -- Get manager token for game (admin).
    DELETE /api/admin/games/{game_id}             -- Delete a game and all data (admin).
    GET    /api/admin/stats                       -- Dashboard statistics (admin).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_admin
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus
from app.services.admin_service import AdminService

logger = logging.getLogger("chipmate.routes.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> AdminService:
    """Build an AdminService wired to the current database."""
    db = get_database()
    return AdminService(
        game_dal=GameDAL(db),
        player_dal=PlayerDAL(db),
        chip_request_dal=ChipRequestDAL(db),
        notification_dal=NotificationDAL(db),
    )


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class BankSummary(BaseModel):
    """Bank summary in game list responses."""
    cash_balance: int
    total_cash_in: int
    total_cash_out: int
    chips_in_play: int


class GameListItem(BaseModel):
    """A single game entry in the admin game list response."""
    game_id: str
    game_code: str
    status: str
    player_count: int
    bank: BankSummary
    created_at: str


class GameListResponse(BaseModel):
    """Response for GET /api/admin/games."""
    games: list[GameListItem]
    total: int


class AdminPlayerInfo(BaseModel):
    """A single player entry in the admin game detail response."""
    player_id: str
    player_token: str
    display_name: str
    is_manager: bool
    is_active: bool
    credits_owed: int
    checked_out: bool
    joined_at: str


class RequestStats(BaseModel):
    """Request statistics for a game."""
    total: int
    pending: int
    approved: int


class BankDetail(BaseModel):
    """Full bank details for game detail response."""
    cash_balance: int
    total_cash_in: int
    total_cash_out: int
    total_credits_issued: int
    total_credits_repaid: int
    total_chips_issued: int
    total_chips_returned: int
    chips_in_play: int


class GameDetailInfo(BaseModel):
    """Game information in the admin game detail response."""
    game_id: str
    game_code: str
    status: str
    manager_player_token: str
    created_at: str
    closed_at: Optional[str] = None
    expires_at: str
    bank: BankDetail


class AdminGameDetailResponse(BaseModel):
    """Response for GET /api/admin/games/{game_id}."""
    game: GameDetailInfo
    players: list[AdminPlayerInfo]
    request_stats: RequestStats


class ForceCloseResponse(BaseModel):
    """Response for POST /api/admin/games/{game_id}/force-close."""
    game_id: str
    game_code: str
    status: str
    closed_at: Optional[str] = None


class DashboardStatsResponse(BaseModel):
    """Response for GET /api/admin/stats."""
    total_games: int
    active_games: int
    settling_games: int
    closed_games: int
    total_players: int


class ImpersonateResponse(BaseModel):
    """Response for POST /api/admin/games/{game_id}/impersonate."""
    game_id: str
    game_code: str
    manager_player_token: str
    manager_name: str


class DeleteGameResponse(BaseModel):
    """Response for DELETE /api/admin/games/{game_id}."""
    game_id: str
    deleted: bool
    players_deleted: int
    requests_deleted: int
    notifications_deleted: int


# ---------------------------------------------------------------------------
# GET /api/admin/games -- List all games
# ---------------------------------------------------------------------------

@router.get(
    "/games",
    response_model=GameListResponse,
    summary="List all games (admin only)",
)
async def list_games(
    status: Optional[GameStatus] = Query(
        None, description="Filter by game status (OPEN, SETTLING, CLOSED)."
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of games to return."),
    offset: int = Query(0, ge=0, description="Number of games to skip."),
    admin: dict[str, Any] = Depends(get_current_admin),
) -> GameListResponse:
    """List all games with optional status filter. Requires admin JWT."""
    service = _get_service()
    games = await service.list_games(
        status_filter=status,
        limit=limit,
        offset=offset,
    )
    return GameListResponse(
        games=[GameListItem(**g) for g in games],
        total=len(games),
    )


# ---------------------------------------------------------------------------
# GET /api/admin/games/{game_id} -- Get detailed game info
# ---------------------------------------------------------------------------

@router.get(
    "/games/{game_id}",
    response_model=AdminGameDetailResponse,
    summary="Get detailed game info (admin only)",
)
async def get_game_detail(
    game_id: str = Path(...),
    admin: dict[str, Any] = Depends(get_current_admin),
) -> AdminGameDetailResponse:
    """Get full game details including players and request stats. Requires admin JWT."""
    service = _get_service()
    detail = await service.get_game_detail(game_id)
    return AdminGameDetailResponse(
        game=GameDetailInfo(**detail["game"]),
        players=[AdminPlayerInfo(**p) for p in detail["players"]],
        request_stats=RequestStats(**detail["request_stats"]),
    )


# ---------------------------------------------------------------------------
# POST /api/admin/games/{game_id}/force-close -- Force close a game
# ---------------------------------------------------------------------------

@router.post(
    "/games/{game_id}/force-close",
    response_model=ForceCloseResponse,
    summary="Force close a game (admin only)",
)
async def force_close_game(
    game_id: str = Path(...),
    admin: dict[str, Any] = Depends(get_current_admin),
) -> ForceCloseResponse:
    """Force close a game regardless of current status. Requires admin JWT."""
    service = _get_service()
    game = await service.force_close_game(game_id)

    closed_at_str = (
        game.closed_at.isoformat()
        if game.closed_at and hasattr(game.closed_at, "isoformat")
        else None
    )

    return ForceCloseResponse(
        game_id=str(game.id),
        game_code=game.code,
        status=str(game.status),
        closed_at=closed_at_str,
    )


# ---------------------------------------------------------------------------
# GET /api/admin/stats -- Dashboard statistics
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    summary="Dashboard statistics (admin only)",
)
async def get_dashboard_stats(
    admin: dict[str, Any] = Depends(get_current_admin),
) -> DashboardStatsResponse:
    """Get aggregate dashboard statistics. Requires admin JWT."""
    service = _get_service()
    stats = await service.get_dashboard_stats()
    return DashboardStatsResponse(**stats)


# ---------------------------------------------------------------------------
# POST /api/admin/games/{game_id}/impersonate -- Get manager token
# ---------------------------------------------------------------------------

@router.post(
    "/games/{game_id}/impersonate",
    response_model=ImpersonateResponse,
    summary="Get manager token for a game (admin only)",
)
async def impersonate_manager(
    game_id: str = Path(...),
    admin: dict[str, Any] = Depends(get_current_admin),
) -> ImpersonateResponse:
    """Get the manager's player token for a game to impersonate them.

    This is useful for admin support and debugging. The returned token
    can be used to access the game as the manager.

    Requires admin JWT.
    """
    service = _get_service()
    result = await service.get_manager_token(game_id)

    logger.info(
        "Admin %s impersonated manager for game %s",
        admin.get("username", "unknown"),
        game_id,
    )

    return ImpersonateResponse(**result)


# ---------------------------------------------------------------------------
# DELETE /api/admin/games/{game_id} -- Delete game and all data
# ---------------------------------------------------------------------------

@router.delete(
    "/games/{game_id}",
    response_model=DeleteGameResponse,
    summary="Delete a game and all associated data (admin only)",
)
async def delete_game(
    game_id: str = Path(...),
    force: bool = Query(
        False,
        description="Force delete even if game is not CLOSED.",
    ),
    admin: dict[str, Any] = Depends(get_current_admin),
) -> DeleteGameResponse:
    """Permanently delete a game and all associated data.

    By default, only CLOSED games can be deleted. Use force=true to
    delete games in any status.

    This action is irreversible. All players, chip requests, and
    notifications associated with the game will be deleted.

    Requires admin JWT.
    """
    service = _get_service()
    result = await service.delete_game(game_id, force=force)

    logger.info(
        "Admin %s deleted game %s (players=%d, requests=%d, notifications=%d)",
        admin.get("username", "unknown"),
        game_id,
        result["players_deleted"],
        result["requests_deleted"],
        result["notifications_deleted"],
    )

    return DeleteGameResponse(**result)
