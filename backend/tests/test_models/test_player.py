"""Tests for Player Pydantic model."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models.player import Player, PlayerResponse


class TestPlayer:
    """Tests for the Player domain model."""

    def test_player_creation_minimal(self):
        player = Player(
            game_id="665f1a2b3c4d5e6f7a8b9c0d",
            player_token="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            display_name="Danny",
        )
        assert player.game_id == "665f1a2b3c4d5e6f7a8b9c0d"
        assert player.player_token == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert player.display_name == "Danny"
        assert player.is_manager is False
        assert player.is_active is True
        assert player.credits_owed == 0
        assert player.checked_out is False
        assert player.final_chip_count is None
        assert player.profit_loss is None
        assert isinstance(player.joined_at, datetime)
        assert player.checked_out_at is None
        assert player.id is None

    def test_player_with_manager_flag(self):
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Host",
            is_manager=True,
        )
        assert player.is_manager is True

    def test_player_with_objectid(self):
        oid = ObjectId()
        player = Player(
            _id=oid,
            game_id="game1",
            player_token="token1",
            display_name="Alice",
        )
        assert player.id == str(oid)

    def test_player_checkout_fields(self):
        now = datetime.now(timezone.utc)
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Bob",
            checked_out=True,
            checked_out_at=now,
            final_chip_count=750,
            profit_loss=250,
        )
        assert player.checked_out is True
        assert player.checked_out_at == now
        assert player.final_chip_count == 750
        assert player.profit_loss == 250

    def test_player_credits_owed(self):
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Charlie",
            credits_owed=300,
        )
        assert player.credits_owed == 300

    def test_player_inactive(self):
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Dave",
            is_active=False,
        )
        assert player.is_active is False

    def test_player_to_mongo_dict_no_id(self):
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Eve",
        )
        doc = player.to_mongo_dict()
        assert "_id" not in doc
        assert doc["game_id"] == "game1"
        assert doc["display_name"] == "Eve"
        assert doc["is_manager"] is False

    def test_player_to_mongo_dict_with_id(self):
        oid = str(ObjectId())
        player = Player(
            _id=oid,
            game_id="game1",
            player_token="token1",
            display_name="Frank",
        )
        doc = player.to_mongo_dict()
        assert doc["_id"] == oid

    def test_player_serialization_json(self):
        now = datetime(2026, 1, 30, 20, 0, 0, tzinfo=timezone.utc)
        player = Player(
            _id=str(ObjectId()),
            game_id="game1",
            player_token="token1",
            display_name="Grace",
            joined_at=now,
        )
        data = player.model_dump(mode="json")
        assert isinstance(data["joined_at"], str)
        assert "2026-01-30" in data["joined_at"]
        assert data["checked_out_at"] is None

    def test_player_negative_profit_loss(self):
        player = Player(
            game_id="game1",
            player_token="token1",
            display_name="Henry",
            profit_loss=-200,
        )
        assert player.profit_loss == -200


class TestPlayerResponse:
    """Tests for the PlayerResponse API model."""

    def test_player_response_from_dict(self):
        data = {
            "_id": str(ObjectId()),
            "game_id": "game1",
            "player_token": "token1",
            "display_name": "Alice",
            "is_manager": False,
            "is_active": True,
            "credits_owed": 0,
            "checked_out": False,
            "joined_at": "2026-01-30T20:00:00+00:00",
        }
        resp = PlayerResponse(**data)
        assert resp.display_name == "Alice"
        assert resp.final_chip_count is None
        assert resp.profit_loss is None
