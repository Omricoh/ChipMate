"""Unit tests for NotificationService business logic.

Tests cover:
    - create_notification
    - create_bulk_notifications (including empty list edge case)
    - get_player_notifications (unread_only vs all)
    - get_unread_count
    - mark_notification_read (ownership validation, not found)
    - mark_all_read
    - format_notification_message helper
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.dal.notifications_dal import NotificationDAL
from app.models.common import NotificationType
from app.models.notification import Notification
from app.services.notification_service import (
    NotificationService,
    format_notification_message,
    MESSAGE_TEMPLATES,
)


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
async def service(mock_db) -> NotificationService:
    """Provide a NotificationService instance backed by the mock database."""
    return NotificationService(notification_dal=NotificationDAL(mock_db))


@pytest_asyncio.fixture
async def notification_dal(mock_db) -> NotificationDAL:
    return NotificationDAL(mock_db)


GAME_ID = "665f1a2b3c4d5e6f7a8b9c0d"
PLAYER_TOKEN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PLAYER_TOKEN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# create_notification
# ---------------------------------------------------------------------------

class TestCreateNotification:

    @pytest.mark.asyncio
    async def test_create_notification_returns_notification_with_id(
        self, service: NotificationService
    ):
        result = await service.create_notification(
            game_id=GAME_ID,
            player_token=PLAYER_TOKEN_A,
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Your request was approved",
        )
        assert result.id is not None
        assert result.game_id == GAME_ID
        assert result.player_token == PLAYER_TOKEN_A
        assert result.notification_type == NotificationType.REQUEST_APPROVED
        assert result.message == "Your request was approved"
        assert result.is_read is False

    @pytest.mark.asyncio
    async def test_create_notification_with_related_id(
        self, service: NotificationService
    ):
        result = await service.create_notification(
            game_id=GAME_ID,
            player_token=PLAYER_TOKEN_A,
            notification_type=NotificationType.REQUEST_EDITED,
            message="Edited",
            related_id="some-request-id",
        )
        assert result.related_id == "some-request-id"


# ---------------------------------------------------------------------------
# create_bulk_notifications
# ---------------------------------------------------------------------------

class TestCreateBulkNotifications:

    @pytest.mark.asyncio
    async def test_bulk_create_multiple_players(
        self, service: NotificationService
    ):
        tokens = [PLAYER_TOKEN_A, PLAYER_TOKEN_B]
        result = await service.create_bulk_notifications(
            game_id=GAME_ID,
            player_tokens=tokens,
            notification_type=NotificationType.GAME_SETTLING,
            message="Game is settling",
        )
        assert len(result) == 2
        assert all(n.id is not None for n in result)
        returned_tokens = {n.player_token for n in result}
        assert returned_tokens == set(tokens)

    @pytest.mark.asyncio
    async def test_bulk_create_empty_list_returns_empty(
        self, service: NotificationService
    ):
        result = await service.create_bulk_notifications(
            game_id=GAME_ID,
            player_tokens=[],
            notification_type=NotificationType.GAME_CLOSED,
            message="Game closed",
        )
        assert result == []


# ---------------------------------------------------------------------------
# get_player_notifications
# ---------------------------------------------------------------------------

class TestGetPlayerNotifications:

    @pytest.mark.asyncio
    async def test_get_unread_only(self, service: NotificationService):
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "Approved",
        )
        result = await service.get_player_notifications(
            GAME_ID, PLAYER_TOKEN_A, unread_only=True,
        )
        assert len(result) == 1
        assert result[0].is_read is False

    @pytest.mark.asyncio
    async def test_get_all_including_read(
        self, service: NotificationService, notification_dal: NotificationDAL
    ):
        n = await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "Approved",
        )
        # Mark it as read directly via DAL
        await notification_dal.mark_read(n.id)

        # unread_only=True should return nothing
        unread = await service.get_player_notifications(
            GAME_ID, PLAYER_TOKEN_A, unread_only=True,
        )
        assert len(unread) == 0

        # unread_only=False should return the read notification
        all_notifs = await service.get_player_notifications(
            GAME_ID, PLAYER_TOKEN_A, unread_only=False,
        )
        assert len(all_notifs) == 1

    @pytest.mark.asyncio
    async def test_get_notifications_scoped_to_player(
        self, service: NotificationService
    ):
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "For A",
        )
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_B,
            NotificationType.REQUEST_DECLINED, "For B",
        )
        result_a = await service.get_player_notifications(
            GAME_ID, PLAYER_TOKEN_A, unread_only=True,
        )
        assert len(result_a) == 1
        assert result_a[0].player_token == PLAYER_TOKEN_A


# ---------------------------------------------------------------------------
# get_unread_count
# ---------------------------------------------------------------------------

class TestGetUnreadCount:

    @pytest.mark.asyncio
    async def test_unread_count_zero_initially(self, service: NotificationService):
        count = await service.get_unread_count(GAME_ID, PLAYER_TOKEN_A)
        assert count == 0

    @pytest.mark.asyncio
    async def test_unread_count_increments(self, service: NotificationService):
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "One",
        )
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_DECLINED, "Two",
        )
        count = await service.get_unread_count(GAME_ID, PLAYER_TOKEN_A)
        assert count == 2


# ---------------------------------------------------------------------------
# mark_notification_read
# ---------------------------------------------------------------------------

class TestMarkNotificationRead:

    @pytest.mark.asyncio
    async def test_mark_read_success(self, service: NotificationService):
        n = await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "Approved",
        )
        result = await service.mark_notification_read(n.id, PLAYER_TOKEN_A)
        assert result is True

        count = await service.get_unread_count(GAME_ID, PLAYER_TOKEN_A)
        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_read_wrong_player_raises_403(
        self, service: NotificationService
    ):
        from fastapi import HTTPException

        n = await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "Approved",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.mark_notification_read(n.id, PLAYER_TOKEN_B)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_mark_read_nonexistent_raises_404(
        self, service: NotificationService
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.mark_notification_read(
                "000000000000000000000000", PLAYER_TOKEN_A
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_read_invalid_id_raises_404(
        self, service: NotificationService
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.mark_notification_read("not-valid-id", PLAYER_TOKEN_A)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# mark_all_read
# ---------------------------------------------------------------------------

class TestMarkAllRead:

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_count(self, service: NotificationService):
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "One",
        )
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_DECLINED, "Two",
        )
        count = await service.mark_all_read(GAME_ID, PLAYER_TOKEN_A)
        assert count == 2

        remaining = await service.get_unread_count(GAME_ID, PLAYER_TOKEN_A)
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_when_none_returns_zero(
        self, service: NotificationService
    ):
        count = await service.mark_all_read(GAME_ID, PLAYER_TOKEN_A)
        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_does_not_affect_other_player(
        self, service: NotificationService
    ):
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_A,
            NotificationType.REQUEST_APPROVED, "For A",
        )
        await service.create_notification(
            GAME_ID, PLAYER_TOKEN_B,
            NotificationType.REQUEST_APPROVED, "For B",
        )

        await service.mark_all_read(GAME_ID, PLAYER_TOKEN_A)

        count_b = await service.get_unread_count(GAME_ID, PLAYER_TOKEN_B)
        assert count_b == 1


# ---------------------------------------------------------------------------
# format_notification_message helper
# ---------------------------------------------------------------------------

class TestFormatNotificationMessage:

    def test_request_approved_template(self):
        msg = format_notification_message(
            "REQUEST_APPROVED", type="cash", amount=100
        )
        assert "100" in msg
        assert "approved" in msg.lower()

    def test_request_declined_template(self):
        msg = format_notification_message(
            "REQUEST_DECLINED", type="credit", amount=50
        )
        assert "50" in msg
        assert "declined" in msg.lower()

    def test_request_edited_template(self):
        msg = format_notification_message(
            "REQUEST_EDITED", new_amount=75, original_amount=100
        )
        assert "75" in msg
        assert "100" in msg

    def test_checkout_processed_template(self):
        msg = format_notification_message(
            "CHECKOUT_PROCESSED", final_chips=120, profit_loss="+20"
        )
        assert "120" in msg

    def test_unknown_template_raises_key_error(self):
        with pytest.raises(KeyError):
            format_notification_message("NONEXISTENT_TEMPLATE")

    def test_missing_kwargs_raises_key_error(self):
        with pytest.raises(KeyError):
            format_notification_message("REQUEST_APPROVED")
