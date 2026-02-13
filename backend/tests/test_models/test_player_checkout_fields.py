"""Tests for new checkout fields on the Player model."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

from app.models.common import CheckoutStatus
from app.models.player import Player


def test_checkout_status_enum_values():
    assert CheckoutStatus.PENDING == "PENDING"
    assert CheckoutStatus.SUBMITTED == "SUBMITTED"
    assert CheckoutStatus.VALIDATED == "VALIDATED"
    assert CheckoutStatus.CREDIT_DEDUCTED == "CREDIT_DEDUCTED"
    assert CheckoutStatus.AWAITING_DISTRIBUTION == "AWAITING_DISTRIBUTION"
    assert CheckoutStatus.DISTRIBUTED == "DISTRIBUTED"
    assert CheckoutStatus.DONE == "DONE"


def test_player_has_checkout_fields():
    p = Player(game_id="g1", player_token="t1", display_name="Alice")
    assert p.checkout_status is None
    assert p.submitted_chip_count is None
    assert p.validated_chip_count is None
    assert p.preferred_cash is None
    assert p.preferred_credit is None
    assert p.chips_after_credit is None
    assert p.credit_repaid is None
    assert p.distribution is None
    assert p.actions is None
    assert p.input_locked is False
    assert p.frozen_buy_in is None


def test_player_checkout_fields_set():
    p = Player(
        game_id="g1",
        player_token="t1",
        display_name="Bob",
        checkout_status=CheckoutStatus.SUBMITTED,
        submitted_chip_count=200,
        preferred_cash=150,
        preferred_credit=50,
        input_locked=False,
        frozen_buy_in={"total_cash_in": 100, "total_credit_in": 100, "total_buy_in": 200},
    )
    assert p.checkout_status == CheckoutStatus.SUBMITTED
    assert p.submitted_chip_count == 200
    assert p.preferred_cash == 150
    assert p.preferred_credit == 50
    assert p.frozen_buy_in["total_buy_in"] == 200


def test_player_checkout_fields_in_mongo_dict():
    p = Player(
        game_id="g1",
        player_token="t1",
        display_name="Charlie",
        checkout_status=CheckoutStatus.VALIDATED,
        validated_chip_count=300,
    )
    doc = p.to_mongo_dict()
    assert doc["checkout_status"] == "VALIDATED"
    assert doc["validated_chip_count"] == 300
