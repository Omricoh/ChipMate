"""Chip request business logic service.

Handles creation, approval, decline, and edit-approve workflows
for chip buy-in requests. Coordinates between ChipRequestDAL,
GameDAL, PlayerDAL, and NotificationDAL.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.chip_request import ChipRequest
from app.models.common import (
    GameStatus,
    NotificationType,
    RequestStatus,
    RequestType,
)
from app.models.notification import Notification

logger = logging.getLogger("chipmate.services.request")


class RequestService:
    """Service layer for chip request operations."""

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

    async def _get_request_or_404(self, request_id: str) -> ChipRequest:
        """Fetch a chip request by ID, raising 404 if not found."""
        chip_request = await self._chip_request_dal.get_by_id(request_id)
        if chip_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chip request not found",
            )
        return chip_request

    def _validate_request_belongs_to_game(
        self, chip_request: ChipRequest, game_id: str
    ) -> None:
        """Ensure the chip request belongs to the specified game."""
        if chip_request.game_id != game_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chip request not found in this game",
            )

    def _validate_request_pending(self, chip_request: ChipRequest) -> None:
        """Ensure the chip request is still PENDING."""
        if chip_request.status != RequestStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chip request already processed (status: {chip_request.status})",
            )

    async def _apply_bank_and_player_updates(
        self,
        game_id: str,
        player_token: str,
        request_type: RequestType,
        amount: int,
    ) -> None:
        """Update bank and player records for an approved/edited request.

        For cash: bank.total_cash_in += amount, bank.cash_balance += amount
        For credit: bank.total_credits_issued += amount, player.credits_owed += amount
        Always: bank.total_chips_issued += amount, bank.chips_in_play += amount
        """
        bank_increments: dict[str, int] = {
            "bank.total_chips_issued": amount,
            "bank.chips_in_play": amount,
        }

        if request_type == RequestType.CASH:
            bank_increments["bank.total_cash_in"] = amount
            bank_increments["bank.cash_balance"] = amount
        elif request_type == RequestType.CREDIT:
            bank_increments["bank.total_credits_issued"] = amount

        await self._game_dal.update_bank(game_id, bank_increments)

        if request_type == RequestType.CREDIT:
            await self._player_dal.increment_credits(
                game_id, player_token, amount
            )

        logger.info(
            "Applied bank/player updates: game=%s player=%s type=%s amount=%d",
            game_id,
            player_token,
            request_type,
            amount,
        )

    async def _create_notification(
        self,
        game_id: str,
        player_token: str,
        notification_type: NotificationType,
        message: str,
        related_id: Optional[str] = None,
    ) -> None:
        """Create a notification for a player."""
        notification = Notification(
            game_id=game_id,
            player_token=player_token,
            notification_type=notification_type,
            message=message,
            related_id=related_id,
        )
        await self._notification_dal.create(notification)

    # ------------------------------------------------------------------
    # Create request
    # ------------------------------------------------------------------

    async def create_request(
        self,
        game_id: str,
        player_token: str,
        request_type: RequestType,
        amount: int,
        on_behalf_of_token: Optional[str] = None,
    ) -> ChipRequest:
        """Create a new chip buy-in request.

        Args:
            game_id: The game's string ObjectId.
            player_token: The requesting player's UUID token.
            request_type: CASH or CREDIT.
            amount: Number of chips requested (must be > 0).
            on_behalf_of_token: If set, create request for this target
                player instead (manager on-behalf-of flow).

        Returns:
            The created ChipRequest.

        Raises:
            HTTPException 400: Game is not OPEN.
            HTTPException 404: Game or player not found.
        """
        game = await self._get_game_or_404(game_id)

        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Game is {game.status} and cannot accept chip requests",
            )

        # Validate the requesting player is in the game
        await self._get_player_or_404(game_id, player_token)

        # Determine the target player (self or on-behalf-of)
        target_token = player_token
        if on_behalf_of_token is not None:
            target_player = await self._get_player_or_404(
                game_id, on_behalf_of_token
            )
            target_token = on_behalf_of_token

        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be a positive integer",
            )

        chip_request = ChipRequest(
            game_id=game_id,
            player_token=target_token,
            requested_by=player_token,
            request_type=request_type,
            amount=amount,
            status=RequestStatus.PENDING,
        )

        chip_request = await self._chip_request_dal.create(chip_request)

        # If on-behalf-of, notify the target player
        if on_behalf_of_token is not None:
            requester = await self._player_dal.get_by_token(
                game_id, player_token
            )
            requester_name = requester.display_name if requester else "Manager"
            await self._create_notification(
                game_id=game_id,
                player_token=on_behalf_of_token,
                notification_type=NotificationType.ON_BEHALF_SUBMITTED,
                message=(
                    f"{requester_name} submitted a {request_type.value.lower()} "
                    f"buy-in of {amount} chips on your behalf"
                ),
                related_id=str(chip_request.id),
            )

        logger.info(
            "Chip request created: id=%s game=%s player=%s type=%s amount=%d",
            chip_request.id,
            game_id,
            target_token,
            request_type,
            amount,
        )

        return chip_request

    # ------------------------------------------------------------------
    # Approve request
    # ------------------------------------------------------------------

    async def approve_request(
        self,
        game_id: str,
        request_id: str,
        manager_token: str,
    ) -> ChipRequest:
        """Approve a pending chip request.

        Updates request status to APPROVED, updates bank and player
        totals, and sends a notification to the requesting player.

        Args:
            game_id: The game's string ObjectId.
            request_id: The chip request's string ObjectId.
            manager_token: The manager's player token.

        Returns:
            The updated ChipRequest.

        Raises:
            HTTPException 400: Request already processed.
            HTTPException 404: Game or request not found.
        """
        await self._get_game_or_404(game_id)
        chip_request = await self._get_request_or_404(request_id)
        self._validate_request_belongs_to_game(chip_request, game_id)
        self._validate_request_pending(chip_request)

        # Update request status (optimistic lock on PENDING)
        updated = await self._chip_request_dal.update_status(
            request_id=request_id,
            new_status=RequestStatus.APPROVED,
            resolved_by=manager_token,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chip request already processed",
            )

        # Apply bank and player updates
        await self._apply_bank_and_player_updates(
            game_id=game_id,
            player_token=chip_request.player_token,
            request_type=chip_request.request_type,
            amount=chip_request.amount,
        )

        # Notify the player
        await self._create_notification(
            game_id=game_id,
            player_token=chip_request.player_token,
            notification_type=NotificationType.REQUEST_APPROVED,
            message=(
                f"Your {chip_request.request_type.value.lower()} buy-in of "
                f"{chip_request.amount} chips was approved"
            ),
            related_id=request_id,
        )

        # Re-fetch the updated request
        updated_request = await self._chip_request_dal.get_by_id(request_id)
        return updated_request  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Decline request
    # ------------------------------------------------------------------

    async def decline_request(
        self,
        game_id: str,
        request_id: str,
        manager_token: str,
    ) -> ChipRequest:
        """Decline a pending chip request.

        Updates request status to DECLINED with no bank/player changes.
        Sends a notification to the requesting player.

        Args:
            game_id: The game's string ObjectId.
            request_id: The chip request's string ObjectId.
            manager_token: The manager's player token.

        Returns:
            The updated ChipRequest.

        Raises:
            HTTPException 400: Request already processed.
            HTTPException 404: Game or request not found.
        """
        await self._get_game_or_404(game_id)
        chip_request = await self._get_request_or_404(request_id)
        self._validate_request_belongs_to_game(chip_request, game_id)
        self._validate_request_pending(chip_request)

        updated = await self._chip_request_dal.update_status(
            request_id=request_id,
            new_status=RequestStatus.DECLINED,
            resolved_by=manager_token,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chip request already processed",
            )

        # Notify the player
        await self._create_notification(
            game_id=game_id,
            player_token=chip_request.player_token,
            notification_type=NotificationType.REQUEST_DECLINED,
            message=(
                f"Your {chip_request.request_type.value.lower()} buy-in of "
                f"{chip_request.amount} chips was declined"
            ),
            related_id=request_id,
        )

        updated_request = await self._chip_request_dal.get_by_id(request_id)
        return updated_request  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Edit and approve request
    # ------------------------------------------------------------------

    async def edit_and_approve_request(
        self,
        game_id: str,
        request_id: str,
        new_amount: int,
        new_type: Optional[RequestType],
        manager_token: str,
    ) -> ChipRequest:
        """Edit a request's amount and approve it atomically.

        Sets status to EDITED, stores edited_amount, and applies
        bank/player updates using the new amount. The original amount
        is preserved in the request's ``amount`` field.

        Args:
            game_id: The game's string ObjectId.
            request_id: The chip request's string ObjectId.
            new_amount: The manager-adjusted chip amount (must be > 0).
            manager_token: The manager's player token.

        Returns:
            The updated ChipRequest.

        Raises:
            HTTPException 400: Request already processed or invalid amount.
            HTTPException 404: Game or request not found.
        """
        if new_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be a positive integer",
            )

        await self._get_game_or_404(game_id)
        chip_request = await self._get_request_or_404(request_id)
        self._validate_request_belongs_to_game(chip_request, game_id)
        self._validate_request_pending(chip_request)

        original_amount = chip_request.amount
        effective_type = new_type or chip_request.request_type

        updated = await self._chip_request_dal.update_status(
            request_id=request_id,
            new_status=RequestStatus.EDITED,
            resolved_by=manager_token,
            edited_amount=new_amount,
            edited_request_type=new_type,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chip request already processed",
            )

        # Apply bank and player updates with the NEW amount
        await self._apply_bank_and_player_updates(
            game_id=game_id,
            player_token=chip_request.player_token,
            request_type=effective_type,
            amount=new_amount,
        )

        # Notify the player
        await self._create_notification(
            game_id=game_id,
            player_token=chip_request.player_token,
            notification_type=NotificationType.REQUEST_EDITED,
            message=(
                f"Your {effective_type.value.lower()} buy-in was edited to "
                f"{new_amount} chips and approved (original: {original_amount})"
            ),
            related_id=request_id,
        )

        updated_request = await self._chip_request_dal.get_by_id(request_id)
        return updated_request  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    async def get_pending_requests(self, game_id: str) -> list[ChipRequest]:
        """Get all pending chip requests for a game, oldest first.

        Args:
            game_id: The game's string ObjectId.

        Returns:
            A list of pending ChipRequest instances.
        """
        await self._get_game_or_404(game_id)
        return await self._chip_request_dal.get_pending_by_game(game_id)

    async def get_player_requests(
        self, game_id: str, player_token: str
    ) -> list[ChipRequest]:
        """Get all chip requests for a specific player in a game.

        Args:
            game_id: The game's string ObjectId.
            player_token: The player's UUID token.

        Returns:
            A list of ChipRequest instances for the player, newest first.
        """
        await self._get_game_or_404(game_id)
        return await self._chip_request_dal.get_by_player(game_id, player_token)
