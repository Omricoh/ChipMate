"""Unit tests for the GameService business logic layer.

Tests cover:
    - Game code generation (format, uniqueness, retries)
    - Game creation (game + manager player record)
    - Joining a game (OPEN, SETTLING, CLOSED states)
    - Game status / bankroll calculation
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus
from app.models.game import Game
from app.services.game_service import GameService, _CODE_CHARS, _CODE_LENGTH


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    """Provide an in-memory mock MongoDB database."""
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def service(mock_db) -> GameService:
    """Provide a GameService instance backed by the mock database."""
    game_dal = GameDAL(mock_db)
    player_dal = PlayerDAL(mock_db)
    chip_request_dal = ChipRequestDAL(mock_db)
    return GameService(game_dal, player_dal, chip_request_dal)


@pytest_asyncio.fixture
async def game_dal(mock_db) -> GameDAL:
    return GameDAL(mock_db)


@pytest_asyncio.fixture
async def player_dal(mock_db) -> PlayerDAL:
    return PlayerDAL(mock_db)


# ---------------------------------------------------------------------------
# Game code generation
# ---------------------------------------------------------------------------

class TestGenerateGameCode:
    """Tests for GameService.generate_game_code."""

    @pytest.mark.asyncio
    async def test_code_is_6_characters(self, service: GameService):
        code = await service.generate_game_code()
        assert len(code) == _CODE_LENGTH

    @pytest.mark.asyncio
    async def test_code_uses_unambiguous_characters(self, service: GameService):
        """Code should only contain characters from the allowed set."""
        for _ in range(20):
            code = await service.generate_game_code()
            for char in code:
                assert char in _CODE_CHARS, (
                    f"Character '{char}' not in allowed set"
                )

    @pytest.mark.asyncio
    async def test_code_excludes_ambiguous_characters(self, service: GameService):
        """Code must never contain I, O, 0, or 1."""
        ambiguous = set("IO01")
        for _ in range(50):
            code = await service.generate_game_code()
            assert ambiguous.isdisjoint(set(code)), (
                f"Code '{code}' contains ambiguous characters"
            )

    @pytest.mark.asyncio
    async def test_code_is_uppercase(self, service: GameService):
        code = await service.generate_game_code()
        assert code == code.upper()


# ---------------------------------------------------------------------------
# Game creation
# ---------------------------------------------------------------------------

class TestCreateGame:
    """Tests for GameService.create_game."""

    @pytest.mark.asyncio
    async def test_create_game_returns_expected_keys(self, service: GameService):
        result = await service.create_game(manager_name="Alice")
        assert "game_id" in result
        assert "game_code" in result
        assert "player_token" in result
        assert "manager_name" in result

    @pytest.mark.asyncio
    async def test_create_game_code_format(self, service: GameService):
        result = await service.create_game(manager_name="Alice")
        code = result["game_code"]
        assert len(code) == 6
        for ch in code:
            assert ch in _CODE_CHARS

    @pytest.mark.asyncio
    async def test_create_game_stores_game_in_db(
        self, service: GameService, game_dal: GameDAL
    ):
        result = await service.create_game(manager_name="Bob")
        game = await game_dal.get_by_id(result["game_id"])
        assert game is not None
        assert game.code == result["game_code"]
        assert game.status == GameStatus.OPEN

    @pytest.mark.asyncio
    async def test_create_game_stores_manager_player(
        self, service: GameService, player_dal: PlayerDAL
    ):
        result = await service.create_game(manager_name="Charlie")
        player = await player_dal.get_by_token(
            result["game_id"], result["player_token"]
        )
        assert player is not None
        assert player.display_name == "Charlie"
        assert player.is_manager is True
        assert player.is_active is True

    @pytest.mark.asyncio
    async def test_create_game_sets_expires_at(
        self, service: GameService, game_dal: GameDAL
    ):
        """auto_close_at / expires_at should be ~24 hours after created_at."""
        result = await service.create_game(manager_name="Dana")
        game = await game_dal.get_by_id(result["game_id"])
        assert game is not None
        delta = game.expires_at - game.created_at
        # Allow a small tolerance for test execution time
        assert 23.9 * 3600 <= delta.total_seconds() <= 24.1 * 3600

    @pytest.mark.asyncio
    async def test_create_game_manager_token_matches_game(
        self, service: GameService, game_dal: GameDAL
    ):
        result = await service.create_game(manager_name="Eve")
        game = await game_dal.get_by_id(result["game_id"])
        assert game is not None
        assert game.manager_player_token == result["player_token"]


# ---------------------------------------------------------------------------
# Get game
# ---------------------------------------------------------------------------

class TestGetGame:
    """Tests for GameService.get_game and get_game_by_code."""

    @pytest.mark.asyncio
    async def test_get_game_found(self, service: GameService):
        result = await service.create_game(manager_name="Alice")
        game = await service.get_game(result["game_id"])
        assert str(game.id) == result["game_id"]

    @pytest.mark.asyncio
    async def test_get_game_not_found_raises_404(self, service: GameService):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_game("000000000000000000000000")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_game_by_code_found(self, service: GameService):
        result = await service.create_game(manager_name="Alice")
        game = await service.get_game_by_code(result["game_code"])
        assert str(game.id) == result["game_id"]

    @pytest.mark.asyncio
    async def test_get_game_by_code_not_found_raises_404(self, service: GameService):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_game_by_code("ZZZZZZ")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_game_by_code_case_insensitive(self, service: GameService):
        result = await service.create_game(manager_name="Alice")
        code = result["game_code"]
        game = await service.get_game_by_code(code.lower())
        assert str(game.id) == result["game_id"]


# ---------------------------------------------------------------------------
# Join game
# ---------------------------------------------------------------------------

class TestJoinGame:
    """Tests for GameService.join_game."""

    @pytest.mark.asyncio
    async def test_join_open_game_succeeds(self, service: GameService):
        game_result = await service.create_game(manager_name="Alice")
        join_result = await service.join_game(
            game_id=game_result["game_id"], player_name="Bob"
        )
        assert "player_id" in join_result
        assert "player_token" in join_result
        assert "game" in join_result
        assert join_result["game"]["game_id"] == game_result["game_id"]
        assert join_result["game"]["game_code"] == game_result["game_code"]
        assert join_result["game"]["manager_name"] == "Alice"
        assert join_result["game"]["status"] == "OPEN"

    @pytest.mark.asyncio
    async def test_join_game_creates_player_record(
        self, service: GameService, player_dal: PlayerDAL
    ):
        game_result = await service.create_game(manager_name="Alice")
        join_result = await service.join_game(
            game_id=game_result["game_id"], player_name="Bob"
        )
        player = await player_dal.get_by_token(
            game_result["game_id"], join_result["player_token"]
        )
        assert player is not None
        assert player.display_name == "Bob"
        assert player.is_manager is False

    @pytest.mark.asyncio
    async def test_join_settling_game_raises_400(
        self, service: GameService, game_dal: GameDAL
    ):
        game_result = await service.create_game(manager_name="Alice")
        await game_dal.update_status(game_result["game_id"], GameStatus.SETTLING)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.join_game(
                game_id=game_result["game_id"], player_name="Bob"
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_join_closed_game_raises_400(
        self, service: GameService, game_dal: GameDAL
    ):
        from datetime import datetime, timezone

        game_result = await service.create_game(manager_name="Alice")
        await game_dal.update_status(
            game_result["game_id"],
            GameStatus.CLOSED,
            closed_at=datetime.now(timezone.utc),
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.join_game(
                game_id=game_result["game_id"], player_name="Bob"
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_join_nonexistent_game_raises_404(self, service: GameService):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.join_game(
                game_id="000000000000000000000000", player_name="Bob"
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Game status / bankroll
# ---------------------------------------------------------------------------

class TestGameStatus:
    """Tests for GameService.get_game_status."""

    @pytest.mark.asyncio
    async def test_status_returns_expected_structure(self, service: GameService):
        game_result = await service.create_game(manager_name="Alice")
        status_data = await service.get_game_status(game_result["game_id"])

        assert "game" in status_data
        assert "players" in status_data
        assert "chips" in status_data

        assert status_data["game"]["game_id"] == game_result["game_id"]
        assert status_data["game"]["status"] == "OPEN"
        assert status_data["players"]["total"] == 1  # manager
        assert status_data["players"]["active"] == 1

    @pytest.mark.asyncio
    async def test_status_player_count_increases_on_join(
        self, service: GameService
    ):
        game_result = await service.create_game(manager_name="Alice")
        await service.join_game(game_result["game_id"], "Bob")
        await service.join_game(game_result["game_id"], "Charlie")

        status_data = await service.get_game_status(game_result["game_id"])
        assert status_data["players"]["total"] == 3  # Alice + Bob + Charlie
        assert status_data["players"]["active"] == 3

    @pytest.mark.asyncio
    async def test_status_bank_starts_at_zero(self, service: GameService):
        game_result = await service.create_game(manager_name="Alice")
        status_data = await service.get_game_status(game_result["game_id"])
        chips = status_data["chips"]
        assert chips["total_cash_in"] == 0
        assert chips["total_credit_in"] == 0
        assert chips["total_in_play"] == 0


# ---------------------------------------------------------------------------
# Get game players
# ---------------------------------------------------------------------------

class TestGetGamePlayers:
    """Tests for GameService.get_game_players."""

    @pytest.mark.asyncio
    async def test_returns_all_players(self, service: GameService):
        game_result = await service.create_game(manager_name="Alice")
        await service.join_game(game_result["game_id"], "Bob")
        players = await service.get_game_players(game_result["game_id"])
        assert len(players) == 2
        names = {p.display_name for p in players}
        assert names == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_empty_game_has_only_manager(self, service: GameService):
        game_result = await service.create_game(manager_name="Alice")
        players = await service.get_game_players(game_result["game_id"])
        assert len(players) == 1
        assert players[0].display_name == "Alice"
        assert players[0].is_manager is True
