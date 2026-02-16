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


    def test_high_credit_low_chips_200_cash_400_credit_300_chips(self):
        """Player with 200 cash + 400 credit returning 300 chips gets 0 after credit."""
        result = compute_credit_deduction(final_chips=300, total_cash_in=200, total_credit_in=400)
        assert result["total_buy_in"] == 600
        assert result["profit_loss"] == -300
        assert result["credit_repaid"] == 300  # all chips go to credit
        assert result["credit_owed"] == 100  # still owes 100
        assert result["chips_after_credit"] == 0  # nothing left for cash

    def test_high_credit_low_chips_200_cash_400_credit_500_chips(self):
        """Player with 200 cash + 400 credit returning 500 chips gets 100 after credit."""
        result = compute_credit_deduction(final_chips=500, total_cash_in=200, total_credit_in=400)
        assert result["total_buy_in"] == 600
        assert result["profit_loss"] == -100
        assert result["credit_repaid"] == 400  # all credit repaid
        assert result["credit_owed"] == 0
        assert result["chips_after_credit"] == 100  # 500 - 400 = 100 for cash


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

    def test_high_credit_player_gets_zero_cash(self):
        """Player with more credit than chips should get 0 cash in distribution.

        Winner has 800 chips but only 700 cash available. Gets 700 cash + 100 credit from debtor.
        """
        players = [
            # This player had 200 cash + 400 credit, returned 300 chips
            # chips_after_credit = 0, credit_owed = 100
            {"player_token": "debtor", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 100},
            # Winner: 500 cash only, returned 800, chips_after_credit = 800
            {"player_token": "winner", "chips_after_credit": 800, "preferred_cash": 700, "preferred_credit": 100, "credit_owed": 0},
        ]
        result = compute_distribution_suggestion(players, cash_pool=700, credit_pool=0)
        assert result["debtor"]["cash"] == 0
        assert result["debtor"]["credit_from"] == []
        # Winner gets 700 cash + 100 credit (cash pool capped at 700)
        assert result["winner"]["cash"] == 700
        assert result["winner"]["credit_from"] == [{"from": "debtor", "amount": 100}]

    def test_no_chips_after_credit(self):
        players = [
            {"player_token": "a", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 50},
        ]
        result = compute_distribution_suggestion(players, cash_pool=100, credit_pool=0)
        assert result["a"]["cash"] == 0
        assert result["a"]["credit_from"] == []

    def test_cash_pool_capped(self):
        """Total cash distributed must not exceed cash_pool.

        Scenario: Manager (300 after credit), p1 (0, owes 100), p2 (200).
        Cash pool = 400, total needed = 500. Must assign 100 as credit from p1.
        """
        players = [
            {"player_token": "manager", "chips_after_credit": 300, "preferred_cash": 300, "preferred_credit": 0, "credit_owed": 0},
            {"player_token": "p1", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 100},
            {"player_token": "p2", "chips_after_credit": 200, "preferred_cash": 200, "preferred_credit": 0, "credit_owed": 0},
        ]
        result = compute_distribution_suggestion(players, cash_pool=400, credit_pool=0)
        total_cash = sum(r["cash"] for r in result.values())
        assert total_cash <= 400, f"Total cash {total_cash} exceeds pool of 400"
        # Someone must receive 100 credit from p1
        total_credit = sum(
            sum(c["amount"] for c in r["credit_from"])
            for r in result.values()
        )
        assert total_credit == 100
        # Each player still gets their full chips_after_credit
        for token, chips in [("manager", 300), ("p1", 0), ("p2", 200)]:
            player_total = result[token]["cash"] + sum(
                c["amount"] for c in result[token]["credit_from"]
            )
            assert player_total == chips, f"{token}: expected {chips}, got {player_total}"

    def test_cash_pool_capped_prefers_credit_requesters(self):
        """When cash is short, players who preferred credit absorb it first."""
        players = [
            {"player_token": "a", "chips_after_credit": 200, "preferred_cash": 200, "preferred_credit": 0, "credit_owed": 0},
            {"player_token": "b", "chips_after_credit": 200, "preferred_cash": 100, "preferred_credit": 100, "credit_owed": 0},
            {"player_token": "debtor", "chips_after_credit": 0, "preferred_cash": 0, "preferred_credit": 0, "credit_owed": 150},
        ]
        result = compute_distribution_suggestion(players, cash_pool=300, credit_pool=0)
        total_cash = sum(r["cash"] for r in result.values())
        assert total_cash <= 300
        # b preferred credit, so b should get credit assignment before a
        assert len(result["b"]["credit_from"]) > 0
