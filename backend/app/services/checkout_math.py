"""Pure functions for checkout calculations.

No database access, no async. All inputs are plain dicts/ints.
"""

from typing import Any


def compute_credit_deduction(
    final_chips: int,
    total_cash_in: int,
    total_credit_in: int,
) -> dict[str, int]:
    """Compute credit deduction results for a single player.

    Args:
        final_chips: Number of chips the player is returning.
        total_cash_in: Total cash buy-in amount.
        total_credit_in: Total credit buy-in amount.

    Returns:
        Dict with total_buy_in, profit_loss, credit_repaid,
        credit_owed, and chips_after_credit.
    """
    total_buy_in = total_cash_in + total_credit_in
    profit_loss = final_chips - total_buy_in
    credit_repaid = min(final_chips, total_credit_in)
    credit_owed = max(0, total_credit_in - final_chips)
    chips_after_credit = max(0, final_chips - total_credit_in)

    return {
        "total_buy_in": total_buy_in,
        "profit_loss": profit_loss,
        "credit_repaid": credit_repaid,
        "credit_owed": credit_owed,
        "chips_after_credit": chips_after_credit,
    }


def compute_distribution_suggestion(
    players: list[dict[str, Any]],
    cash_pool: int,
    credit_pool: int,
) -> dict[str, dict[str, Any]]:
    """Compute optimal distribution of cash and credit to players.

    Minimizes the number of credit splits (fewest people taking one
    person's credit). Respects player preferences where possible,
    falls back to cash when credit is unavailable.

    Args:
        players: List of dicts with player_token, chips_after_credit,
            preferred_cash, preferred_credit, credit_owed.
        cash_pool: Available cash for distribution.
        credit_pool: Available credit from completed debtors.

    Returns:
        Dict keyed by player_token with cash amount and credit_from list.
    """
    result: dict[str, dict[str, Any]] = {}

    for p in players:
        result[p["player_token"]] = {"cash": 0, "credit_from": []}

    debtors = [p for p in players if p["credit_owed"] > 0]
    debtor_remaining = {d["player_token"]: d["credit_owed"] for d in debtors}

    credit_requesters = [
        p for p in players
        if p["preferred_credit"] > 0 and p["chips_after_credit"] > 0
    ]
    credit_requesters.sort(key=lambda p: p["preferred_credit"], reverse=True)

    remaining_credit_pool = credit_pool

    for requester in credit_requesters:
        token = requester["player_token"]
        wanted = requester["preferred_credit"]
        assigned = 0

        sorted_debtors = sorted(
            debtor_remaining.items(), key=lambda x: x[1], reverse=True
        )
        for debtor_token, debtor_amt in sorted_debtors:
            if assigned >= wanted or debtor_amt <= 0:
                continue
            transfer = min(wanted - assigned, debtor_amt, remaining_credit_pool)
            if transfer <= 0:
                continue
            result[token]["credit_from"].append(
                {"from": debtor_token, "amount": transfer}
            )
            debtor_remaining[debtor_token] -= transfer
            remaining_credit_pool -= transfer
            assigned += transfer

        cash_amount = requester["chips_after_credit"] - assigned
        result[token]["cash"] = max(0, cash_amount)

    for p in players:
        token = p["player_token"]
        if token in [r["player_token"] for r in credit_requesters]:
            continue
        result[token]["cash"] = p["chips_after_credit"]

    return result
