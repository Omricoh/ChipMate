"""Tests for checkout math pure functions.

Covers all P/L, credit deduction, and pool calculations from the design doc.
"""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

from app.services.checkout_math import compute_credit_deduction, compute_distribution_suggestion


class TestComputeCreditDeduction:
    """Tests based on design doc examples: 100 cash + 100 credit = 200 buy-in."""

    def test_returns_0(self):
        result = compute_credit_deduction(final_chips=0, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == -200
        assert result["credit_owed"] == 100
        assert result["credit_repaid"] == 0
        assert result["chips_after_credit"] == 0
        assert result["total_buy_in"] == 200

    def test_returns_50(self):
        result = compute_credit_deduction(final_chips=50, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == -150
        assert result["credit_owed"] == 50
        assert result["credit_repaid"] == 50
        assert result["chips_after_credit"] == 0

    def test_returns_100(self):
        result = compute_credit_deduction(final_chips=100, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == -100
        assert result["credit_owed"] == 0
        assert result["credit_repaid"] == 100
        assert result["chips_after_credit"] == 0

    def test_returns_150(self):
        result = compute_credit_deduction(final_chips=150, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == -50
        assert result["credit_owed"] == 0
        assert result["credit_repaid"] == 100
        assert result["chips_after_credit"] == 50

    def test_returns_200_break_even(self):
        result = compute_credit_deduction(final_chips=200, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == 0
        assert result["credit_owed"] == 0
        assert result["credit_repaid"] == 100
        assert result["chips_after_credit"] == 100

    def test_returns_250_profit(self):
        result = compute_credit_deduction(final_chips=250, total_cash_in=100, total_credit_in=100)
        assert result["profit_loss"] == 50
        assert result["credit_owed"] == 0
        assert result["credit_repaid"] == 100
        assert result["chips_after_credit"] == 150

    def test_cash_only_player(self):
        result = compute_credit_deduction(final_chips=150, total_cash_in=100, total_credit_in=0)
        assert result["profit_loss"] == 50
        assert result["credit_owed"] == 0
        assert result["credit_repaid"] == 0
        assert result["chips_after_credit"] == 150

    def test_credit_only_player(self):
        result = compute_credit_deduction(final_chips=50, total_cash_in=0, total_credit_in=200)
        assert result["profit_loss"] == -150
        assert result["credit_owed"] == 150
        assert result["credit_repaid"] == 50
        assert result["chips_after_credit"] == 0


class TestComputeDistributionSuggestion:
    """Tests for the distribution algorithm."""

    def test_all_cash_players(self):
        players = [
            {"player_token": "a", "chips_after_credit": 150, "preferred_cash": 150, "preferred_credit": 0, "credit_owed": 0},
            {"player_token": "b", "chips_after_credit": 50, "preferred_cash": 50, "preferred_credit": 0, "credit_owed": 0},
        ]
        result = compute_distribution_suggestion(players, cash_pool=200, credit_pool=0)
        assert result["a"]["cash"] == 150
        assert result["b"]["cash"] == 50

    def test_credit_assignment_minimizes_splits(self):
        """One debtor's credit should go to fewest recipients possible."""
        players = [
            {"player_token": "winner1", "chips_after_credit": 200, "preferred_cash": 100, "preferred_credit": 100, "credit_owed": 0},
            {"player_token": "winner2", "chips_after_credit": 50, "preferred_cash": 50, "preferred_credit": 0, "credit_owed": 0},
            {"player_token": "debtor", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 100},
        ]
        result = compute_distribution_suggestion(players, cash_pool=300, credit_pool=100)
        assert result["winner1"]["credit_from"] == [{"from": "debtor", "amount": 100}]
        assert result["winner1"]["cash"] == 100
        assert result["winner2"]["cash"] == 50

    def test_no_chips_after_credit(self):
        players = [
            {"player_token": "a", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 50},
        ]
        result = compute_distribution_suggestion(players, cash_pool=100, credit_pool=0)
        assert result["a"]["cash"] == 0
        assert result["a"]["credit_from"] == []
