"""Settlement route handlers.

Endpoints:
    POST /api/games/{game_id}/settle                              -- Start settling (OPEN -> SETTLING).
    POST /api/games/{game_id}/checkout-all                        -- Batch checkout all active players.
    POST /api/games/{game_id}/players/{player_token}/settle-debt  -- Settle a player's credit debt.
    POST /api/games/{game_id}/close                               -- Close a SETTLING game.
    POST /api/games/{game_id}/settlement/finalize                 -- Finalize and close (requires all debts settled).
    GET  /api/games/{game_id}/settlement/report                   -- Export game report (JSON or CSV).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_manager
from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.game import Bank, GameResponse
from app.models.player import Player
from app.services.settlement_service import SettlementService

logger = logging.getLogger("chipmate.routes.settlement")

router = APIRouter(prefix="/games/{game_id}", tags=["Settlement"])


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
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class SettleGameResponse(BaseModel):
    """Response for POST /api/games/{game_id}/settle."""
    game_id: str
    status: str
    message: str


class PlayerChipEntry(BaseModel):
    """A single player's final chip count in the checkout-all request."""
    player_id: str = Field(
        ..., description="The player_token identifying the player."
    )
    final_chip_count: int = Field(
        ..., ge=0, description="Final chip count (must be >= 0)."
    )


class CheckoutAllRequest(BaseModel):
    """Request body for POST /api/games/{game_id}/checkout-all."""
    player_chips: list[PlayerChipEntry] = Field(
        ..., min_length=1,
        description="Final chip counts for all active players.",
    )


class CheckedOutPlayer(BaseModel):
    """A single player entry in the checkout-all response."""
    player_id: str
    player_name: str
    final_chip_count: int
    profit_loss: int
    has_debt: bool


class CheckoutSummary(BaseModel):
    """Summary section of the checkout-all response."""
    total_checked_out: int
    debt_players_count: int
    total_profit: int
    total_loss: int


class CheckoutAllResponse(BaseModel):
    """Response for POST /api/games/{game_id}/checkout-all."""
    checked_out: list[CheckedOutPlayer]
    summary: CheckoutSummary


class SettleDebtResponse(BaseModel):
    """Response for POST /api/games/{game_id}/players/{player_token}/settle-debt."""
    player_id: str
    player_name: str
    previous_credits_owed: int
    credits_owed: int
    settled: bool
    allocations: list[dict[str, Any]]


class SettleDebtAllocation(BaseModel):
    """Allocation entry for settling a player's debt."""
    recipient_token: str = Field(..., description="Recipient player token.")
    amount: int = Field(..., gt=0, description="Amount allocated to recipient.")


class SettleDebtRequest(BaseModel):
    """Request body for settling a player's debt with allocations."""
    allocations: list[SettleDebtAllocation] = Field(
        ..., min_length=1, description="Allocation recipients and amounts."
    )


class CloseGameSummary(BaseModel):
    """Summary section of the close-game response."""
    total_players: int
    total_profit: int
    total_loss: int
    unsettled_debts: int


class CloseGameResponse(BaseModel):
    """Response for POST /api/games/{game_id}/close."""
    game_id: str
    status: str
    closed_at: str
    summary: CloseGameSummary


class FinalizeGameResponse(BaseModel):
    """Response for POST /api/games/{game_id}/settlement/finalize."""
    game_id: str
    status: str
    closed_at: str
    summary: CloseGameSummary


class ReportPlayerRow(BaseModel):
    """A single player row in the settlement report."""
    player_name: str
    is_manager: bool
    total_buy_in: int
    final_chips: int
    profit_loss: int
    credits_owed: int
    checked_out: bool


class SettlementReportResponse(BaseModel):
    """Response for GET /api/games/{game_id}/settlement/report (JSON format)."""
    format: str
    data: list[ReportPlayerRow]


class PlayerSummary(BaseModel):
    """Individual player summary in settlement response."""
    player_token: str
    display_name: str
    is_manager: bool
    is_active: bool
    checked_out: bool
    total_buy_in: int
    final_chip_count: Optional[int] = None
    profit_loss: Optional[int] = None
    credits_owed: int


class DebtorInfo(BaseModel):
    """A player with outstanding debt."""
    player_token: str
    display_name: str
    credits_owed: int
    checked_out: bool


class RecipientInfo(BaseModel):
    """A player eligible to receive debt payments (has positive profit)."""
    player_token: str
    display_name: str
    profit: int


class SettlementSummaryResponse(BaseModel):
    """Response for GET /api/games/{game_id}/settlement/summary."""
    game_id: str
    game_status: str
    game_code: str
    players: list[PlayerSummary]
    debtors: list[DebtorInfo]
    recipients: list[RecipientInfo]
    total_outstanding_debt: int
    all_debts_settled: bool


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/summary -- Settlement summary
# ---------------------------------------------------------------------------

@router.get(
    "/settlement/summary",
    response_model=SettlementSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get settlement summary for a game",
)
async def get_settlement_summary(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> SettlementSummaryResponse:
    """Get a comprehensive summary of the settlement state.

    Returns game status, player checkout status with P/L and credits owed,
    debtors paired with potential recipients, and overall debt totals.
    Requires manager token.
    """
    service = _get_service()
    result = await service.get_settlement_summary(game_id=game_id)

    return SettlementSummaryResponse(
        game_id=result["game_id"],
        game_status=result["game_status"],
        game_code=result["game_code"],
        players=[PlayerSummary(**p) for p in result["players"]],
        debtors=[DebtorInfo(**d) for d in result["debtors"]],
        recipients=[RecipientInfo(**r) for r in result["recipients"]],
        total_outstanding_debt=result["total_outstanding_debt"],
        all_debts_settled=result["all_debts_settled"],
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settle -- Start settling
# ---------------------------------------------------------------------------

@router.post(
    "/settle",
    response_model=SettleGameResponse,
    status_code=status.HTTP_200_OK,
    summary="Start settling a game (OPEN -> SETTLING)",
)
async def settle_game(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> SettleGameResponse:
    """Transition game from OPEN to SETTLING.

    Declines all pending chip requests and notifies all players.
    Requires manager token.
    """
    service = _get_service()
    game = await service.start_settling(game_id=game_id)

    return SettleGameResponse(
        game_id=str(game.id),
        status=str(game.status),
        message="Game is now settling. All pending chip requests have been declined.",
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/checkout-all -- Batch checkout
# ---------------------------------------------------------------------------

@router.post(
    "/checkout-all",
    response_model=CheckoutAllResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch checkout all active players",
)
async def checkout_all(
    body: CheckoutAllRequest,
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> CheckoutAllResponse:
    """Batch checkout all active players with final chip counts.

    Calculates P/L for each player, flags credit-debt players,
    updates bank totals, and sends notifications. Requires manager token.
    """
    service = _get_service()

    # Convert Pydantic models to dicts for the service
    player_chips_dicts = [
        {
            "player_id": entry.player_id,
            "final_chip_count": entry.final_chip_count,
        }
        for entry in body.player_chips
    ]

    result = await service.checkout_all_players(
        game_id=game_id,
        player_chips=player_chips_dicts,
    )

    # Build typed response
    checked_out = [
        CheckedOutPlayer(**player_data)
        for player_data in result["checked_out"]
    ]
    summary = CheckoutSummary(**result["summary"])

    return CheckoutAllResponse(
        checked_out=checked_out,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/players/{player_token}/settle-debt
# ---------------------------------------------------------------------------

@router.post(
    "/players/{player_token}/settle-debt",
    response_model=SettleDebtResponse,
    status_code=status.HTTP_200_OK,
    summary="Settle a player's credit debt",
)
async def settle_debt(
    body: SettleDebtRequest,
    game_id: str = Path(...),
    player_token: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> SettleDebtResponse:
    """Mark a player's credit debt as settled (set credits_owed to 0).

    The player must be checked out and have outstanding debt.
    Requires manager token.
    """
    service = _get_service()
    result = await service.settle_player_debt(
        game_id=game_id,
        player_token=player_token,
        allocations=[
            {"recipient_token": a.recipient_token, "amount": a.amount}
            for a in body.allocations
        ],
    )
    return SettleDebtResponse(**result)


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/close -- Close game
# ---------------------------------------------------------------------------

@router.post(
    "/close",
    response_model=CloseGameResponse,
    status_code=status.HTTP_200_OK,
    summary="Close a SETTLING game",
)
async def close_game(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> CloseGameResponse:
    """Close a game that is in SETTLING status.

    All active players must be checked out. Unsettled debts are allowed
    but reported in the summary. Requires manager token.
    """
    service = _get_service()
    result = await service.close_game(game_id=game_id)

    return CloseGameResponse(
        game_id=result["game_id"],
        status=result["status"],
        closed_at=result["closed_at"],
        summary=CloseGameSummary(**result["summary"]),
    )


# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/settlement/finalize -- Finalize and close game
# ---------------------------------------------------------------------------

@router.post(
    "/settlement/finalize",
    response_model=FinalizeGameResponse,
    status_code=status.HTTP_200_OK,
    summary="Finalize and close a game (requires all debts settled)",
)
async def finalize_settlement(
    game_id: str = Path(...),
    manager: Player = Depends(get_current_manager),
) -> FinalizeGameResponse:
    """Finalize and close a game that is in SETTLING status.

    Unlike the regular close endpoint, this requires all players to have
    zero credits_owed (all debts must be settled first).
    All active players must also be checked out. Requires manager token.
    """
    service = _get_service()
    result = await service.finalize_settlement(game_id=game_id)

    return FinalizeGameResponse(
        game_id=result["game_id"],
        status=result["status"],
        closed_at=result["closed_at"],
        summary=CloseGameSummary(**result["summary"]),
    )


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/settlement/report -- Export game report
# ---------------------------------------------------------------------------

@router.get(
    "/settlement/report",
    status_code=status.HTTP_200_OK,
    summary="Export settlement report (JSON or CSV)",
    responses={
        200: {
            "description": "Settlement report in requested format",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/SettlementReportResponse"}
                },
                "text/csv": {
                    "schema": {"type": "string"}
                },
            },
        },
    },
)
async def get_settlement_report(
    game_id: str = Path(...),
    format: str = Query(
        default="json",
        description="Output format: 'json' or 'csv'",
        pattern="^(json|csv)$",
    ),
    manager: Player = Depends(get_current_manager),
):
    """Export a settlement report for the game.

    Returns player data including name, manager status, total buy-in,
    final chips, profit/loss, credits owed, and checkout status.

    Requires manager token.
    """
    service = _get_service()
    result = await service.get_settlement_report(game_id=game_id, report_format=format)

    if result["format"] == "csv":
        return PlainTextResponse(
            content=result["data"],
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=settlement_{game_id}.csv"},
        )

    # JSON format
    return SettlementReportResponse(
        format=result["format"],
        data=[ReportPlayerRow(**row) for row in result["data"]],
    )
