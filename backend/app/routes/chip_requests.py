"""Chip request route handlers.

Endpoints:
    POST /api/games/{game_id}/requests                        -- Create chip request.
    GET  /api/games/{game_id}/requests/pending                -- Get pending requests (manager).
    GET  /api/games/{game_id}/requests/mine                   -- Get player's request history.
    POST /api/games/{game_id}/requests/{request_id}/approve   -- Approve request (manager).
    POST /api/games/{game_id}/requests/{request_id}/decline   -- Decline request (manager).
    POST /api/games/{game_id}/requests/{request_id}/edit      -- Edit and approve (manager).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field

from app.auth.dependencies import (
    get_admin_or_player,
    get_current_manager,
    get_current_player,
)
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import RequestType
from app.models.player import Player
from app.services.request_service import RequestService

logger = logging.getLogger("chipmate.routes.chip_requests")

router = APIRouter(prefix="/games/{game_id}/requests", tags=["Chip Requests"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> RequestService:
    """Build a RequestService wired to the current database."""
    db = get_database()
    return RequestService(
        game_dal=GameDAL(db),
        player_dal=PlayerDAL(db),
        chip_request_dal=ChipRequestDAL(db),
        notification_dal=NotificationDAL(db),
    )


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class CreateChipRequestBody(BaseModel):
    """Request body for POST /api/games/{game_id}/requests."""
    request_type: RequestType
    amount: int = Field(..., gt=0, description="Number of chips requested.")
    on_behalf_of_token: Optional[str] = Field(
        default=None,
        description="If set, create request on behalf of this player.",
    )
    on_behalf_of_player_id: Optional[str] = Field(
        default=None,
        description="Legacy alias for on_behalf_of_token.",
    )


class EditRequestBody(BaseModel):
    """Request body for POST .../requests/{request_id}/edit."""
    new_amount: int = Field(..., gt=0, description="Manager-adjusted chip amount.")
    new_type: Optional[RequestType] = Field(
        default=None,
        description="Optional new request type (CASH or CREDIT).",
    )


class ChipRequestOut(BaseModel):
    """Response model for a single chip request."""
    id: str
    game_id: str
    player_token: str
    requested_by: str
    player_name: Optional[str] = None
    request_type: RequestType
    amount: int
    status: str
    edited_amount: Optional[int] = None
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _to_response(chip_request, player_name: Optional[str] = None) -> ChipRequestOut:
    """Convert a ChipRequest domain model to the route response model."""
    created_at_str = (
        chip_request.created_at.isoformat()
        if hasattr(chip_request.created_at, "isoformat")
        else str(chip_request.created_at)
    )
    resolved_at_str = (
        chip_request.resolved_at.isoformat()
        if chip_request.resolved_at
        and hasattr(chip_request.resolved_at, "isoformat")
        else None
    )
    return ChipRequestOut(
        id=str(chip_request.id),
        game_id=chip_request.game_id,
        player_token=chip_request.player_token,
        requested_by=chip_request.requested_by,
        player_name=player_name,
        request_type=chip_request.request_type,
        amount=chip_request.amount,
        status=str(chip_request.status),
        edited_amount=chip_request.edited_amount,
        created_at=created_at_str,
        resolved_at=resolved_at_str,
        resolved_by=chip_request.resolved_by,
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests -- Create chip request
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ChipRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chip buy-in request",
)
async def create_chip_request(
    body: CreateChipRequestBody,
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> ChipRequestOut:
    """Create a chip buy-in request. Requires player token."""
    service = _get_service()
    on_behalf_of_token = body.on_behalf_of_token or body.on_behalf_of_player_id
    chip_request = await service.create_request(
        game_id=game_id,
        player_token=player.player_token,
        request_type=body.request_type,
        amount=body.amount,
        on_behalf_of_token=on_behalf_of_token,
    )
    return _to_response(chip_request)


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/pending -- Pending requests (manager)
# ---------------------------------------------------------------------------

@router.get(
    "/pending",
    response_model=list[ChipRequestOut],
    summary="Get pending chip requests (manager only)",
)
async def get_pending_requests(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> list[ChipRequestOut]:
    """Get all pending chip requests for the game. Requires manager token."""
    service = _get_service()
    requests = await service.get_pending_requests(game_id=game_id)

    # Build a mapping from player_token to display_name
    db = get_database()
    player_dal = PlayerDAL(db)
    players = await player_dal.get_by_game(game_id, include_inactive=True)
    token_to_name = {p.player_token: p.display_name for p in players}

    return [
        _to_response(r, player_name=token_to_name.get(r.player_token))
        for r in requests
    ]


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/mine -- Player request history
# ---------------------------------------------------------------------------

@router.get(
    "/mine",
    response_model=list[ChipRequestOut],
    summary="Get player chip request history",
)
async def get_my_requests(
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> list[ChipRequestOut]:
    """Get the authenticated player's chip request history."""
    service = _get_service()
    requests = await service.get_player_requests(
        game_id=game_id,
        player_token=player.player_token,
    )
    return [_to_response(r) for r in requests]


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/history -- Full request history
# ---------------------------------------------------------------------------

@router.get(
    "/history",
    response_model=list[ChipRequestOut],
    summary="Get chip request history (manager sees all, player sees own)",
)
async def get_request_history(
    game_id: str = Path(...),
    auth_ctx: dict[str, Any] = Depends(get_admin_or_player),
) -> list[ChipRequestOut]:
    """Get chip request history for the game.

    Managers and admins see all requests. Regular players see only their own.
    Returns all statuses (PENDING, APPROVED, DECLINED, EDITED), sorted by
    created_at descending (newest first).
    """
    service = _get_service()

    # Determine if caller can see all requests or only their own
    if auth_ctx["auth_type"] in ("admin", "manager"):
        # Manager or admin: see all requests
        requests = await service.get_request_history(game_id=game_id)
    else:
        # Regular player: see only own requests
        player = auth_ctx["player"]
        requests = await service.get_request_history(
            game_id=game_id,
            player_token=player.player_token,
        )

    # Build player name mapping
    db = get_database()
    player_dal = PlayerDAL(db)
    players = await player_dal.get_by_game(game_id, include_inactive=True)
    token_to_name = {p.player_token: p.display_name for p in players}

    return [
        _to_response(r, player_name=token_to_name.get(r.player_token))
        for r in requests
    ]


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/requests/{request_id} -- Single request detail
# ---------------------------------------------------------------------------

@router.get(
    "/{request_id}",
    response_model=ChipRequestOut,
    summary="Get a single chip request by ID",
)
async def get_request_by_id(
    game_id: str = Path(...),
    request_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> ChipRequestOut:
    """Get details for a single chip request.

    Any authenticated player in the game can view request details.
    """
    service = _get_service()
    chip_request = await service.get_request_by_id(
        game_id=game_id,
        request_id=request_id,
    )

    # Get player name for the response
    db = get_database()
    player_dal = PlayerDAL(db)
    request_player = await player_dal.get_by_token(
        game_id, chip_request.player_token
    )
    player_name = request_player.display_name if request_player else None

    return _to_response(chip_request, player_name=player_name)


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/approve
# ---------------------------------------------------------------------------

@router.post(
    "/{request_id}/approve",
    response_model=ChipRequestOut,
    summary="Approve a pending chip request (manager only)",
)
async def approve_request(
    game_id: str = Path(...),
    request_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> ChipRequestOut:
    """Approve a pending chip request. Requires manager token."""
    service = _get_service()
    chip_request = await service.approve_request(
        game_id=game_id,
        request_id=request_id,
        manager_token=manager.player_token,
    )
    return _to_response(chip_request)


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/decline
# ---------------------------------------------------------------------------

@router.post(
    "/{request_id}/decline",
    response_model=ChipRequestOut,
    summary="Decline a pending chip request (manager only)",
)
async def decline_request(
    game_id: str = Path(...),
    request_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> ChipRequestOut:
    """Decline a pending chip request. Requires manager token."""
    service = _get_service()
    chip_request = await service.decline_request(
        game_id=game_id,
        request_id=request_id,
        manager_token=manager.player_token,
    )
    return _to_response(chip_request)


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/requests/{request_id}/edit -- Edit and approve
# ---------------------------------------------------------------------------

@router.post(
    "/{request_id}/edit",
    response_model=ChipRequestOut,
    summary="Edit amount and approve a chip request (manager only)",
)
async def edit_and_approve_request(
    body: EditRequestBody,
    game_id: str = Path(...),
    request_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> ChipRequestOut:
    """Edit the amount and approve a pending chip request."""
    service = _get_service()
    chip_request = await service.edit_and_approve_request(
        game_id=game_id,
        request_id=request_id,
        new_amount=body.new_amount,
        new_type=body.new_type,
        manager_token=manager.player_token,
    )
    return _to_response(chip_request)
