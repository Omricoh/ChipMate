"""Game route handlers.

Endpoints:
    POST /api/games                     -- Create a new game.
    GET  /api/games/{game_id}           -- Get game details.
    GET  /api/games/code/{game_code}    -- Look up game by code (public).
    POST /api/games/{game_id}/join      -- Join a game.
    GET  /api/games/{game_id}/players   -- List all players in a game.
    GET  /api/games/{game_id}/status    -- Get game status with bankroll.
    GET  /api/games/{game_code}/qr      -- Generate QR code PNG.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Response, status, Request
from pydantic import BaseModel, Field

from app.auth.dependencies import get_admin_or_player
from app.config import settings
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.dal.chip_requests_dal import ChipRequestDAL
from app.services.game_service import GameService

logger = logging.getLogger("chipmate.routes.games")

router = APIRouter(prefix="/games", tags=["Games"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> GameService:
    """Build a GameService wired to the current database."""
    db = get_database()
    return GameService(GameDAL(db), PlayerDAL(db), ChipRequestDAL(db))


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class CreateGameRequest(BaseModel):
    """Request body for POST /api/games."""
    manager_name: str = Field(
        ..., min_length=2, max_length=30,
        description="Display name for the game manager (2-30 characters).",
    )


class CreateGameResponse(BaseModel):
    """Response for POST /api/games."""
    game_id: str
    game_code: str
    player_token: str
    manager_name: str
    manager_player_id: str
    created_at: str


class GameCodeLookupResponse(BaseModel):
    """Response for GET /api/games/code/{game_code}."""
    game_id: str
    game_code: str
    status: str
    manager_name: Optional[str] = None
    player_count: int = 0
    can_join: bool = True


class JoinGameRequest(BaseModel):
    """Request body for POST /api/games/{game_id}/join."""
    player_name: str = Field(
        ..., min_length=2, max_length=30,
        description="Display name for the joining player (2-30 characters).",
    )


class GameInfo(BaseModel):
    """Game information included in join response."""
    game_id: str
    game_code: str
    manager_name: Optional[str]
    status: str


class JoinGameResponse(BaseModel):
    """Response for POST /api/games/{game_id}/join."""
    player_id: str
    player_token: str
    game: GameInfo


class PlayerInfo(BaseModel):
    """A single player entry in the players list response."""
    player_id: str
    name: str
    is_manager: bool
    is_active: bool
    credits_owed: int
    checked_out: bool
    joined_at: str
    total_cash_in: int
    total_credit_in: int
    current_chips: int


class PlayersListResponse(BaseModel):
    """Response for GET /api/games/{game_id}/players."""
    players: list[PlayerInfo]
    total_count: int


class GameDetailResponse(BaseModel):
    """Response for GET /api/games/{game_id}."""
    game_id: str
    game_code: str
    status: str
    manager_player_token: str
    created_at: str
    closed_at: Optional[str] = None
    expires_at: str
    player_count: int = 0


# ---------------------------------------------------------------------------
# POST /api/games -- Create a new game
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=CreateGameResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new game",
)
async def create_game(body: CreateGameRequest) -> CreateGameResponse:
    """Create a new game. The creator becomes the manager.

    No authentication required -- anyone can create a game.
    """
    service = _get_service()
    result = await service.create_game(manager_name=body.manager_name)
    return CreateGameResponse(**result)


# ---------------------------------------------------------------------------
# GET /api/games/code/{game_code} -- Public game lookup by code
# ---------------------------------------------------------------------------

@router.get(
    "/code/{game_code}",
    response_model=GameCodeLookupResponse,
    summary="Look up game by code (public)",
)
async def get_game_by_code(
    game_code: str = Path(..., min_length=6, max_length=6),
) -> GameCodeLookupResponse:
    """Look up a game by its 6-character join code. No auth required.

    Used by the join screen to display game info before joining.
    """
    service = _get_service()
    game = await service.get_game_by_code(game_code)

    # Fetch the manager player record to get manager display name
    db = get_database()
    player_dal = PlayerDAL(db)
    manager = await player_dal.get_by_token(str(game.id), game.manager_player_token)
    manager_name = manager.display_name if manager else None

    # Count players
    players = await player_dal.get_by_game(str(game.id), include_inactive=False)
    player_count = len(players)

    can_join = game.status == "OPEN"

    return GameCodeLookupResponse(
        game_id=str(game.id),
        game_code=game.code,
        status=str(game.status),
        manager_name=manager_name,
        player_count=player_count,
        can_join=can_join,
    )


# ---------------------------------------------------------------------------
# GET /api/games/{game_id} -- Get game details (auth required)
# ---------------------------------------------------------------------------

@router.get(
    "/{game_id}",
    response_model=GameDetailResponse,
    summary="Get game details",
)
async def get_game(
    game_id: str = Path(...),
    auth_ctx: dict[str, Any] = Depends(get_admin_or_player),
) -> GameDetailResponse:
    """Get game details by ID. Requires player token or admin JWT."""
    service = _get_service()
    game = await service.get_game(game_id)

    # Count active players
    db = get_database()
    player_dal = PlayerDAL(db)
    players = await player_dal.get_by_game(str(game.id), include_inactive=False)
    player_count = len(players)

    created_at_str = (
        game.created_at.isoformat()
        if hasattr(game.created_at, "isoformat")
        else str(game.created_at)
    )
    closed_at_str = (
        game.closed_at.isoformat()
        if game.closed_at and hasattr(game.closed_at, "isoformat")
        else None
    )
    expires_at_str = (
        game.expires_at.isoformat()
        if hasattr(game.expires_at, "isoformat")
        else str(game.expires_at)
    )

    return GameDetailResponse(
        game_id=str(game.id),
        game_code=game.code,
        status=str(game.status),
        manager_player_token=game.manager_player_token,
        created_at=created_at_str,
        closed_at=closed_at_str,
        expires_at=expires_at_str,
        player_count=player_count,
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/join -- Join a game
# ---------------------------------------------------------------------------

@router.post(
    "/{game_id}/join",
    response_model=JoinGameResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join a game",
)
async def join_game(
    body: JoinGameRequest,
    game_id: str = Path(...),
) -> JoinGameResponse:
    """Join a game. No auth required.

    The game must be OPEN. Returns a player token on success.
    """
    service = _get_service()
    result = await service.join_game(game_id=game_id, player_name=body.player_name)
    return JoinGameResponse(**result)


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/players -- List players (auth required)
# ---------------------------------------------------------------------------

@router.get(
    "/{game_id}/players",
    response_model=PlayersListResponse,
    summary="List all players in a game",
)
async def list_players(
    game_id: str = Path(...),
    auth_ctx: dict[str, Any] = Depends(get_admin_or_player),
) -> PlayersListResponse:
    """List all players in a game. Requires player token or admin JWT."""
    service = _get_service()
    players = await service.get_game_players_summary(game_id)

    player_infos = []
    for p in players:
        joined_at_str = (
            p["joined_at"].isoformat()
            if hasattr(p["joined_at"], "isoformat")
            else str(p["joined_at"])
        )
        player_infos.append(
            PlayerInfo(
                player_id=p["player_id"],
                name=p["name"],
                is_manager=p["is_manager"],
                is_active=p["is_active"],
                credits_owed=p["credits_owed"],
                checked_out=p["checked_out"],
                joined_at=joined_at_str,
                total_cash_in=p["total_cash_in"],
                total_credit_in=p["total_credit_in"],
                current_chips=p["current_chips"],
            )
        )

    return PlayersListResponse(
        players=player_infos,
        total_count=len(player_infos),
    )


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/status -- Game status with bankroll
# ---------------------------------------------------------------------------

@router.get(
    "/{game_id}/status",
    summary="Get game status with bankroll summary",
)
async def get_game_status(
    game_id: str = Path(...),
    auth_ctx: dict[str, Any] = Depends(get_admin_or_player),
) -> dict[str, Any]:
    """Get comprehensive game status including bankroll summary.

    Requires player token or admin JWT.
    """
    service = _get_service()
    return await service.get_game_status(game_id)


# ---------------------------------------------------------------------------
# GET /api/games/{game_code}/qr -- QR code PNG
# ---------------------------------------------------------------------------

@router.get(
    "/{game_code}/qr",
    summary="Generate QR code for game join URL",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "QR code PNG image",
        }
    },
)
async def get_qr_code(
    request: Request,
    game_code: str = Path(..., min_length=6, max_length=6),
) -> Response:
    """Generate a QR code PNG for the game join URL. No auth required.

    Returns a PNG image with content-type image/png.
    """
    # Lazy import: qrcode + Pillow may not be installed in every environment
    from app.services.qr_service import generate_qr_code

    # Validate game code exists
    service = _get_service()
    await service.get_game_by_code(game_code)

    base_url = ""
    png_bytes = generate_qr_code(game_code=game_code.upper(), base_url=base_url)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=300",
        },
    )
