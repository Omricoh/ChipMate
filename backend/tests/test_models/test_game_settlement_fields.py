"""Tests for new settlement fields on the Game model."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

from app.models.game import Game


def test_game_has_settlement_fields():
    g = Game(code="ABC123", manager_player_token="tok1")
    assert g.settlement_state is None
    assert g.cash_pool == 0
    assert g.credit_pool == 0
    assert g.frozen_at is None


def test_game_settlement_fields_in_mongo_dict():
    g = Game(
        code="ABC123",
        manager_player_token="tok1",
        settlement_state="SETTLING_CHIP_COUNT",
        cash_pool=500,
        credit_pool=100,
    )
    doc = g.to_mongo_dict()
    assert doc["settlement_state"] == "SETTLING_CHIP_COUNT"
    assert doc["cash_pool"] == 500
    assert doc["credit_pool"] == 100
