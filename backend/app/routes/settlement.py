"""Settlement route handlers.

Endpoints:
    POST /api/games/{game_id}/settlement/start                          -- Start settling.
    POST /api/games/{game_id}/settlement/submit-chips                   -- Player submits chip count.
    POST /api/games/{game_id}/settlement/validate-chips/{player_token}  -- Manager validates.
    POST /api/games/{game_id}/settlement/reject-chips/{player_token}    -- Manager rejects.
    POST /api/games/{game_id}/settlement/manager-input/{player_token}   -- Manager inputs on behalf.
    GET  /api/games/{game_id}/settlement/pool                           -- Get pool state.
    GET  /api/games/{game_id}/settlement/distribution                   -- Get distribution suggestion.
    PUT  /api/games/{game_id}/settlement/distribution                   -- Override distribution.
    POST /api/games/{game_id}/settlement/confirm/{player_token}         -- Confirm distribution.
    GET  /api/games/{game_id}/settlement/actions                        -- Get player actions.
    POST /api/games/{game_id}/settlement/close                          -- Close game.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_manager, get_current_player
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.player import Player
from app.services.settlement_service import SettlementService

logger = logging.getLogger("chipmate.routes.settlement")

router = APIRouter(prefix="/games/{game_id}/settlement", tags=["Settlement"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> SettlementService:
    """Build a SettlementService wired to the current database."""
    db = get_database()
    return SettlementService(
        game_dal=GameDAL(db),
        player_dal=PlayerDAL(db),
        chip_request_dal=ChipRequestDAL(db),
        notification_dal=NotificationDAL(db),
    )


# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------

class SubmitChipsBody(BaseModel):
    """Request body for POST .../settlement/submit-chips."""
    chip_count: int = Field(..., description="Number of chips the player is returning.")
    preferred_cash: int = Field(..., description="Preferred cash payout amount.")
    preferred_credit: int = Field(..., description="Preferred credit payout amount.")


class ManagerInputBody(BaseModel):
    """Request body for POST .../settlement/manager-input/{player_token}."""
    chip_count: int = Field(..., description="Number of chips the player is returning.")
    preferred_cash: int = Field(..., description="Preferred cash payout amount.")
    preferred_credit: int = Field(..., description="Preferred credit payout amount.")


class OverrideDistributionBody(BaseModel):
    """Request body for PUT .../settlement/distribution."""
    distribution: dict[str, Any] = Field(
        ..., description="Distribution dict keyed by player_token."
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/checkout-request
# ---------------------------------------------------------------------------

@router.post("/checkout-request", summary="Player requests mid-game checkout")
async def request_checkout(
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> dict:
    """Player requests mid-game checkout during OPEN state."""
    service = _get_service()
    return await service.request_midgame_checkout(game_id, player.player_token)


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/start
# ---------------------------------------------------------------------------

@router.post("/start", summary="Start settling the game (manager only)")
async def start_settling(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Transition game from OPEN to SETTLING. Requires manager token."""
    service = _get_service()
    result = await service.start_settling(game_id)
    return result


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/submit-chips
# ---------------------------------------------------------------------------

@router.post("/submit-chips", summary="Player submits chip count")
async def submit_chips(
    body: SubmitChipsBody,
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> dict:
    """Player submits their chip count and payout preferences."""
    service = _get_service()
    await service.submit_chips(
        game_id,
        player.player_token,
        body.chip_count,
        body.preferred_cash,
        body.preferred_credit,
    )
    return {"status": "submitted"}


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/validate-chips/{player_token}
# ---------------------------------------------------------------------------

@router.post(
    "/validate-chips/{player_token}",
    summary="Manager validates a player's chip count",
)
async def validate_chips(
    game_id: str = Path(...),
    player_token: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Manager validates a player's submitted chip count."""
    service = _get_service()
    await service.validate_chips(game_id, player_token)
    return {"status": "validated"}


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/reject-chips/{player_token}
# ---------------------------------------------------------------------------

@router.post(
    "/reject-chips/{player_token}",
    summary="Manager rejects a player's chip count",
)
async def reject_chips(
    game_id: str = Path(...),
    player_token: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Manager rejects a player's submitted chip count."""
    service = _get_service()
    await service.reject_chips(game_id, player_token)
    return {"status": "rejected"}


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/manager-input/{player_token}
# ---------------------------------------------------------------------------

@router.post(
    "/manager-input/{player_token}",
    summary="Manager inputs chip count on behalf of player",
)
async def manager_input(
    body: ManagerInputBody,
    game_id: str = Path(...),
    player_token: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Manager directly inputs chip count for a player and auto-validates."""
    service = _get_service()
    await service.manager_input(
        game_id,
        player_token,
        body.chip_count,
        body.preferred_cash,
        body.preferred_credit,
    )
    return {"status": "validated"}


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/pool
# ---------------------------------------------------------------------------

@router.get("/pool", summary="Get pool state (manager only)")
async def get_pool(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Get the current cash/credit pool and settlement state."""
    service = _get_service()
    game_dal = GameDAL(get_database())
    game = await game_dal.get_by_id(game_id)
    if game is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found",
        )
    return {
        "cash_pool": game.cash_pool,
        "credit_pool": game.credit_pool,
        "settlement_state": game.settlement_state,
    }


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/distribution
# ---------------------------------------------------------------------------

@router.get("/distribution", summary="Get distribution suggestion (manager only)")
async def get_distribution(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Compute and return a distribution suggestion."""
    service = _get_service()
    suggestion = await service.get_distribution_suggestion(game_id)
    return suggestion


# ---------------------------------------------------------------------------
# PUT /api/games/{game_id}/settlement/distribution
# ---------------------------------------------------------------------------

@router.put("/distribution", summary="Override distribution (manager only)")
async def override_distribution(
    body: OverrideDistributionBody,
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Manager overrides the distribution for all players."""
    service = _get_service()
    await service.override_distribution(game_id, body.distribution)
    return {"status": "distributed"}


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/confirm/{player_token}
# ---------------------------------------------------------------------------

@router.post(
    "/confirm/{player_token}",
    summary="Confirm distribution for a player (manager only)",
)
async def confirm_distribution(
    game_id: str = Path(...),
    player_token: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Confirm a player's distribution, transitioning to DONE."""
    service = _get_service()
    await service.confirm_distribution(game_id, player_token)
    return {"status": "confirmed"}


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/actions
# ---------------------------------------------------------------------------

@router.get("/actions", summary="Get player's settlement actions")
async def get_actions(
    game_id: str = Path(...),
    player: Player = Depends(get_current_player),
) -> list[dict]:
    """Get the authenticated player's settlement actions."""
    service = _get_service()
    actions = await service.get_player_actions(game_id, player.player_token)
    return actions


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/close
# ---------------------------------------------------------------------------

@router.post("/close", summary="Close the game (manager only)")
async def close_game(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> dict:
    """Close the game after all players have completed checkout."""
    service = _get_service()
    result = await service.close_game(game_id)
    return result
