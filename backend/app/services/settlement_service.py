"""Settlement business logic service.

Handles game settling transition (OPEN -> SETTLING), batch checkout
of all active players, debt resolution, and game closing.
Coordinates between Game, Player, ChipRequest, and Notification DALs.
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
from app.models.game import Game
from app.models.notification import Notification
from app.services.notification_service import NotificationService

logger = logging.getLogger("chipmate.services.settlement")


class SettlementService:
    """Service layer for game settlement and batch checkout operations."""

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
        self._notification_service = NotificationService(notification_dal)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_game_or_404(self, game_id: str) -> Game:
        """Fetch a game by ID, raising 404 if not found."""
        game = await self._game_dal.get_by_id(game_id)
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )
        return game

    async def _compute_total_buy_in(
        self, game_id: str, player_token: str
    ) -> int:
        """Compute total chips bought in by a player (sum of effective amounts).

        Only counts APPROVED and EDITED requests.
        """
        requests = await self._chip_request_dal.get_by_player(
            game_id, player_token
        )
        total = 0
        for req in requests:
            if req.status in (RequestStatus.APPROVED, RequestStatus.EDITED):
                total += req.effective_amount
        return total

    # ------------------------------------------------------------------
    # Start settling
    # ------------------------------------------------------------------

    async def start_settling(self, game_id: str) -> Game:
        """Transition game from OPEN to SETTLING.

        - Validates game is currently OPEN.
        - Declines all pending chip requests.
        - Changes status to SETTLING.
        - Sends notification to all players.

        Args:
            game_id: The game's string ObjectId.

        Returns:
            The updated Game.

        Raises:
            HTTPException 400: Game is not OPEN.
            HTTPException 404: Game not found.
        """
        game = await self._get_game_or_404(game_id)

        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Game is {game.status}, can only settle an OPEN game",
            )

        # Decline all pending chip requests
        declined_count = await self._chip_request_dal.decline_all_pending(
            game_id
        )
        if declined_count > 0:
            logger.info(
                "Declined %d pending requests for game %s during settling",
                declined_count,
                game_id,
            )

        # Update game status to SETTLING
        updated = await self._game_dal.update_status(
            game_id, GameStatus.SETTLING
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update game status",
            )

        # Send notification to all active players
        players = await self._player_dal.get_by_game(
            game_id, include_inactive=False
        )
        player_tokens = [p.player_token for p in players]
        await self._notification_service.create_bulk_notifications(
            game_id=game_id,
            player_tokens=player_tokens,
            notification_type=NotificationType.GAME_SETTLING,
            message="Game is settling - no more chip requests",
        )

        # Re-fetch and return updated game
        updated_game = await self._get_game_or_404(game_id)
        logger.info("Game %s transitioned to SETTLING", game_id)
        return updated_game

    # ------------------------------------------------------------------
    # Checkout all players
    # ------------------------------------------------------------------

    async def checkout_all_players(
        self,
        game_id: str,
        player_chips: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Batch checkout all active players.

        Args:
            game_id: The game's string ObjectId.
            player_chips: List of dicts with player_id (player_token)
                and final_chip_count for each active player.

        Returns:
            A dict with checked_out list and summary.

        Raises:
            HTTPException 400: Game not in SETTLING status, missing players,
                or no active players.
            HTTPException 404: Game not found.
        """
        game = await self._get_game_or_404(game_id)

        if game.status != GameStatus.SETTLING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Game is {game.status}, checkout-all requires SETTLING status",
            )

        # Get all active, non-checked-out players
        all_players = await self._player_dal.get_by_game(
            game_id, include_inactive=False
        )
        active_players = [p for p in all_players if not p.checked_out]

        if not active_players:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active players to check out",
            )

        # Build lookup of submitted chip counts by player_token
        submitted_tokens: dict[str, int] = {}
        for entry in player_chips:
            pid = entry["player_id"]
            chips = entry["final_chip_count"]
            submitted_tokens[pid] = chips

        # Validate all active players are included
        active_token_set = {p.player_token for p in active_players}
        missing = active_token_set - set(submitted_tokens.keys())
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing players in checkout list: {sorted(missing)}",
            )

        # Separate credit-debt and non-debt players for processing order
        # We will process all players, but credit-debt ones first
        now = datetime.now(timezone.utc)
        checked_out_results: list[dict[str, Any]] = []
        total_profit = 0
        total_loss = 0
        debt_players_count = 0
        total_chips_returned = 0

        # Sort: process players who have credits_owed > 0 first
        sorted_players = sorted(
            active_players,
            key=lambda p: (0 if p.credits_owed > 0 else 1, p.display_name),
        )

        for player in sorted_players:
            final_chips = submitted_tokens[player.player_token]
            total_buy_in = await self._compute_total_buy_in(
                game_id, player.player_token
            )
            profit_loss = final_chips - total_buy_in
            has_debt = player.credits_owed > 0

            # Update player record
            await self._player_dal.update(
                str(player.id),
                {
                    "checked_out": True,
                    "final_chip_count": final_chips,
                    "profit_loss": profit_loss,
                    "checked_out_at": now,
                },
            )

            # Track bank totals
            total_chips_returned += final_chips
            if profit_loss > 0:
                total_profit += profit_loss
            elif profit_loss < 0:
                total_loss += abs(profit_loss)

            if has_debt:
                debt_players_count += 1

            # Send checkout notification to the player
            pl_sign = "+" if profit_loss >= 0 else ""
            await self._notification_service.create_notification(
                game_id=game_id,
                player_token=player.player_token,
                notification_type=NotificationType.CHECKOUT_COMPLETE,
                message=(
                    f"You have been checked out. Final chips: {final_chips}. "
                    f"P/L: {pl_sign}{profit_loss}"
                ),
            )

            checked_out_results.append(
                {
                    "player_id": player.player_token,
                    "player_name": player.display_name,
                    "final_chip_count": final_chips,
                    "profit_loss": profit_loss,
                    "has_debt": has_debt,
                }
            )

        # Update bank: track total chips returned, decrement chips_in_play
        if total_chips_returned > 0:
            await self._game_dal.update_bank(
                game_id,
                {
                    "bank.total_chips_returned": total_chips_returned,
                    "bank.chips_in_play": -total_chips_returned,
                },
            )

        logger.info(
            "Checked out %d players for game %s (profit=%d, loss=%d, debt=%d)",
            len(checked_out_results),
            game_id,
            total_profit,
            total_loss,
            debt_players_count,
        )

        return {
            "checked_out": checked_out_results,
            "summary": {
                "total_checked_out": len(checked_out_results),
                "debt_players_count": debt_players_count,
                "total_profit": total_profit,
                "total_loss": total_loss,
            },
        }

    # ------------------------------------------------------------------
    # Settle a player's debt
    # ------------------------------------------------------------------

    async def settle_player_debt(
        self,
        game_id: str,
        player_token: str,
        allocations: list[dict[str, int]],
    ) -> dict[str, Any]:
        """Mark a player's credit debt as settled (set credits_owed to 0).

        The player must exist in the game, be checked out, and have
        credits_owed > 0.

        Args:
            game_id: The game's string ObjectId.
            player_token: The player's UUID token.
            allocations: List of dicts with recipient_token and amount.

        Returns:
            A dict with player_id, player_name, previous_credits_owed,
            credits_owed (0), settled (True), and allocations.

        Raises:
            HTTPException 404: Game or player not found.
            HTTPException 400: Player not checked out or has no debt.
        """
        await self._get_game_or_404(game_id)

        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found in this game",
            )

        if not player.checked_out:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player must be checked out before settling debt",
            )

        if player.credits_owed <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player has no outstanding debt to settle",
            )

        previous_credits_owed = player.credits_owed

        if not allocations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Allocations are required to settle debt",
            )

        total_allocated = 0
        allocations_by_token: dict[str, int] = {}
        for entry in allocations:
            recipient_token = entry.get("recipient_token")
            amount = entry.get("amount")
            if not recipient_token or amount is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Each allocation must include recipient_token and amount",
                )
            if amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Allocation amounts must be greater than 0",
                )
            if recipient_token == player_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Recipient cannot be the same as the debtor",
                )
            allocations_by_token[recipient_token] = (
                allocations_by_token.get(recipient_token, 0) + amount
            )
            total_allocated += amount

        if total_allocated != previous_credits_owed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Allocated total ({total_allocated}) must equal "
                    f"debt amount ({previous_credits_owed})"
                ),
            )

        recipients = []
        for recipient_token, amount in allocations_by_token.items():
            recipient = await self._player_dal.get_by_token(
                game_id, recipient_token
            )
            if recipient is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Recipient not found in this game",
                )
            recipients.append(
                {
                    "recipient_token": recipient_token,
                    "recipient_name": recipient.display_name,
                    "amount": amount,
                }
            )

        # Zero out the debt
        await self._player_dal.update_by_token(
            game_id, player_token, {"credits_owed": 0}
        )

        # Send notification to the debtor with recipients list
        recipients_summary = ", ".join(
            f"{r['recipient_name']} ({r['amount']})" for r in recipients
        )
        await self._notification_service.create_notification(
            game_id=game_id,
            player_token=player_token,
            notification_type=NotificationType.DEBT_SETTLED,
            message=(
                f"Your credit debt of {previous_credits_owed} chips "
                f"was settled and allocated to: {recipients_summary}."
            ),
        )

        # Notify recipients
        for recipient in recipients:
            await self._notification_service.create_notification(
                game_id=game_id,
                player_token=recipient["recipient_token"],
                notification_type=NotificationType.DEBT_SETTLED,
                message=(
                    f"You received {recipient['amount']} chips from "
                    f"{player.display_name}'s settled debt."
                ),
            )

        logger.info(
            "Settled debt for player_token=%s in game=%s (was %d)",
            player_token,
            game_id,
            previous_credits_owed,
        )

        return {
            "player_id": player.player_token,
            "player_name": player.display_name,
            "previous_credits_owed": previous_credits_owed,
            "credits_owed": 0,
            "settled": True,
            "allocations": recipients,
        }

    # ------------------------------------------------------------------
    # Close game
    # ------------------------------------------------------------------

    async def close_game(self, game_id: str) -> dict[str, Any]:
        """Close a game that is in SETTLING status.

        All active players must be checked out. If players still have
        unsettled debts, the game can still be closed but the count
        is included in the response summary.

        Args:
            game_id: The game's string ObjectId.

        Returns:
            A dict with game_id, status, closed_at, and summary.

        Raises:
            HTTPException 404: Game not found.
            HTTPException 400: Game not in SETTLING status or has
                unchecked-out players.
        """
        game = await self._get_game_or_404(game_id)

        if game.status != GameStatus.SETTLING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Game is {game.status}, can only close a SETTLING game"
                ),
            )

        # Check for unchecked-out active players
        active_players = await self._player_dal.get_active_players(game_id)
        if active_players:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{len(active_players)} player(s) have not been "
                    f"checked out yet"
                ),
            )

        # Gather summary data from all players
        all_players = await self._player_dal.get_by_game(
            game_id, include_inactive=True
        )
        total_profit = 0
        total_loss = 0
        unsettled_debts = 0
        for p in all_players:
            if p.profit_loss is not None:
                if p.profit_loss > 0:
                    total_profit += p.profit_loss
                elif p.profit_loss < 0:
                    total_loss += abs(p.profit_loss)
            if p.credits_owed > 0:
                unsettled_debts += 1

        # Transition to CLOSED
        now = datetime.now(timezone.utc)
        updated = await self._game_dal.update_status(
            game_id, GameStatus.CLOSED, closed_at=now
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update game status",
            )

        # Notify all players
        player_tokens = [p.player_token for p in all_players if p.is_active]
        await self._notification_service.create_bulk_notifications(
            game_id=game_id,
            player_tokens=player_tokens,
            notification_type=NotificationType.GAME_CLOSED,
            message="The game has been closed by the manager.",
        )

        logger.info(
            "Game %s closed (players=%d, profit=%d, loss=%d, debts=%d)",
            game_id,
            len(all_players),
            total_profit,
            total_loss,
            unsettled_debts,
        )

        return {
            "game_id": game_id,
            "status": str(GameStatus.CLOSED),
            "closed_at": now.isoformat(),
            "summary": {
                "total_players": len(all_players),
                "total_profit": total_profit,
                "total_loss": total_loss,
                "unsettled_debts": unsettled_debts,
            },
        }
