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
from app.services.checkout_math import compute_credit_deduction, compute_distribution_suggestion

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
    # Mid-game checkout (single player, during OPEN)
    # ------------------------------------------------------------------

    async def request_midgame_checkout(self, game_id: str, player_token: str) -> dict:
        """Initiate mid-game checkout for a single player during OPEN state.

        Freezes this player's buy-in data and sets checkout_status to PENDING.
        The player then goes through the same per-player flow.
        """
        game = await self._get_game_or_404(game_id)
        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=400,
                detail="Game must be OPEN for mid-game checkout",
            )

        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=404,
                detail="Player not found",
            )
        if player.checkout_status is not None:
            raise HTTPException(
                status_code=400,
                detail="Player already in checkout",
            )

        # Compute and freeze buy-in
        totals = await self._compute_player_totals(game_id, player_token)
        frozen = {
            "total_cash_in": totals["total_cash_in"],
            "total_credit_in": totals["total_credit_in"],
            "total_buy_in": totals["total_cash_in"] + totals["total_credit_in"],
        }

        await self._player_dal.update_by_token(game_id, player_token, {
            "frozen_buy_in": frozen,
            "checkout_status": str(CheckoutStatus.PENDING),
        })

        return {"status": "checkout_initiated", "player_token": player_token}

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

    # ------------------------------------------------------------------
    # Chip submission
    # ------------------------------------------------------------------

    async def submit_chips(
        self,
        game_id: str,
        player_token: str,
        chip_count: int,
        preferred_cash: int,
        preferred_credit: int,
    ) -> None:
        """Player submits their chip count and payout preferences.

        Validates the player is in PENDING status and not input-locked,
        then saves the submission and transitions to SUBMITTED.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.
            chip_count: Number of chips the player is returning.
            preferred_cash: Preferred cash payout amount.
            preferred_credit: Preferred credit payout amount.

        Raises:
            HTTPException 404: Player not found.
            HTTPException 400: Player not in PENDING state or input is locked.
        """
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        if player.input_locked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player input is locked by manager",
            )

        if player.checkout_status != CheckoutStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player must be in PENDING status to submit chips",
            )

        await self._player_dal.update_by_token(
            game_id,
            player_token,
            {
                "submitted_chip_count": chip_count,
                "preferred_cash": preferred_cash,
                "preferred_credit": preferred_credit,
                "checkout_status": str(CheckoutStatus.SUBMITTED),
            },
        )

    # ------------------------------------------------------------------
    # Chip validation
    # ------------------------------------------------------------------

    async def validate_chips(
        self, game_id: str, player_token: str
    ) -> None:
        """Manager validates a player's submitted chip count.

        Copies submitted_chip_count to validated_chip_count, runs credit
        deduction math, and transitions to CREDIT_DEDUCTED.

        Fast path: if the player is cash-only (no credit buy-in) AND
        preferred_credit == 0, skip directly to DONE with immediate payout.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.

        Raises:
            HTTPException 404: Player not found.
            HTTPException 400: Player not in SUBMITTED state.
        """
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        if player.checkout_status != CheckoutStatus.SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player must be in SUBMITTED status to validate",
            )

        validated = player.submitted_chip_count
        frozen = player.frozen_buy_in
        total_cash_in = frozen["total_cash_in"]
        total_credit_in = frozen["total_credit_in"]

        result = compute_credit_deduction(validated, total_cash_in, total_credit_in)

        is_cash_only = total_credit_in == 0 and (player.preferred_credit or 0) == 0

        if is_cash_only:
            # Fast path: skip to DONE
            now = datetime.now(timezone.utc)
            chips_after = result["chips_after_credit"]
            await self._player_dal.update_by_token(
                game_id,
                player_token,
                {
                    "validated_chip_count": validated,
                    "credit_repaid": result["credit_repaid"],
                    "chips_after_credit": chips_after,
                    "profit_loss": result["profit_loss"],
                    "credits_owed": result["credit_owed"],
                    "checkout_status": str(CheckoutStatus.DONE),
                    "distribution": {"cash": chips_after, "credit_from": []},
                    "checked_out": True,
                    "checked_out_at": now,
                },
            )
            # Decrement cash_pool on the game
            game = await self._get_game_or_404(game_id)
            await self._game_dal.update(
                game_id, {"cash_pool": game.cash_pool - chips_after}
            )
        else:
            # Normal path: transition to CREDIT_DEDUCTED
            await self._player_dal.update_by_token(
                game_id,
                player_token,
                {
                    "validated_chip_count": validated,
                    "credit_repaid": result["credit_repaid"],
                    "chips_after_credit": result["chips_after_credit"],
                    "profit_loss": result["profit_loss"],
                    "credits_owed": result["credit_owed"],
                    "checkout_status": str(CheckoutStatus.CREDIT_DEDUCTED),
                },
            )

    # ------------------------------------------------------------------
    # Chip rejection
    # ------------------------------------------------------------------

    async def reject_chips(
        self, game_id: str, player_token: str
    ) -> None:
        """Manager rejects a player's submitted chip count.

        Resets the player back to PENDING and clears submission fields.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.

        Raises:
            HTTPException 404: Player not found.
            HTTPException 400: Player not in SUBMITTED state.
        """
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        if player.checkout_status != CheckoutStatus.SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player must be in SUBMITTED status to reject",
            )

        await self._player_dal.update_by_token(
            game_id,
            player_token,
            {
                "checkout_status": str(CheckoutStatus.PENDING),
                "submitted_chip_count": None,
                "preferred_cash": None,
                "preferred_credit": None,
            },
        )

    # ------------------------------------------------------------------
    # Manager input (override)
    # ------------------------------------------------------------------

    async def manager_input(
        self,
        game_id: str,
        player_token: str,
        chip_count: int,
        preferred_cash: int,
        preferred_credit: int,
    ) -> None:
        """Manager directly inputs chip count for a player, locks input, and auto-validates.

        Sets input_locked=True, saves submission fields, transitions to
        SUBMITTED, then immediately runs validate_chips logic.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.
            chip_count: Number of chips the player is returning.
            preferred_cash: Preferred cash payout amount.
            preferred_credit: Preferred credit payout amount.

        Raises:
            HTTPException 404: Player not found.
        """
        await self._player_dal.update_by_token(
            game_id,
            player_token,
            {
                "input_locked": True,
                "submitted_chip_count": chip_count,
                "preferred_cash": preferred_cash,
                "preferred_credit": preferred_credit,
                "checkout_status": str(CheckoutStatus.SUBMITTED),
            },
        )

        # Auto-validate
        await self.validate_chips(game_id, player_token)

    # ------------------------------------------------------------------
    # Distribution
    # ------------------------------------------------------------------

    async def get_distribution_suggestion(self, game_id: str) -> dict:
        """Compute a distribution suggestion for all eligible players.

        Gathers players with checkout_status >= CREDIT_DEDUCTED (but not DONE),
        then delegates to the pure ``compute_distribution_suggestion`` function.

        Returns:
            Dict keyed by player_token with cash amount and credit_from list.
        """
        game = await self._get_game_or_404(game_id)
        players = await self._player_dal.get_by_game(game_id, include_inactive=False)

        eligible_statuses = {
            CheckoutStatus.CREDIT_DEDUCTED,
            CheckoutStatus.AWAITING_DISTRIBUTION,
            CheckoutStatus.DISTRIBUTED,
        }

        eligible = []
        for p in players:
            if p.checkout_status in eligible_statuses:
                eligible.append({
                    "player_token": p.player_token,
                    "chips_after_credit": p.chips_after_credit or 0,
                    "preferred_cash": p.preferred_cash or 0,
                    "preferred_credit": p.preferred_credit or 0,
                    "credit_owed": p.credits_owed or 0,
                })

        return compute_distribution_suggestion(
            eligible, game.cash_pool, game.credit_pool
        )

    async def override_distribution(
        self, game_id: str, distribution: dict[str, dict]
    ) -> None:
        """Manager overrides the distribution for all players.

        Validates that cash allocations sum to remaining cash_pool and
        credit allocations do not exceed credit_pool, then saves
        distribution on each player and transitions to DISTRIBUTED.

        Args:
            game_id: The game identifier.
            distribution: Dict keyed by player_token with cash and credit_from.

        Raises:
            HTTPException 400: If totals don't match pools.
        """
        game = await self._get_game_or_404(game_id)

        total_cash = sum(d["cash"] for d in distribution.values())
        total_credit = sum(
            sum(c["amount"] for c in d.get("credit_from", []))
            for d in distribution.values()
        )

        if total_cash != game.cash_pool:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cash allocations ({total_cash}) must equal cash_pool ({game.cash_pool})",
            )

        # Credit pool grows as debtors reach DONE, so validate against
        # total available credit (current pool + outstanding debtor credit_owed).
        players = await self._player_dal.get_by_game(game_id, include_inactive=False)
        total_available_credit = game.credit_pool + sum(
            p.credits_owed or 0 for p in players
        )

        if total_credit > total_available_credit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credit allocations ({total_credit}) exceed available credit ({total_available_credit})",
            )

        for player_token, dist in distribution.items():
            await self._player_dal.update_by_token(
                game_id,
                player_token,
                {
                    "distribution": dist,
                    "checkout_status": str(CheckoutStatus.DISTRIBUTED),
                },
            )

    async def confirm_distribution(
        self, game_id: str, player_token: str
    ) -> None:
        """Confirm a player's distribution, transitioning to DONE.

        If the player is a debtor (credit_owed > 0), their credit_owed
        is added to the game's credit_pool. Cash pool is decremented by
        the player's cash distribution amount.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.

        Raises:
            HTTPException 404: Player not found.
            HTTPException 400: Player not in DISTRIBUTED status.
        """
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        if player.checkout_status != CheckoutStatus.DISTRIBUTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player must be in DISTRIBUTED status to confirm",
            )

        now = datetime.now(timezone.utc)
        actions = self._build_actions(game_id, player_token, player.distribution, player.credits_owed or 0)

        await self._player_dal.update_by_token(
            game_id,
            player_token,
            {
                "checkout_status": str(CheckoutStatus.DONE),
                "checked_out": True,
                "checked_out_at": now,
                "actions": actions,
            },
        )

        # Update game pools
        game = await self._get_game_or_404(game_id)
        updates: dict = {}

        # If debtor, add credit_owed to credit_pool
        credit_owed = player.credits_owed or 0
        if credit_owed > 0:
            updates["credit_pool"] = game.credit_pool + credit_owed

        # Decrement cash_pool by cash distribution
        cash_amount = (player.distribution or {}).get("cash", 0)
        if cash_amount > 0:
            current_cash = updates.get("cash_pool", game.cash_pool)
            updates["cash_pool"] = current_cash - cash_amount

        if updates:
            await self._game_dal.update(game_id, updates)

    def _build_actions(
        self,
        game_id: str,
        player_token: str,
        distribution: dict | None,
        credit_owed: int,
    ) -> list[dict]:
        """Build the actions list for a player based on their distribution.

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.
            distribution: The player's distribution dict (cash, credit_from).
            credit_owed: The player's credit_owed amount.

        Returns:
            List of action dicts.
        """
        actions: list[dict] = []
        dist = distribution or {"cash": 0, "credit_from": []}

        cash = dist.get("cash", 0)
        if cash > 0:
            actions.append({"type": "receive_cash", "amount": cash})

        for entry in dist.get("credit_from", []):
            actions.append({
                "type": "receive_credit",
                "from": entry["from"],
                "amount": entry["amount"],
            })

        # Debtor pay_credit actions: find who receives credit FROM this player
        # by scanning all players' distributions (stored on player docs)
        # We handle this synchronously from the distribution data passed in,
        # but debtor actions require knowing other players' distributions.
        # We'll handle this in the async caller instead.

        return actions

    async def _build_debtor_actions(
        self, game_id: str, player_token: str
    ) -> list[dict]:
        """Build pay_credit actions for a debtor by scanning all distributions."""
        players = await self._player_dal.get_by_game(game_id, include_inactive=False)
        actions: list[dict] = []
        for p in players:
            if p.player_token == player_token:
                continue
            dist = p.distribution or {"cash": 0, "credit_from": []}
            for entry in dist.get("credit_from", []):
                if entry["from"] == player_token:
                    actions.append({
                        "type": "pay_credit",
                        "to": p.player_token,
                        "amount": entry["amount"],
                    })
        return actions

    async def get_player_actions(
        self, game_id: str, player_token: str
    ) -> list[dict]:
        """Return the actions list for a player.

        Actions are generated from distribution data:
        - receive_cash if cash > 0
        - receive_credit for each credit_from entry
        - pay_credit for each player who receives credit from this player (debtor)

        Args:
            game_id: The game identifier.
            player_token: The player's UUID token.

        Returns:
            List of action dicts.

        Raises:
            HTTPException 404: Player not found.
        """
        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        actions = self._build_actions(
            game_id, player_token, player.distribution, player.credits_owed or 0
        )

        # Add debtor pay_credit actions
        debtor_actions = await self._build_debtor_actions(game_id, player_token)
        actions.extend(debtor_actions)

        return actions

    # ------------------------------------------------------------------
    # Close game
    # ------------------------------------------------------------------

    async def close_game(self, game_id: str) -> dict:
        """Close a game after all players have completed checkout.

        Validates that every active player has checkout_status == DONE,
        then sets game status to CLOSED with a closed_at timestamp.

        Args:
            game_id: The game identifier.

        Returns:
            Dict with game_id, status, and closed_at.

        Raises:
            HTTPException 400: If any active player is not DONE.
        """
        game = await self._get_game_or_404(game_id)
        players = await self._player_dal.get_by_game(game_id, include_inactive=False)

        not_done = [
            p for p in players
            if p.checkout_status != CheckoutStatus.DONE
        ]

        if not_done:
            names = [p.display_name for p in not_done]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"All players must be DONE to close game. Not done: {names}",
            )

        now = datetime.now(timezone.utc)
        await self._game_dal.update_status(game_id, GameStatus.CLOSED)
        await self._game_dal.update(game_id, {"closed_at": now})

        return {
            "game_id": game_id,
            "status": "CLOSED",
            "closed_at": now.isoformat(),
        }
