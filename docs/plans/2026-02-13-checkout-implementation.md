# Checkout System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a per-player rolling state machine checkout system replacing the removed broken checkout/settlement code.

**Architecture:** Each player progresses independently through checkout states (PENDING -> SUBMITTED -> VALIDATED -> CREDIT_DEDUCTED -> AWAITING_DISTRIBUTION -> DISTRIBUTED -> DONE). The game stays in SETTLING until all players reach DONE, then transitions to CLOSED. A distribution algorithm assigns cash/credit payouts respecting player preferences, with manager override capability.

**Tech Stack:** Python 3.10+ / FastAPI / Motor (MongoDB) / React 18 / TypeScript / TailwindCSS

**Design Doc:** `docs/plans/2026-02-13-checkout-redesign-design.md`

---

## Task 1: Add CheckoutStatus enum and update Player model

**Files:**
- Modify: `backend/app/models/common.py`
- Modify: `backend/app/models/player.py`
- Test: `backend/tests/test_models/test_player_checkout_fields.py`

**Step 1: Write the failing test**

Create `backend/tests/test_models/test_player_checkout_fields.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_models/test_player_checkout_fields.py -v`
Expected: FAIL - `CheckoutStatus` does not exist yet

**Step 3: Write minimal implementation**

In `backend/app/models/common.py`, add after the `NotificationType` class:

```python
class CheckoutStatus(StrEnum):
    """Per-player checkout state machine states."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VALIDATED = "VALIDATED"
    CREDIT_DEDUCTED = "CREDIT_DEDUCTED"
    AWAITING_DISTRIBUTION = "AWAITING_DISTRIBUTION"
    DISTRIBUTED = "DISTRIBUTED"
    DONE = "DONE"
```

In `backend/app/models/player.py`, add these fields to the `Player` class (after `checked_out_at`):

```python
    # -- Checkout state machine fields --
    checkout_status: Optional[str] = None
    submitted_chip_count: Optional[int] = None
    validated_chip_count: Optional[int] = None
    preferred_cash: Optional[int] = None
    preferred_credit: Optional[int] = None
    chips_after_credit: Optional[int] = None
    credit_repaid: Optional[int] = None
    distribution: Optional[dict] = None
    actions: Optional[list] = None
    input_locked: bool = False
    frozen_buy_in: Optional[dict] = None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_models/test_player_checkout_fields.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/app/models/common.py backend/app/models/player.py backend/tests/test_models/test_player_checkout_fields.py
git commit -m "feat: add CheckoutStatus enum and checkout fields to Player model"
```

---

## Task 2: Add settlement fields to Game model

**Files:**
- Modify: `backend/app/models/game.py`
- Test: `backend/tests/test_models/test_game_settlement_fields.py`

**Step 1: Write the failing test**

Create `backend/tests/test_models/test_game_settlement_fields.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_models/test_game_settlement_fields.py -v`
Expected: FAIL - fields don't exist

**Step 3: Write minimal implementation**

In `backend/app/models/game.py`, add to the `Game` class after `bank`:

```python
    # -- Settlement state fields --
    settlement_state: Optional[str] = None
    cash_pool: int = 0
    credit_pool: int = 0
    frozen_at: Optional[datetime] = None
```

Update the `serialize_datetime` field_serializer decorator to include `frozen_at`:

```python
    @field_serializer("created_at", "closed_at", "expires_at", "frozen_at")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_models/test_game_settlement_fields.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/models/game.py backend/tests/test_models/test_game_settlement_fields.py
git commit -m "feat: add settlement state fields to Game model"
```

---

## Task 3: Implement checkout math as pure functions

**Files:**
- Create: `backend/app/services/checkout_math.py`
- Test: `backend/tests/test_services/test_checkout_math.py`

These are the core formulas as pure functions (no DB, no async). Easy to test exhaustively.

**Step 1: Write the failing tests**

Create `backend/tests/test_services/test_checkout_math.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_services/test_checkout_math.py -v`
Expected: FAIL - module not found

**Step 3: Write minimal implementation**

Create `backend/app/services/checkout_math.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/b/Documents/GitHub/ChipMate/backend && python -m pytest tests/test_services/test_checkout_math.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/checkout_math.py backend/tests/test_services/test_checkout_math.py
git commit -m "feat: implement checkout math pure functions with TDD"
```

---

## Task 4: Implement SettlementService - start settling + freeze buy-ins

**Files:**
- Create: `backend/app/services/settlement_service.py`
- Test: `backend/tests/test_services/test_settlement_service.py`

**Step 1: Write the failing test**

Create `backend/tests/test_services/test_settlement_service.py`. Key tests:
- `test_start_settling_transitions_game` - game goes to SETTLING, frozen_at set, cash_pool computed
- `test_start_settling_freezes_player_buy_ins` - each player gets frozen_buy_in snapshot + checkout_status=PENDING
- `test_start_settling_declines_pending_requests` - pending chip requests auto-declined
- `test_start_settling_fails_if_not_open` - 400 if game is not OPEN

Use the same fixture pattern as `test_request_service.py`: `mock_db`, DAL fixtures, service fixtures, `open_game` fixture that creates a game with players and approved chip requests.

**Step 3: Implement**

Create `backend/app/services/settlement_service.py` with `SettlementService` class and `start_settling` method. Follow existing service patterns (constructor takes DALs, `_get_game_or_404` helper).

Key logic:
- Validate game is OPEN
- Decline all pending requests via `chip_request_dal.decline_all_pending`
- For each active player: compute buy-in breakdown, save as `frozen_buy_in`, set `checkout_status=PENDING`
- Sum all cash buy-ins into `cash_pool` on game
- Set `frozen_at`, update game status to SETTLING
- Send GAME_SETTLING notifications

**Step 5: Commit**

```bash
git commit -m "feat: implement start_settling with buy-in freeze"
```

---

## Task 5: Implement player chip submission + manager validation

**Files:**
- Modify: `backend/app/services/settlement_service.py`
- Test: `backend/tests/test_services/test_settlement_submit_validate.py`

**Step 1: Write failing tests**

Key tests:
- `test_player_submits_chips` - status goes to SUBMITTED, fields saved
- `test_submit_fails_if_locked` - 400 if manager locked input
- `test_manager_validates_submission` - credit deducted, correct math
- `test_manager_rejects_submission` - reset to PENDING
- `test_manager_input_locks_player` - input_locked=True, auto-validates
- `test_cash_only_player_validated_goes_to_done` - fast path: VALIDATED -> DONE, cash_pool decremented

Use settling_game fixture (game in SETTLING state with players).

**Step 3: Implement**

Add methods to `SettlementService`:
- `submit_chips(game_id, player_token, final_chip_count, preferred_cash, preferred_credit)` - validates state, saves submission
- `validate_chips(game_id, player_token)` - runs `compute_credit_deduction`, determines next state, fast-paths cash-only players to DONE
- `reject_chips(game_id, player_token)` - resets to PENDING, notifies player
- `manager_input(game_id, player_token, ...)` - locks player, submits, auto-validates

**Step 5: Commit**

```bash
git commit -m "feat: implement chip submission, validation, rejection, and manager input"
```

---

## Task 6: Implement distribution and close game

**Files:**
- Modify: `backend/app/services/settlement_service.py`
- Test: `backend/tests/test_services/test_settlement_distribution.py`

**Step 1: Write failing tests**

Key tests:
- `test_get_distribution_returns_suggestion` - calls algorithm, returns per-player allocation
- `test_confirm_distribution_marks_done` - player goes DISTRIBUTED -> DONE, pools updated
- `test_credit_enters_pool_when_debtor_done` - debtor reaching DONE adds their credit_owed to credit_pool
- `test_close_game_requires_all_done` - 400 if any player not DONE
- `test_close_game_succeeds` - game -> CLOSED

**Step 3: Implement**

Add methods:
- `get_distribution_suggestion(game_id)` - gathers player data, calls `compute_distribution_suggestion`
- `override_distribution(game_id, overrides)` - manager edits, validates totals
- `confirm_distribution(game_id, player_token)` - marks DISTRIBUTED -> DONE, updates pools
- `get_player_actions(game_id, player_token)` - returns action list for a player
- `close_game(game_id)` - validates all DONE, transitions to CLOSED, notifies

**Step 5: Commit**

```bash
git commit -m "feat: implement distribution algorithm and game close"
```

---

## Task 7: Implement settlement API routes

**Files:**
- Create: `backend/app/routes/settlement.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_settlement/test_settlement_routes.py`

**Step 1: Write failing route tests**

Test each endpoint using the `client` fixture from conftest.py.

**Step 3: Implement routes**

Follow `backend/app/routes/chip_requests.py` pattern:
- `_get_service()` helper wires DALs
- Pydantic request body models
- Auth dependencies: `get_current_manager` for manager endpoints, `get_current_player` for player endpoints

Endpoints:
- `POST /api/games/{game_id}/settle`
- `POST /api/games/{game_id}/players/{player_token}/submit-chips`
- `POST /api/games/{game_id}/players/{player_token}/validate-chips`
- `POST /api/games/{game_id}/players/{player_token}/reject-chips`
- `POST /api/games/{game_id}/players/{player_token}/manager-input`
- `GET /api/games/{game_id}/settlement/pool`
- `GET /api/games/{game_id}/settlement/distribution`
- `PUT /api/games/{game_id}/settlement/distribution`
- `POST /api/games/{game_id}/players/{player_token}/confirm-distribution`
- `GET /api/games/{game_id}/players/{player_token}/actions`
- `POST /api/games/{game_id}/close`

Register in `backend/app/main.py`:
```python
from app.routes.settlement import router as settlement_router
app.include_router(settlement_router, prefix="/api")
```

**Step 5: Commit**

```bash
git commit -m "feat: add settlement API routes"
```

---

## Task 8: Add frontend TypeScript types and API client

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/api/settlement.ts`

Add types:
- `CheckoutStatus` enum matching backend
- Request/response interfaces for all settlement endpoints
- `PlayerAction` interface for action list items

Create `settlement.ts` API functions calling each endpoint.

```bash
git commit -m "feat: add frontend settlement types and API client"
```

---

## Task 9: Implement manager settlement UI

**Files:**
- Create: `frontend/src/components/game/SettlementDashboard.tsx`
- Modify: `frontend/src/components/game/ManagerDashboard.tsx`

Build manager settlement view:
- Player list with checkout_status badges
- Validate/reject buttons per submitted player
- Manager input form (locks player)
- Pool status (cash available, credit available)
- Distribution editor: editable textbox with algorithm suggestion, total validation
- Action list after all distributed
- Close game button

Wire into ManagerDashboard when `gameStatus === GameStatus.SETTLING`.

```bash
git commit -m "feat: implement manager settlement dashboard"
```

---

## Task 10: Implement player checkout UI

**Files:**
- Create: `frontend/src/components/game/PlayerCheckoutView.tsx`
- Modify: player-facing game view components

Build player checkout view showing different UI per checkout_status:
- PENDING: chip count input + cash/credit preference split + submit
- SUBMITTED: "Waiting for manager validation"
- CREDIT_DEDUCTED: frozen before/after credit view
- AWAITING_DISTRIBUTION: "Waiting for credit to become available"
- DISTRIBUTED/DONE: action items ("Receive X cash", "Pay Y to Z")
- Locked indicator when manager input on behalf

```bash
git commit -m "feat: implement player checkout view"
```

---

## Task 11: Implement mid-game checkout

**Files:**
- Modify: `backend/app/services/settlement_service.py`
- Modify: `backend/app/routes/settlement.py`
- Modify: `frontend/src/components/game/PlayerListCard.tsx`
- Test: `backend/tests/test_services/test_midgame_checkout.py`

Add `request_midgame_checkout` method: during OPEN, a single player can initiate checkout. Same per-player flow. Cash-only + cash preference -> immediate DONE.

Frontend: add "Checkout" button per player in PlayerListCard during OPEN.

```bash
git commit -m "feat: implement mid-game checkout for individual players"
```

---

## Task 12: End-to-end integration test

**Files:**
- Create: `backend/tests/test_services/test_checkout_e2e.py`

Full scenario:
1. Create game, add 4 players with mix of cash/credit
2. Start settling
3. Players submit chip counts with various preferences
4. Manager validates all
5. Distribution algorithm runs
6. Verify pool math correct throughout
7. All players reach DONE
8. Close game
9. Verify: all P/L correct, all actions correct, game CLOSED, pools zeroed

```bash
git commit -m "test: add end-to-end checkout flow integration test"
```
