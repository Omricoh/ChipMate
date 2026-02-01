"""Checkout route handlers.

Endpoints:
    POST /api/games/{game_id}/players/{player_token}/checkout -- Checkout a single player.
"""

import logging

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_manager
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.player import Player
from app.services.checkout_service import CheckoutService

logger = logging.getLogger("chipmate.routes.checkout")

router = APIRouter(
    prefix="/games/{game_id}/players/{player_token}",
    tags=["Checkout"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service() -> CheckoutService:
    """Build a CheckoutService wired to the current database."""
    db = get_database()
    return CheckoutService(
        game_dal=GameDAL(db),
        player_dal=PlayerDAL(db),
        chip_request_dal=ChipRequestDAL(db),
        notification_dal=NotificationDAL(db),
    )


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    """Request body for POST .../checkout."""
    final_chip_count: int = Field(
        ..., ge=0,
        description="The player's final chip count at checkout (must be >= 0).",
    )


class CheckoutResponse(BaseModel):
    """Response model for a successful checkout."""
    player_id: str
    player_name: str
    final_chip_count: int
    total_buy_in: int
    profit_loss: int
    credits_owed: int
    has_debt: bool
    checked_out_at: str


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/players/{player_token}/checkout
# ---------------------------------------------------------------------------

@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Checkout a single player (manager only)",
)
async def checkout_player(
    body: CheckoutRequest,
    game_id: str = Path(...),
    player_token: str = Path(..., description="The target player's UUID token"),
    manager: Player = Depends(get_current_manager),
) -> CheckoutResponse:
    """Checkout a player from the game. Requires manager token.

    Calculates profit/loss based on approved buy-in requests,
    updates bank and player records, and sends a checkout notification.
    """
    service = _get_service()
    result = await service.checkout_player(
        game_id=game_id,
        player_token=player_token,
        final_chip_count=body.final_chip_count,
    )
    return CheckoutResponse(**result)
