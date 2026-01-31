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
from app.models.common import GameStatus
from app.models.game import Game
from app.models.player import Player

logger = logging.getLogger("chipmate.services.game")

# Characters for game code generation.
# Excludes ambiguous characters: I, O, 0, 1
_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6
_MAX_CODE_RETRIES = 10


class GameService:
    """Service layer for game-related operations."""

    def __init__(self, game_dal: GameDAL, player_dal: PlayerDAL) -> None:
        self._game_dal = game_dal
        self._player_dal = player_dal

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
        await self._player_dal.create(manager_player)

        logger.info(
            "Game created: id=%s code=%s manager=%s",
            game.id, code, manager_name,
        )

        return {
            "game_id": str(game.id),
            "game_code": game.code,
            "player_token": manager_token,
            "manager_name": manager_name,
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
            A dict with player_token, player_name, and game_id.

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
        await self._player_dal.create(player)

        logger.info(
            "Player joined: game_id=%s name=%s", game_id, player_name,
        )

        return {
            "player_token": player_token,
            "player_name": player_name,
            "game_id": game_id,
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
        return await self._player_dal.get_by_game(game_id, include_inactive=True)

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
        players = await self._player_dal.get_by_game(game_id, include_inactive=True)

        active_count = sum(1 for p in players if p.is_active)
        checked_out_count = sum(1 for p in players if p.checked_out)

        return {
            "game": {
                "game_id": str(game.id),
                "game_code": game.code,
                "status": str(game.status),
                "created_at": game.created_at.isoformat() if isinstance(game.created_at, datetime) else str(game.created_at),
            },
            "players": {
                "total": len(players),
                "active": active_count,
                "checked_out": checked_out_count,
            },
            "bank": {
                "total_cash_in": game.bank.total_cash_in,
                "total_credit_in": game.bank.total_credits_issued,
                "total_chips_in_play": game.bank.chips_in_play,
                "total_chips_issued": game.bank.total_chips_issued,
                "cash_balance": game.bank.cash_balance,
            },
        }
