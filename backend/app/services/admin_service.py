"""Admin business logic service.

Provides methods for admin dashboard: listing games, game detail,
force-closing games, and aggregate statistics.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus
from app.models.game import Game

logger = logging.getLogger("chipmate.services.admin")


class AdminService:
    """Service layer for admin-specific operations."""

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
    # List games
    # ------------------------------------------------------------------

    async def list_games(
        self,
        status_filter: Optional[GameStatus],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """List games with optional status filter, sorted by created_at desc.

        Args:
            status_filter: Optional GameStatus to filter by.
            limit: Maximum number of results.
            offset: Number of documents to skip.

        Returns:
            A list of dicts with game summary information.
        """
        if status_filter is not None:
            games = await self._game_dal.list_by_status(
                status=status_filter, limit=limit, skip=offset
            )
        else:
            games = await self._game_dal.list_all(limit=limit, skip=offset)

        results: list[dict[str, Any]] = []
        for game in games:
            game_id = str(game.id)
            players = await self._player_dal.get_by_game(
                game_id, include_inactive=True
            )
            created_at_str = (
                game.created_at.isoformat()
                if hasattr(game.created_at, "isoformat")
                else str(game.created_at)
            )
            results.append({
                "game_id": game_id,
                "game_code": game.code,
                "status": str(game.status),
                "player_count": len(players),
                "bank": {
                    "cash_balance": game.bank.cash_balance,
                    "total_cash_in": game.bank.total_cash_in,
                    "total_cash_out": game.bank.total_cash_out,
                    "chips_in_play": game.bank.chips_in_play,
                },
                "created_at": created_at_str,
            })

        return results

    # ------------------------------------------------------------------
    # Game detail
    # ------------------------------------------------------------------

    async def get_game_detail(self, game_id: str) -> dict[str, Any]:
        """Get detailed information about a single game.

        Includes the full game document, all players, and request stats.

        Args:
            game_id: String ObjectId of the game.

        Returns:
            A dict with game, players, and request_stats.

        Raises:
            HTTPException 404: Game not found.
        """
        game = await self._game_dal.get_by_id(game_id)
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )

        players = await self._player_dal.get_by_game(
            game_id, include_inactive=True
        )

        # Request stats
        all_requests = await self._chip_request_dal.get_by_game(
            game_id, limit=10000
        )
        total_requests = len(all_requests)
        pending_requests = sum(
            1 for r in all_requests if str(r.status) == "PENDING"
        )
        approved_requests = sum(
            1 for r in all_requests
            if str(r.status) in ("APPROVED", "EDITED")
        )

        created_at_str = (
            game.created_at.isoformat()
            if hasattr(game.created_at, "isoformat")
            else str(game.created_at)
        )
        closed_at_str = (
            game.closed_at.isoformat()
            if game.closed_at and hasattr(game.closed_at, "isoformat")
            else None
        )
        expires_at_str = (
            game.expires_at.isoformat()
            if hasattr(game.expires_at, "isoformat")
            else str(game.expires_at)
        )

        player_list = []
        for p in players:
            joined_at_str = (
                p.joined_at.isoformat()
                if hasattr(p.joined_at, "isoformat")
                else str(p.joined_at)
            )
            player_list.append({
                "player_id": str(p.id),
                "player_token": p.player_token,
                "display_name": p.display_name,
                "is_manager": p.is_manager,
                "is_active": p.is_active,
                "credits_owed": p.credits_owed,
                "checked_out": p.checked_out,
                "joined_at": joined_at_str,
            })

        return {
            "game": {
                "game_id": str(game.id),
                "game_code": game.code,
                "status": str(game.status),
                "manager_player_token": game.manager_player_token,
                "created_at": created_at_str,
                "closed_at": closed_at_str,
                "expires_at": expires_at_str,
                "bank": {
                    "cash_balance": game.bank.cash_balance,
                    "total_cash_in": game.bank.total_cash_in,
                    "total_cash_out": game.bank.total_cash_out,
                    "total_credits_issued": game.bank.total_credits_issued,
                    "total_credits_repaid": game.bank.total_credits_repaid,
                    "total_chips_issued": game.bank.total_chips_issued,
                    "total_chips_returned": game.bank.total_chips_returned,
                    "chips_in_play": game.bank.chips_in_play,
                },
            },
            "players": player_list,
            "request_stats": {
                "total": total_requests,
                "pending": pending_requests,
                "approved": approved_requests,
            },
        }

    # ------------------------------------------------------------------
    # Force close game
    # ------------------------------------------------------------------

    async def force_close_game(self, game_id: str) -> Game:
        """Force close a game regardless of current status.

        Sets status to CLOSED and records closed_at timestamp.

        Args:
            game_id: String ObjectId of the game.

        Returns:
            The updated Game model.

        Raises:
            HTTPException 404: Game not found.
        """
        game = await self._game_dal.get_by_id(game_id)
        if game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )

        now = datetime.now(timezone.utc)
        await self._game_dal.update_status(
            game_id, GameStatus.CLOSED, closed_at=now
        )

        # Refresh and return
        game.status = GameStatus.CLOSED
        game.closed_at = now

        logger.info("Game %s force-closed by admin", game_id)
        return game

    # ------------------------------------------------------------------
    # Dashboard stats
    # ------------------------------------------------------------------

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """Get aggregate dashboard statistics.

        Returns:
            A dict with total_games, active_games, settling_games,
            closed_games, and total_players.
        """
        total_games = await self._game_dal.count_all()
        active_games = await self._game_dal.count_by_status(GameStatus.OPEN)
        settling_games = await self._game_dal.count_by_status(GameStatus.SETTLING)
        closed_games = await self._game_dal.count_by_status(GameStatus.CLOSED)
        total_players = await self._player_dal.count_all()

        return {
            "total_games": total_games,
            "active_games": active_games,
            "settling_games": settling_games,
            "closed_games": closed_games,
            "total_players": total_players,
        }
