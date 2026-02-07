"""Checkout business logic service.

Handles single-player checkout from a game. Calculates profit/loss,
updates bank and player records, and sends checkout notifications.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, NotificationType, RequestStatus
from app.models.notification import Notification

logger = logging.getLogger("chipmate.services.checkout")


class CheckoutService:
    """Service layer for player checkout operations."""

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

    async def _get_player_or_404(self, game_id: str, player_token: str):
        """Fetch a player by game_id + token, raising 404 if not found."""
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found in this game",
            )
        return player

    async def _compute_total_buy_in(
        self, game_id: str, player_token: str
    ) -> dict[str, int]:
        """Compute a player's total buy-in from their approved/edited requests.

        Returns a dict with total_cash_in, total_credit_in, and total_buy_in.
        Only counts requests with APPROVED or EDITED status.
        """
        requests = await self._chip_request_dal.get_by_player(
            game_id, player_token
        )

        total_cash_in = 0
        total_credit_in = 0

        for req in requests:
            if req.status not in (RequestStatus.APPROVED, RequestStatus.EDITED):
                continue
            amount = req.effective_amount
            if req.request_type.value == "CASH":
                total_cash_in += amount
            else:
                total_credit_in += amount

        return {
            "total_cash_in": total_cash_in,
            "total_credit_in": total_credit_in,
            "total_buy_in": total_cash_in + total_credit_in,
        }

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------

    async def checkout_player(
        self,
        game_id: str,
        player_token: str,
        final_chip_count: int,
    ) -> dict[str, Any]:
        """Checkout a single player from the game.

        Steps:
        1. Validate game exists and is OPEN or SETTLING.
        2. Validate player exists and is not already checked out.
        3. Calculate profit/loss = final_chip_count - total_buy_in.
        4. Update player: checked_out=True, checked_out_at=now,
           final_chip_count, profit_loss.
        5. Update bank: chips_in_play -= total_buy_in,
           total_chips_returned += final_chip_count.
        6. Flag if player has outstanding credits (credits_owed > 0).
        7. Send notification to the player about checkout.
        8. Return checkout summary.

        Args:
            game_id: The game's string ObjectId.
            player_token: The target player's UUID token.
            final_chip_count: The number of chips the player has at checkout.

        Returns:
            A dict with checkout summary fields.

        Raises:
            HTTPException 400: Game is CLOSED or player already checked out.
            HTTPException 404: Game or player not found.
        """
        # 1. Validate game
        game = await self._get_game_or_404(game_id)

        if game.status == GameStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Game is CLOSED and cannot process checkouts",
            )

        if game.status not in (GameStatus.OPEN, GameStatus.SETTLING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Game is {game.status} and cannot process checkouts",
            )

        # 2. Validate player
        player = await self._get_player_or_404(game_id, player_token)

        if player.checked_out:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player is already checked out",
            )

        # 3. Calculate profit/loss
        buy_in_totals = await self._compute_total_buy_in(game_id, player_token)
        total_buy_in = buy_in_totals["total_buy_in"]
        profit_loss = final_chip_count - total_buy_in

        # 4. Update player record
        now = datetime.now(timezone.utc)
        await self._player_dal.update(
            str(player.id),
            {
                "checked_out": True,
                "checked_out_at": now,
                "final_chip_count": final_chip_count,
                "profit_loss": profit_loss,
            },
        )

        # 5. Update bank
        bank_increments: dict[str, int] = {
            "bank.chips_in_play": -total_buy_in,
            "bank.total_chips_returned": final_chip_count,
        }
        await self._game_dal.update_bank(game_id, bank_increments)

        # 6. Determine debt status
        credits_owed = player.credits_owed
        has_debt = credits_owed > 0

        # 7. Send notification
        pl_prefix = "+" if profit_loss > 0 else ""
        message = (
            f"You have been checked out. Final chips: {final_chip_count}. "
            f"P/L: {pl_prefix}{profit_loss}"
        )
        notification = Notification(
            game_id=game_id,
            player_token=player_token,
            notification_type=NotificationType.CHECKOUT_COMPLETE,
            message=message,
            related_id=str(player.id),
        )
        await self._notification_dal.create(notification)

        checked_out_at_str = now.isoformat()

        logger.info(
            "Player checked out: game=%s player=%s final_chips=%d "
            "total_buy_in=%d profit_loss=%d has_debt=%s",
            game_id,
            player_token,
            final_chip_count,
            total_buy_in,
            profit_loss,
            has_debt,
        )

        # 8. Return checkout summary
        return {
            "player_id": player_token,
            "player_name": player.display_name,
            "final_chip_count": final_chip_count,
            "total_buy_in": total_buy_in,
            "profit_loss": profit_loss,
            "credits_owed": credits_owed,
            "has_debt": has_debt,
            "checked_out_at": checked_out_at_str,
        }

    # ------------------------------------------------------------------
    # Checkout Order
    # ------------------------------------------------------------------

    async def get_checkout_order(self, game_id: str) -> list[dict[str, Any]]:
        """Get the ordered list of active players for checkout.

        The order prioritizes:
        1. Players with credits_owed > 0 (sorted alphabetically by name)
        2. Remaining players (sorted alphabetically by name)

        Args:
            game_id: The game's string ObjectId.

        Returns:
            A list of dicts with player_token, display_name, credits_owed,
            and has_debt for each active, non-checked-out player.

        Raises:
            HTTPException 404: Game not found.
        """
        # Validate game exists
        await self._get_game_or_404(game_id)

        # Get all active, non-checked-out players
        active_players = await self._player_dal.get_active_players(game_id)

        # Separate players with credits_owed > 0 from others
        credit_players = [p for p in active_players if p.credits_owed > 0]
        other_players = [p for p in active_players if p.credits_owed <= 0]

        # Sort each group alphabetically by display_name (case-insensitive)
        credit_players.sort(key=lambda p: p.display_name.lower())
        other_players.sort(key=lambda p: p.display_name.lower())

        # Combine: credit players first, then others
        ordered_players = credit_players + other_players

        logger.info(
            "Checkout order for game=%s: %d players (%d with credits)",
            game_id,
            len(ordered_players),
            len(credit_players),
        )

        return [
            {
                "player_token": p.player_token,
                "display_name": p.display_name,
                "credits_owed": p.credits_owed,
                "has_debt": p.credits_owed > 0,
            }
            for p in ordered_players
        ]

    async def checkout_next_player(
        self,
        game_id: str,
        final_chip_count: int,
    ) -> dict[str, Any]:
        """Checkout the next player in the checkout queue.

        Uses the checkout order (credit-debt players first, then alphabetical)
        to determine which player to check out.

        Args:
            game_id: The game's string ObjectId.
            final_chip_count: The number of chips the player has at checkout.

        Returns:
            A dict with checkout summary fields (same as checkout_player).

        Raises:
            HTTPException 400: No players remaining to checkout.
            HTTPException 404: Game not found.
        """
        # Get the checkout order
        checkout_order = await self.get_checkout_order(game_id)

        if not checkout_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No players remaining to checkout",
            )

        # Get the first player in the queue
        next_player = checkout_order[0]
        player_token = next_player["player_token"]

        logger.info(
            "Checking out next player: game=%s player=%s (%s)",
            game_id,
            player_token,
            next_player["display_name"],
        )

        # Use the existing checkout_player method
        return await self.checkout_player(
            game_id=game_id,
            player_token=player_token,
            final_chip_count=final_chip_count,
        )
