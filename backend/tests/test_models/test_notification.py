"""Tests for Notification Pydantic model."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models.notification import Notification, NotificationResponse
from app.models.common import NotificationType


class TestNotification:
    """Tests for the Notification domain model."""

    def test_notification_creation_minimal(self):
        n = Notification(
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Your 100-chip cash buy-in has been approved.",
        )
        assert n.game_id == "game1"
        assert n.player_token == "token1"
        assert n.notification_type == NotificationType.REQUEST_APPROVED
        assert n.message == "Your 100-chip cash buy-in has been approved."
        assert n.related_id is None
        assert n.is_read is False
        assert isinstance(n.created_at, datetime)
        assert n.id is None

    def test_notification_all_types(self):
        for ntype in NotificationType:
            n = Notification(
                game_id="game1",
                player_token="token1",
                notification_type=ntype,
                message=f"Test message for {ntype}",
            )
            assert n.notification_type == ntype

    def test_notification_invalid_type(self):
        with pytest.raises(ValidationError):
            Notification(
                game_id="game1",
                player_token="token1",
                notification_type="INVALID_TYPE",
                message="This should fail.",
            )

    def test_notification_with_related_id(self):
        related = str(ObjectId())
        n = Notification(
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.REQUEST_EDITED,
            message="Your request was edited.",
            related_id=related,
        )
        assert n.related_id == related

    def test_notification_is_read(self):
        n = Notification(
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.GAME_CLOSED,
            message="The game has been closed.",
            is_read=True,
        )
        assert n.is_read is True

    def test_notification_with_objectid(self):
        oid = ObjectId()
        n = Notification(
            _id=oid,
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.CHECKOUT_COMPLETE,
            message="You have been checked out.",
        )
        assert n.id == str(oid)

    def test_notification_to_mongo_dict_no_id(self):
        n = Notification(
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.ON_BEHALF_SUBMITTED,
            message="Manager submitted a request for you.",
        )
        doc = n.to_mongo_dict()
        assert "_id" not in doc
        assert doc["game_id"] == "game1"
        assert doc["notification_type"] == "ON_BEHALF_SUBMITTED"
        assert doc["is_read"] is False

    def test_notification_to_mongo_dict_with_id(self):
        oid = str(ObjectId())
        n = Notification(
            _id=oid,
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.GAME_SETTLING,
            message="Game is now settling.",
        )
        doc = n.to_mongo_dict()
        assert doc["_id"] == oid

    def test_notification_serialization_json(self):
        now = datetime(2026, 1, 30, 20, 16, 0, tzinfo=timezone.utc)
        n = Notification(
            _id=str(ObjectId()),
            game_id="game1",
            player_token="token1",
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Approved.",
            created_at=now,
        )
        data = n.model_dump(mode="json")
        assert isinstance(data["created_at"], str)
        assert "2026-01-30" in data["created_at"]

    def test_notification_missing_required_field(self):
        with pytest.raises(ValidationError):
            Notification(
                game_id="game1",
                player_token="token1",
                # notification_type is missing
                message="This should fail.",
            )

    def test_notification_message_required(self):
        with pytest.raises(ValidationError):
            Notification(
                game_id="game1",
                player_token="token1",
                notification_type=NotificationType.GAME_CLOSED,
                # message is missing
            )


class TestNotificationResponse:
    """Tests for the NotificationResponse API model."""

    def test_notification_response_from_dict(self):
        data = {
            "_id": str(ObjectId()),
            "game_id": "game1",
            "player_token": "token1",
            "notification_type": "REQUEST_APPROVED",
            "message": "Approved.",
            "is_read": False,
            "created_at": "2026-01-30T20:16:00+00:00",
        }
        resp = NotificationResponse(**data)
        assert resp.notification_type == NotificationType.REQUEST_APPROVED
        assert resp.is_read is False
        assert resp.related_id is None

    def test_notification_response_with_related_id(self):
        data = {
            "_id": str(ObjectId()),
            "game_id": "game1",
            "player_token": "token1",
            "notification_type": "REQUEST_EDITED",
            "message": "Edited.",
            "related_id": str(ObjectId()),
            "is_read": True,
            "created_at": "2026-01-30T20:16:00+00:00",
        }
        resp = NotificationResponse(**data)
        assert resp.related_id is not None
        assert resp.is_read is True
