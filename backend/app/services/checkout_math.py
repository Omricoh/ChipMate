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

    Respects the cash_pool limit. When total payout exceeds available cash,
    forces credit assignments from debtors. Players who preferred credit
    absorb credit first; remaining overage is spread to others.

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
    total_credit_available = credit_pool + sum(debtor_remaining.values())

    # Step 1: Assign credit to players who explicitly preferred it
    credit_requesters = [
        p for p in players
        if p["preferred_credit"] > 0 and p["chips_after_credit"] > 0
    ]
    credit_requesters.sort(key=lambda p: p["preferred_credit"], reverse=True)

    remaining_credit = total_credit_available

    for requester in credit_requesters:
        token = requester["player_token"]
        wanted = min(requester["preferred_credit"], remaining_credit)
        assigned = _assign_credit_from_debtors(
            result, token, wanted, debtor_remaining
        )
        remaining_credit -= assigned
        result[token]["cash"] = requester["chips_after_credit"] - assigned

    # Step 2: Assign remaining players their chips as cash
    credit_requester_tokens = {r["player_token"] for r in credit_requesters}
    for p in players:
        token = p["player_token"]
        if token in credit_requester_tokens:
            continue
        result[token]["cash"] = p["chips_after_credit"]

    # Step 3: Cap total cash at cash_pool — force credit from debtors for overage
    total_cash = sum(r["cash"] for r in result.values())
    overage = total_cash - cash_pool

    if overage > 0 and remaining_credit > 0:
        # Build list of players who can receive credit, sorted:
        # - players who preferred credit first (most willing)
        # - then by cash amount descending (largest cash recipients absorb first)
        receivers = [
            p for p in players
            if result[p["player_token"]]["cash"] > 0
        ]
        receivers.sort(
            key=lambda p: (-p["preferred_credit"], -result[p["player_token"]]["cash"])
        )

        for receiver in receivers:
            if overage <= 0:
                break
            token = receiver["player_token"]
            current_cash = result[token]["cash"]
            convert = min(overage, current_cash, remaining_credit)
            if convert <= 0:
                continue
            assigned = _assign_credit_from_debtors(
                result, token, convert, debtor_remaining
            )
            result[token]["cash"] -= assigned
            remaining_credit -= assigned
            overage -= assigned

    return result


def _assign_credit_from_debtors(
    result: dict[str, dict[str, Any]],
    recipient_token: str,
    amount: int,
    debtor_remaining: dict[str, int],
) -> int:
    """Assign credit from debtors to a recipient. Returns total assigned."""
    assigned = 0
    sorted_debtors = sorted(
        debtor_remaining.items(), key=lambda x: x[1], reverse=True
    )
    for debtor_token, debtor_amt in sorted_debtors:
        if assigned >= amount or debtor_amt <= 0:
            continue
        transfer = min(amount - assigned, debtor_amt)
        if transfer <= 0:
            continue
        result[recipient_token]["credit_from"].append(
            {"from": debtor_token, "amount": transfer}
        )
        debtor_remaining[debtor_token] -= transfer
        assigned += transfer
    return assigned
