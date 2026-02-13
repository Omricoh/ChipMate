"""Settlement business logic service.

Handles the checkout/settlement flow: start settling, freeze buy-ins,
player chip submissions, manager validation, distribution, and game close.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import CheckoutStatus, GameStatus, RequestType

logger = logging.getLogger("chipmate.services.settlement")


class SettlementService:
    """Service layer for settlement/checkout operations."""

    def __init__(
        self,
        game_dal: GameDAL,
        player_dal: PlayerDAL,
        chip_request_dal: ChipRequestDAL,
        notification_dal: NotificationDAL,
    ) -> None:
        self._game_dal = game_dal
        self._player_dal = player_dal
        self._chip_request_dal = chip_request_dal
        self._notification_dal = notification_dal

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_game_or_404(self, game_id: str):
        """Fetch a game by ID, raising 404 if not found."""
        game = await self._game_dal.get_by_id(game_id)
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )
        return game

    async def _compute_player_totals(
        self, game_id: str, player_token: str
    ) -> dict[str, int]:
        """Compute total cash/credit buy-ins for a player from approved/edited requests.

        Uses the ChipRequest.effective_amount property which returns:
        - amount for APPROVED requests
        - edited_amount for EDITED requests
        - 0 for PENDING/DECLINED requests
        """
        requests = await self._chip_request_dal.get_by_player(
            game_id, player_token, limit=10000
        )
        total_cash_in = 0
        total_credit_in = 0

        for req in requests:
            amount = req.effective_amount
            if amount <= 0:
                continue
            if req.request_type == RequestType.CASH:
                total_cash_in += amount
            else:
                total_credit_in += amount

        return {
            "total_cash_in": total_cash_in,
            "total_credit_in": total_credit_in,
        }

    # ------------------------------------------------------------------
    # Start settling
    # ------------------------------------------------------------------

    async def start_settling(self, game_id: str) -> dict:
        """Transition game from OPEN to SETTLING and freeze all buy-in data.

        Steps:
        1. Validate game is OPEN
        2. Decline all pending chip requests
        3. Freeze each player's buy-in data and set checkout_status to PENDING
        4. Compute cash_pool from total cash buy-ins
        5. Update game: status=SETTLING, settlement_state, frozen_at, cash_pool

        Returns:
            Dict with game_id, status, cash_pool, player_count.
        """
        game = await self._get_game_or_404(game_id)

        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Game must be in OPEN state to start settling",
            )

        # Decline all pending chip requests
        await self._chip_request_dal.decline_all_pending(game_id)

        # Get all active players and freeze their buy-in data
        players = await self._player_dal.get_active_players(game_id)
        total_cash_pool = 0

        for player in players:
            totals = await self._compute_player_totals(
                game_id, player.player_token
            )
            cash_in = totals["total_cash_in"]
            credit_in = totals["total_credit_in"]

            frozen = {
                "total_cash_in": cash_in,
                "total_credit_in": credit_in,
                "total_buy_in": cash_in + credit_in,
            }

            await self._player_dal.update_by_token(
                game_id,
                player.player_token,
                {
                    "frozen_buy_in": frozen,
                    "checkout_status": str(CheckoutStatus.PENDING),
                },
            )
            total_cash_pool += cash_in

        now = datetime.now(timezone.utc)

        # Update game status and settlement fields
        await self._game_dal.update_status(game_id, GameStatus.SETTLING)
        await self._game_dal.update(game_id, {
            "settlement_state": "SETTLING_CHIP_COUNT",
            "cash_pool": total_cash_pool,
            "frozen_at": now,
        })

        return {
            "game_id": game_id,
            "status": "SETTLING",
            "cash_pool": total_cash_pool,
            "player_count": len(players),
        }
