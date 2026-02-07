"""Game business logic service.

Handles game creation, code generation, player joining, and
status/bankroll summary. Sits between route handlers and the DAL.
"""

import logging
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.auth.player_token import generate_player_token
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.dal.chip_requests_dal import ChipRequestDAL
from app.models.common import GameStatus
from app.models.game import Game
from app.models.player import Player
from app.models.common import RequestType

logger = logging.getLogger("chipmate.services.game")

# Characters for game code generation.
# Excludes ambiguous characters: I, O, 0, 1
_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6
_MAX_CODE_RETRIES = 10


class GameService:
    """Service layer for game-related operations."""

    def __init__(
        self,
        game_dal: GameDAL,
        player_dal: PlayerDAL,
        chip_request_dal: ChipRequestDAL,
    ) -> None:
        self._game_dal = game_dal
        self._player_dal = player_dal
        self._chip_request_dal = chip_request_dal

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    async def _require_manager_player(self, game_id: str, manager_token: str) -> Player:
        """Ensure the game manager also exists as a player in the same game."""
        manager = await self._player_dal.get_by_token(game_id, manager_token)
        if manager is None or not manager.is_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Game manager player record is missing or invalid",
            )
        return manager

    async def _compute_player_totals(self, game_id: str, player_token: str) -> dict[str, int]:
        """Compute total cash/credit buy-ins for a player from approved/edited requests."""
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
    # Game code generation
    # ------------------------------------------------------------------

    async def generate_game_code(self) -> str:
        """Generate a unique 6-character alphanumeric game code.

        Uses unambiguous characters (no I, O, 0, 1). Checks the database
        for uniqueness and retries up to 10 times.

        Returns:
            A unique 6-character uppercase code.

        Raises:
            HTTPException 500: If unable to generate a unique code after
                               maximum retries.
        """
        for attempt in range(_MAX_CODE_RETRIES):
            code = "".join(random.choices(_CODE_CHARS, k=_CODE_LENGTH))
            existing = await self._game_dal.get_by_code(code)
            if existing is None:
                return code
            logger.warning(
                "Game code collision on attempt %d: %s", attempt + 1, code
            )

        logger.error("Failed to generate unique game code after %d attempts", _MAX_CODE_RETRIES)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate a unique game code. Please try again.",
        )

    # ------------------------------------------------------------------
    # Create game
    # ------------------------------------------------------------------

    async def create_game(self, manager_name: str) -> dict[str, Any]:
        """Create a new game and its manager player record.

        Args:
            manager_name: Display name for the manager (2-30 chars).

        Returns:
            A dict containing game_id, game_code, player_token, and
            manager_name.
        """
        code = await self.generate_game_code()
        manager_token = generate_player_token()

        now = datetime.now(timezone.utc)
        game = Game(
            code=code,
            status=GameStatus.OPEN,
            manager_player_token=manager_token,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )

        game = await self._game_dal.create(game)

        manager_player = Player(
            game_id=str(game.id),
            player_token=manager_token,
            display_name=manager_name,
            is_manager=True,
            joined_at=now,
        )
        manager_player = await self._player_dal.create(manager_player)

        logger.info(
            "Game created: id=%s code=%s manager=%s",
            game.id, code, manager_name,
        )

        return {
            "game_id": str(game.id),
            "game_code": game.code,
            "player_token": manager_token,
            "manager_name": manager_name,
            "manager_player_id": str(manager_player.id),
            "created_at": game.created_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Get game
    # ------------------------------------------------------------------

    async def get_game(self, game_id: str) -> Game:
        """Get a game by its MongoDB ID.

        Args:
            game_id: String ObjectId.

        Returns:
            The Game model instance.

        Raises:
            HTTPException 404: Game not found.
        """
        game = await self._game_dal.get_by_id(game_id)
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )
        return game

    async def get_game_by_code(self, code: str) -> Game:
        """Get a game by its 6-character join code.

        Args:
            code: The uppercase game code.

        Returns:
            The Game model instance.

        Raises:
            HTTPException 404: Game not found.
        """
        game = await self._game_dal.get_by_code(code.upper())
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )
        return game

    # ------------------------------------------------------------------
    # Join game
    # ------------------------------------------------------------------

    async def join_game(self, game_id: str, player_name: str) -> dict[str, Any]:
        """Join an existing game as a new player.

        Args:
            game_id: String ObjectId of the game.
            player_name: Display name for the joining player (2-30 chars).

        Returns:
            A dict with player_id, player_token, and game object containing
            game_id, game_code, manager_name, and status.

        Raises:
            HTTPException 404: Game not found.
            HTTPException 400: Game is not OPEN (SETTLING or CLOSED).
        """
        game = await self.get_game(game_id)

        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Game is {game.status} and cannot accept new players",
            )

        player_token = generate_player_token()
        now = datetime.now(timezone.utc)

        player = Player(
            game_id=game_id,
            player_token=player_token,
            display_name=player_name,
            is_manager=False,
            joined_at=now,
        )
        player = await self._player_dal.create(player)

        # Get manager player to obtain manager name
        manager = await self._player_dal.get_by_token(game_id, game.manager_player_token)
        manager_name = manager.display_name if manager else None

        logger.info(
            "Player joined: game_id=%s name=%s", game_id, player_name,
        )

        return {
            "player_id": str(player.id),
            "player_token": player_token,
            "game": {
                "game_id": game_id,
                "game_code": game.code,
                "manager_name": manager_name,
                "status": str(game.status),
            },
        }

    # ------------------------------------------------------------------
    # Players list
    # ------------------------------------------------------------------

    async def get_game_players(self, game_id: str) -> list[Player]:
        """Return all active players in a game.

        Args:
            game_id: String ObjectId of the game.

        Returns:
            A list of Player model instances.
        """
        game = await self.get_game(game_id)
        await self._require_manager_player(game_id, game.manager_player_token)
        return await self._player_dal.get_by_game(game_id, include_inactive=True)

    async def get_game_players_summary(self, game_id: str) -> list[dict[str, Any]]:
        """Return players with computed buy-in totals and current chip balance."""
        game = await self.get_game(game_id)
        await self._require_manager_player(game_id, game.manager_player_token)
        players = await self._player_dal.get_by_game(game_id, include_inactive=True)

        summaries: list[dict[str, Any]] = []
        for p in players:
            totals = await self._compute_player_totals(game_id, p.player_token)
            total_buy_in = totals["total_cash_in"] + totals["total_credit_in"]
            current_chips = (
                p.final_chip_count
                if p.checked_out and p.final_chip_count is not None
                else total_buy_in
            )
            summaries.append(
                {
                    "player_id": p.player_token,
                    "name": p.display_name,
                    "is_manager": p.is_manager,
                    "is_active": p.is_active,
                    "credits_owed": p.credits_owed,
                    "checked_out": p.checked_out,
                    "joined_at": p.joined_at,
                    "total_cash_in": totals["total_cash_in"],
                    "total_credit_in": totals["total_credit_in"],
                    "current_chips": current_chips,
                }
            )

        return summaries

    # ------------------------------------------------------------------
    # Game status with bankroll
    # ------------------------------------------------------------------

    async def get_game_status(self, game_id: str) -> dict[str, Any]:
        """Return game status with bankroll summary.

        Args:
            game_id: String ObjectId of the game.

        Returns:
            A dict with game info and bankroll totals.

        Raises:
            HTTPException 404: Game not found.
        """
        game = await self.get_game(game_id)
        manager = await self._require_manager_player(game_id, game.manager_player_token)
        players = await self._player_dal.get_by_game(game_id, include_inactive=True)

        active_count = sum(1 for p in players if p.is_active)
        checked_out_count = sum(1 for p in players if p.checked_out)
        credits_outstanding = sum(p.credits_owed for p in players)

        pending_requests = await self._chip_request_dal.count_pending_by_game(game_id)

        return {
            "game": {
                "game_id": str(game.id),
                "game_code": game.code,
                "status": str(game.status),
                "manager_name": manager.display_name,
                "created_at": game.created_at.isoformat() if isinstance(game.created_at, datetime) else str(game.created_at),
            },
            "players": {
                "total": len(players),
                "active": active_count,
                "checked_out": checked_out_count,
            },
            "chips": {
                "total_cash_in": game.bank.total_cash_in,
                "total_credit_in": game.bank.total_credits_issued,
                "total_in_play": game.bank.chips_in_play,
                "total_checked_out": game.bank.total_chips_returned,
            },
            "pending_requests": pending_requests,
            "credits_outstanding": credits_outstanding,
        }

    # ------------------------------------------------------------------
    # Player details
    # ------------------------------------------------------------------

    async def get_player_details(self, game_id: str, player_id: str) -> dict[str, Any]:
        """Get specific player details by player_token.

        Args:
            game_id: String ObjectId of the game.
            player_id: The player's UUID token.

        Returns:
            A dict with full player details including computed totals.

        Raises:
            HTTPException 404: Game or player not found.
        """
        # Ensure game exists
        await self.get_game(game_id)

        player = await self._player_dal.get_by_token(game_id, player_id)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found in this game",
            )

        totals = await self._compute_player_totals(game_id, player.player_token)
        total_buy_in = totals["total_cash_in"] + totals["total_credit_in"]
        current_chips = (
            player.final_chip_count
            if player.checked_out and player.final_chip_count is not None
            else total_buy_in
        )

        pending_requests = await self._chip_request_dal.count_pending_by_player(
            game_id, player.player_token
        )

        return {
            "player_id": str(player.id),
            "player_token": player.player_token,
            "display_name": player.display_name,
            "is_manager": player.is_manager,
            "is_active": player.is_active,
            "credits_owed": player.credits_owed,
            "checked_out": player.checked_out,
            "final_chip_count": player.final_chip_count,
            "profit_loss": player.profit_loss,
            "joined_at": player.joined_at.isoformat() if isinstance(player.joined_at, datetime) else str(player.joined_at),
            "checked_out_at": player.checked_out_at.isoformat() if player.checked_out_at else None,
            "total_cash_in": totals["total_cash_in"],
            "total_credit_in": totals["total_credit_in"],
            "current_chips": current_chips,
            "pending_requests": pending_requests,
        }

    # ------------------------------------------------------------------
    # Leave game
    # ------------------------------------------------------------------

    async def leave_game(self, game_id: str, player_token: str) -> dict[str, Any]:
        """Player leaves the game (soft delete by setting is_active=False).

        Args:
            game_id: String ObjectId of the game.
            player_token: The player's UUID token.

        Returns:
            A dict confirming the leave action with player details.

        Raises:
            HTTPException 404: Game or player not found.
            HTTPException 400: Player is not active, game is not OPEN,
                               manager cannot leave, player has pending requests,
                               or player has outstanding credits.
        """
        game = await self.get_game(game_id)

        # Game must be OPEN
        if game.status != GameStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot leave game: game is {game.status}",
            )

        player = await self._player_dal.get_by_token(game_id, player_token)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found in this game",
            )

        # Player must be active
        if not player.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player is not active in this game",
            )

        # Manager cannot leave their own game
        if player.is_manager:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager cannot leave their own game",
            )

        # Player must have no pending chip requests
        pending_count = await self._chip_request_dal.count_pending_by_player(
            game_id, player_token
        )
        if pending_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot leave: player has {pending_count} pending chip request(s)",
            )

        # Player must have no credits owed
        if player.credits_owed > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot leave: player owes {player.credits_owed} in credits",
            )

        # Soft delete: set is_active to False
        await self._player_dal.update_by_token(game_id, player_token, {"is_active": False})

        logger.info(
            "Player left game: game_id=%s player_token=%s name=%s",
            game_id,
            player_token,
            player.display_name,
        )

        return {
            "player_id": str(player.id),
            "player_token": player.player_token,
            "display_name": player.display_name,
            "left_at": datetime.now(timezone.utc).isoformat(),
        }
