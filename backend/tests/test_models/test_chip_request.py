"""Tests for ChipRequest Pydantic model."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models.chip_request import ChipRequest, ChipRequestResponse
from app.models.common import RequestStatus, RequestType


class TestChipRequest:
    """Tests for the ChipRequest domain model."""

    def test_chip_request_creation_minimal(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="player-token-1",
            requested_by="player-token-1",
            request_type=RequestType.CASH,
            amount=100,
        )
        assert cr.game_id == "game1"
        assert cr.player_token == "player-token-1"
        assert cr.requested_by == "player-token-1"
        assert cr.request_type == RequestType.CASH
        assert cr.amount == 100
        assert cr.status == RequestStatus.PENDING
        assert cr.edited_amount is None
        assert cr.resolved_at is None
        assert cr.resolved_by is None
        assert isinstance(cr.created_at, datetime)
        assert cr.id is None

    def test_chip_request_credit_type(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CREDIT,
            amount=200,
        )
        assert cr.request_type == RequestType.CREDIT

    def test_chip_request_from_string_type(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type="CASH",
            amount=50,
        )
        assert cr.request_type == RequestType.CASH

    def test_chip_request_amount_must_be_positive(self):
        with pytest.raises(ValidationError) as exc_info:
            ChipRequest(
                game_id="game1",
                player_token="token1",
                requested_by="token1",
                request_type=RequestType.CASH,
                amount=0,
            )
        assert "amount" in str(exc_info.value).lower() or "greater_than" in str(exc_info.value).lower()

    def test_chip_request_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            ChipRequest(
                game_id="game1",
                player_token="token1",
                requested_by="token1",
                request_type=RequestType.CASH,
                amount=-50,
            )

    def test_chip_request_on_behalf_of(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="target-player",
            requested_by="manager-token",
            request_type=RequestType.CREDIT,
            amount=200,
        )
        assert cr.player_token == "target-player"
        assert cr.requested_by == "manager-token"
        assert cr.player_token != cr.requested_by

    def test_chip_request_approved_status(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
            status=RequestStatus.APPROVED,
            resolved_by="manager-token",
            resolved_at=datetime.now(timezone.utc),
        )
        assert cr.status == RequestStatus.APPROVED
        assert cr.effective_amount == 100

    def test_chip_request_declined_effective_amount(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
            status=RequestStatus.DECLINED,
            resolved_by="manager-token",
            resolved_at=datetime.now(timezone.utc),
        )
        assert cr.effective_amount == 0

    def test_chip_request_pending_effective_amount(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
        )
        assert cr.effective_amount == 0

    def test_chip_request_edited_status(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CREDIT,
            amount=200,
            status=RequestStatus.EDITED,
            edited_amount=150,
            resolved_by="manager-token",
            resolved_at=datetime.now(timezone.utc),
        )
        assert cr.status == RequestStatus.EDITED
        assert cr.edited_amount == 150
        assert cr.effective_amount == 150

    def test_chip_request_edited_without_edited_amount_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            ChipRequest(
                game_id="game1",
                player_token="token1",
                requested_by="token1",
                request_type=RequestType.CASH,
                amount=100,
                status=RequestStatus.EDITED,
                # edited_amount is missing
            )
        assert "edited_amount" in str(exc_info.value).lower()

    def test_chip_request_edited_amount_must_be_positive(self):
        with pytest.raises(ValidationError):
            ChipRequest(
                game_id="game1",
                player_token="token1",
                requested_by="token1",
                request_type=RequestType.CASH,
                amount=100,
                status=RequestStatus.EDITED,
                edited_amount=0,
            )

    def test_chip_request_with_objectid(self):
        oid = ObjectId()
        cr = ChipRequest(
            _id=oid,
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
        )
        assert cr.id == str(oid)

    def test_chip_request_to_mongo_dict(self):
        cr = ChipRequest(
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
        )
        doc = cr.to_mongo_dict()
        assert "_id" not in doc
        assert doc["game_id"] == "game1"
        assert doc["amount"] == 100
        assert doc["status"] == "PENDING"
        assert doc["request_type"] == "CASH"

    def test_chip_request_serialization_json(self):
        now = datetime(2026, 1, 30, 20, 0, 0, tzinfo=timezone.utc)
        cr = ChipRequest(
            _id=str(ObjectId()),
            game_id="game1",
            player_token="token1",
            requested_by="token1",
            request_type=RequestType.CASH,
            amount=100,
            created_at=now,
        )
        data = cr.model_dump(mode="json")
        assert isinstance(data["created_at"], str)
        assert data["resolved_at"] is None


class TestChipRequestResponse:
    """Tests for the ChipRequestResponse API model."""

    def test_chip_request_response_from_dict(self):
        data = {
            "_id": str(ObjectId()),
            "game_id": "game1",
            "player_token": "token1",
            "requested_by": "token1",
            "request_type": "CASH",
            "amount": 100,
            "status": "PENDING",
            "created_at": "2026-01-30T20:00:00+00:00",
        }
        resp = ChipRequestResponse(**data)
        assert resp.amount == 100
        assert resp.status == RequestStatus.PENDING
        assert resp.edited_amount is None
        assert resp.resolved_at is None
