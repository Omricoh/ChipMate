"""Unit tests for RequestService business logic.

Tests cover:
    - create_request (cash, credit, on-behalf-of, non-OPEN game, invalid amount)
    - approve_request (happy path, bank updates for cash and credit)
    - decline_request (happy path, already processed)
    - edit_and_approve_request (happy path, invalid amount, already processed)
    - get_pending_requests / get_player_requests
    - Request not found / request in wrong game validation
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.chip_requests_dal import ChipRequestDAL
from app.dal.games_dal import GameDAL
from app.dal.notifications_dal import NotificationDAL
from app.dal.players_dal import PlayerDAL
from app.models.common import GameStatus, RequestType, RequestStatus
from app.services.game_service import GameService
from app.services.request_service import RequestService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db():
    client = AsyncMongoMockClient()
    db = client["chipmate_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def game_dal(mock_db) -> GameDAL:
    return GameDAL(mock_db)


@pytest_asyncio.fixture
async def player_dal(mock_db) -> PlayerDAL:
    return PlayerDAL(mock_db)


@pytest_asyncio.fixture
async def chip_request_dal(mock_db) -> ChipRequestDAL:
    return ChipRequestDAL(mock_db)


@pytest_asyncio.fixture
async def notification_dal(mock_db) -> NotificationDAL:
    return NotificationDAL(mock_db)


@pytest_asyncio.fixture
async def game_service(game_dal, player_dal, chip_request_dal) -> GameService:
    return GameService(game_dal, player_dal, chip_request_dal)


@pytest_asyncio.fixture
async def request_service(
    game_dal, player_dal, chip_request_dal, notification_dal
) -> RequestService:
    return RequestService(game_dal, player_dal, chip_request_dal, notification_dal)


@pytest_asyncio.fixture
async def open_game(game_service):
    """Create an open game with manager 'Alice' and return game data."""
    return await game_service.create_game(manager_name="Alice")


@pytest_asyncio.fixture
async def player_bob(game_service, open_game):
    """Join an open game as 'Bob' and return join data."""
    return await game_service.join_game(
        game_id=open_game["game_id"], player_name="Bob"
    )


# ---------------------------------------------------------------------------
# create_request
# ---------------------------------------------------------------------------

class TestCreateRequest:

    @pytest.mark.asyncio
    async def test_create_cash_request(
        self, request_service, open_game, player_bob
    ):
        result = await request_service.create_request(
            game_id=open_game["game_id"],
            player_token=player_bob["player_token"],
            request_type=RequestType.CASH,
            amount=100,
        )
        assert result.id is not None
        assert result.game_id == open_game["game_id"]
        assert result.player_token == player_bob["player_token"]
        assert result.request_type == RequestType.CASH
        assert result.amount == 100
        assert result.status == RequestStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_credit_request(
        self, request_service, open_game, player_bob
    ):
        result = await request_service.create_request(
            game_id=open_game["game_id"],
            player_token=player_bob["player_token"],
            request_type=RequestType.CREDIT,
            amount=50,
        )
        assert result.request_type == RequestType.CREDIT
        assert result.amount == 50

    @pytest.mark.asyncio
    async def test_create_request_on_behalf_of(
        self, request_service, game_service, open_game, player_bob
    ):
        """Manager creates request on behalf of another player."""
        manager_token = open_game["player_token"]
        result = await request_service.create_request(
            game_id=open_game["game_id"],
            player_token=manager_token,
            request_type=RequestType.CASH,
            amount=200,
            on_behalf_of_token=player_bob["player_token"],
        )
        # The request should be for Bob, submitted by manager
        assert result.player_token == player_bob["player_token"]
        assert result.requested_by == manager_token

    @pytest.mark.asyncio
    async def test_create_request_non_open_game_raises_400(
        self, request_service, game_dal, open_game, player_bob
    ):
        from fastapi import HTTPException

        await game_dal.update_status(open_game["game_id"], GameStatus.SETTLING)

        with pytest.raises(HTTPException) as exc_info:
            await request_service.create_request(
                game_id=open_game["game_id"],
                player_token=player_bob["player_token"],
                request_type=RequestType.CASH,
                amount=100,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_request_nonexistent_game_raises_404(
        self, request_service, player_bob
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.create_request(
                game_id="000000000000000000000000",
                player_token=player_bob["player_token"],
                request_type=RequestType.CASH,
                amount=100,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_request_nonexistent_player_raises_404(
        self, request_service, open_game
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.create_request(
                game_id=open_game["game_id"],
                player_token="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                request_type=RequestType.CASH,
                amount=100,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_request_zero_amount_raises_400(
        self, request_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.create_request(
                game_id=open_game["game_id"],
                player_token=player_bob["player_token"],
                request_type=RequestType.CASH,
                amount=0,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_request_negative_amount_raises_400(
        self, request_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.create_request(
                game_id=open_game["game_id"],
                player_token=player_bob["player_token"],
                request_type=RequestType.CASH,
                amount=-50,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# approve_request
# ---------------------------------------------------------------------------

class TestApproveRequest:

    @pytest.mark.asyncio
    async def test_approve_cash_request_updates_bank(
        self, request_service, game_dal, open_game, player_bob
    ):
        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        result = await request_service.approve_request(
            open_game["game_id"], req.id, open_game["player_token"],
        )
        assert result.status == RequestStatus.APPROVED

        # Verify bank was updated
        game = await game_dal.get_by_id(open_game["game_id"])
        assert game.bank.total_cash_in == 100
        assert game.bank.cash_balance == 100
        assert game.bank.total_chips_issued == 100
        assert game.bank.chips_in_play == 100

    @pytest.mark.asyncio
    async def test_approve_credit_request_updates_bank_and_player(
        self, request_service, game_dal, player_dal, open_game, player_bob
    ):
        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CREDIT, 75,
        )
        await request_service.approve_request(
            open_game["game_id"], req.id, open_game["player_token"],
        )

        # Bank should track credits
        game = await game_dal.get_by_id(open_game["game_id"])
        assert game.bank.total_credits_issued == 75
        assert game.bank.total_cash_in == 0  # no cash for credit
        assert game.bank.total_chips_issued == 75

        # Player should have credits_owed incremented
        player = await player_dal.get_by_token(
            open_game["game_id"], player_bob["player_token"]
        )
        assert player.credits_owed == 75

    @pytest.mark.asyncio
    async def test_approve_nonexistent_request_raises_404(
        self, request_service, open_game
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.approve_request(
                open_game["game_id"],
                "000000000000000000000000",
                open_game["player_token"],
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_request_wrong_game_raises_404(
        self, request_service, game_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        # Create another game
        other_game = await game_service.create_game("OtherManager")

        with pytest.raises(HTTPException) as exc_info:
            await request_service.approve_request(
                other_game["game_id"], req.id, other_game["player_token"],
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# decline_request
# ---------------------------------------------------------------------------

class TestDeclineRequest:

    @pytest.mark.asyncio
    async def test_decline_request_no_bank_changes(
        self, request_service, game_dal, open_game, player_bob
    ):
        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        result = await request_service.decline_request(
            open_game["game_id"], req.id, open_game["player_token"],
        )
        assert result.status == RequestStatus.DECLINED

        # Bank should remain at zero
        game = await game_dal.get_by_id(open_game["game_id"])
        assert game.bank.total_cash_in == 0
        assert game.bank.chips_in_play == 0

    @pytest.mark.asyncio
    async def test_decline_already_approved_raises_400(
        self, request_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        await request_service.approve_request(
            open_game["game_id"], req.id, open_game["player_token"],
        )
        with pytest.raises(HTTPException) as exc_info:
            await request_service.decline_request(
                open_game["game_id"], req.id, open_game["player_token"],
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# edit_and_approve_request
# ---------------------------------------------------------------------------

class TestEditAndApproveRequest:

    @pytest.mark.asyncio
    async def test_edit_and_approve_uses_new_amount_for_bank(
        self, request_service, game_dal, open_game, player_bob
    ):
        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        result = await request_service.edit_and_approve_request(
            open_game["game_id"], req.id, new_amount=60,
            new_type=None,
            manager_token=open_game["player_token"],
        )
        assert result.status == RequestStatus.EDITED
        assert result.edited_amount == 60

        # Bank should use the NEW amount (60), not original (100)
        game = await game_dal.get_by_id(open_game["game_id"])
        assert game.bank.total_cash_in == 60
        assert game.bank.total_chips_issued == 60

    @pytest.mark.asyncio
    async def test_edit_with_zero_amount_raises_400(
        self, request_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        with pytest.raises(HTTPException) as exc_info:
            await request_service.edit_and_approve_request(
                open_game["game_id"], req.id, new_amount=0,
                new_type=None,
                manager_token=open_game["player_token"],
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_edit_already_declined_raises_400(
        self, request_service, open_game, player_bob
    ):
        from fastapi import HTTPException

        req = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        await request_service.decline_request(
            open_game["game_id"], req.id, open_game["player_token"],
        )
        with pytest.raises(HTTPException) as exc_info:
            await request_service.edit_and_approve_request(
                open_game["game_id"], req.id, new_amount=50,
                new_type=None,
                manager_token=open_game["player_token"],
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# get_pending_requests / get_player_requests
# ---------------------------------------------------------------------------

class TestQueryMethods:

    @pytest.mark.asyncio
    async def test_get_pending_requests_returns_only_pending(
        self, request_service, open_game, player_bob
    ):
        req1 = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        req2 = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 50,
        )
        # Approve req1
        await request_service.approve_request(
            open_game["game_id"], req1.id, open_game["player_token"],
        )

        pending = await request_service.get_pending_requests(open_game["game_id"])
        assert len(pending) == 1
        assert pending[0].id == req2.id

    @pytest.mark.asyncio
    async def test_get_player_requests_returns_all_statuses(
        self, request_service, open_game, player_bob
    ):
        req1 = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CASH, 100,
        )
        req2 = await request_service.create_request(
            open_game["game_id"], player_bob["player_token"],
            RequestType.CREDIT, 50,
        )
        await request_service.approve_request(
            open_game["game_id"], req1.id, open_game["player_token"],
        )

        requests = await request_service.get_player_requests(
            open_game["game_id"], player_bob["player_token"],
        )
        assert len(requests) == 2

    @pytest.mark.asyncio
    async def test_get_pending_for_nonexistent_game_raises_404(
        self, request_service
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await request_service.get_pending_requests("000000000000000000000000")
        assert exc_info.value.status_code == 404
