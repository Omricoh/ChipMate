"""Tests for Game and Bank Pydantic models."""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models.game import Bank, Game, GameResponse
from app.models.common import GameStatus


class TestBank:
    """Tests for the Bank embedded model."""

    def test_bank_defaults(self):
        bank = Bank()
        assert bank.cash_balance == 0
        assert bank.total_cash_in == 0
        assert bank.total_cash_out == 0
        assert bank.total_credits_issued == 0
        assert bank.total_credits_repaid == 0
        assert bank.total_chips_issued == 0
        assert bank.total_chips_returned == 0
        assert bank.chips_in_play == 0

    def test_bank_with_values(self):
        bank = Bank(
            cash_balance=500,
            total_cash_in=800,
            total_cash_out=300,
            total_credits_issued=200,
            total_credits_repaid=50,
            total_chips_issued=1000,
            total_chips_returned=300,
            chips_in_play=700,
        )
        assert bank.cash_balance == 500
        assert bank.chips_in_play == 700

    def test_bank_serialization(self):
        bank = Bank(cash_balance=100, total_cash_in=100)
        data = bank.model_dump()
        assert data["cash_balance"] == 100
        assert data["total_cash_in"] == 100
        assert isinstance(data["cash_balance"], int)


class TestGame:
    """Tests for the Game domain model."""

    def test_game_creation_minimal(self):
        game = Game(
            code="ABC123",
            manager_player_token="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        )
        assert game.code == "ABC123"
        assert game.manager_player_token == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert game.status == GameStatus.OPEN
        assert game.id is None
        assert game.closed_at is None
        assert isinstance(game.created_at, datetime)
        assert isinstance(game.expires_at, datetime)
        assert isinstance(game.bank, Bank)
        assert game.bank.cash_balance == 0

    def test_game_expires_at_is_12h_after_created(self):
        game = Game(
            code="XYZ789",
            manager_player_token="token-123",
        )
        delta = game.expires_at - game.created_at
        # Should be approximately 12 hours (allow 1 second tolerance)
        assert abs(delta.total_seconds() - 43200) < 1  # 12 * 60 * 60 = 43200

    def test_game_with_objectid_string(self):
        oid = str(ObjectId())
        game = Game(
            _id=oid,
            code="ABC123",
            manager_player_token="token-123",
        )
        assert game.id == oid

    def test_game_with_bson_objectid(self):
        oid = ObjectId()
        game = Game(
            _id=oid,
            code="ABC123",
            manager_player_token="token-123",
        )
        assert game.id == str(oid)

    def test_game_status_enum(self):
        game = Game(
            code="ABC123",
            manager_player_token="token-123",
            status=GameStatus.SETTLING,
        )
        assert game.status == GameStatus.SETTLING
        assert game.status == "SETTLING"

    def test_game_status_from_string(self):
        game = Game(
            code="ABC123",
            manager_player_token="token-123",
            status="CLOSED",
        )
        assert game.status == GameStatus.CLOSED

    def test_game_invalid_status(self):
        with pytest.raises(ValidationError):
            Game(
                code="ABC123",
                manager_player_token="token-123",
                status="INVALID",
            )

    def test_game_to_mongo_dict_no_id(self):
        game = Game(
            code="ABC123",
            manager_player_token="token-123",
        )
        doc = game.to_mongo_dict()
        assert "_id" not in doc
        assert doc["code"] == "ABC123"
        assert doc["status"] == "OPEN"
        assert isinstance(doc["bank"], dict)
        assert doc["bank"]["cash_balance"] == 0

    def test_game_to_mongo_dict_with_id(self):
        oid = str(ObjectId())
        game = Game(
            _id=oid,
            code="ABC123",
            manager_player_token="token-123",
        )
        doc = game.to_mongo_dict()
        assert doc["_id"] == oid

    def test_game_serialization_json(self):
        now = datetime(2026, 1, 30, 20, 0, 0, tzinfo=timezone.utc)
        game = Game(
            _id=str(ObjectId()),
            code="ABC123",
            manager_player_token="token-123",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        data = game.model_dump(mode="json")
        # Datetime should be ISO string
        assert isinstance(data["created_at"], str)
        assert "2026-01-30" in data["created_at"]
        assert data["closed_at"] is None

    def test_game_with_closed_at(self):
        now = datetime.now(timezone.utc)
        game = Game(
            code="ABC123",
            manager_player_token="token-123",
            status=GameStatus.CLOSED,
            closed_at=now,
        )
        assert game.closed_at == now
        assert game.status == GameStatus.CLOSED

    def test_game_bank_embedded(self):
        bank = Bank(cash_balance=500, total_chips_issued=1000)
        game = Game(
            code="ABC123",
            manager_player_token="token-123",
            bank=bank,
        )
        assert game.bank.cash_balance == 500
        assert game.bank.total_chips_issued == 1000


class TestGameResponse:
    """Tests for the GameResponse API model."""

    def test_game_response_from_dict(self):
        data = {
            "_id": str(ObjectId()),
            "code": "ABC123",
            "status": "OPEN",
            "manager_player_token": "token-123",
            "created_at": "2026-01-30T20:00:00+00:00",
            "expires_at": "2026-01-31T20:00:00+00:00",
            "bank": {
                "cash_balance": 0,
                "total_cash_in": 0,
                "total_cash_out": 0,
                "total_credits_issued": 0,
                "total_credits_repaid": 0,
                "total_chips_issued": 0,
                "total_chips_returned": 0,
                "chips_in_play": 0,
            },
        }
        resp = GameResponse(**data)
        assert resp.code == "ABC123"
        assert resp.status == GameStatus.OPEN
        assert resp.closed_at is None
