# Checkout System Redesign

## Problem

The existing checkout/settlement system had incorrect P/L calculations, inconsistent bank math between single and batch checkout, broken credit handling, and illogical settlement suggestions. It was removed entirely.

## Design: Per-Player Rolling State Machine

### Game-Level States

```
OPEN ──(Start Settling)──> SETTLING ──(all players DONE)──> CLOSED
```

During OPEN, individual players can also request mid-game checkout (same per-player flow).

### Per-Player Checkout States

```
PENDING → SUBMITTED → VALIDATED → CREDIT_DEDUCTED → AWAITING_DISTRIBUTION → DISTRIBUTED → DONE
```

- **PENDING**: Waiting for player (or manager) to input chip count + cash/credit preference
- **SUBMITTED**: Player submitted, waiting for manager validation
- **VALIDATED**: Manager approved the chip count
- **CREDIT_DEDUCTED**: System deducted credit from chips (automatic after validation)
- **AWAITING_DISTRIBUTION**: Waiting for credit pool to have enough to fulfill preference
- **DISTRIBUTED**: Cash/credit allocated
- **DONE**: Settled, actions confirmed

**Shortcuts:**
- Cash-only players requesting cash: VALIDATED → DONE (immediate payout)
- Players with no credit preference: skip AWAITING_DISTRIBUTION

### Step 1: SETTLING_CHIP_COUNT

**Trigger:** Manager clicks "Start Settling"
- All pending chip requests are auto-declined
- No new chip requests allowed
- Player buy-in data is frozen (snapshot of cash/credit totals per player)

**Player side:**
- Sees frozen buy-in summary (cash: X, credit: Y, total: Z)
- Enters: final chip count + preferred cash/credit split
- Once manager inputs on their behalf, player's input is locked

**Manager side:**
- Sees submissions as they come in (real-time, no waiting)
- Can validate or reject each submission individually as it arrives
- Rejection sends notification to player to re-enter
- Can input on behalf of any player (locks that player from submitting)

### Step 2: CREDIT_DEDUCTED

Happens automatically after manager validates a player's chip count.

**Formulas:**
- `credit_repaid = min(final_chips, total_credit)`
- `credit_owed = max(0, total_credit - final_chips)`
- `chips_after_credit = max(0, final_chips - total_credit)`
- `profit_loss = final_chips - total_buy_in`

**Player sees frozen before/after:**
- Before: "You returned 200 chips (buy-in: 100 cash + 100 credit)"
- After: "Credit deducted: 100. Remaining: 100 chips. P/L: 0"

Cash-only players skip this step entirely.

### Step 3: Distribution

The distribution algorithm runs whenever the pool state changes.

**Two pools:**
- **Cash pool**: Total cash collected from all buy-ins, decremented as players are paid cash
- **Credit pool**: Accumulates as players with `credit_owed > 0` reach DONE status

A player's unpaid credit only enters the pool AFTER their entire checkout is complete (DONE status).

**Algorithm priority:**
1. Cash-only players requesting cash → pay immediately, mark DONE
2. Players requesting all cash (even if they had credit) → pay from cash pool after credit deduction
3. Players requesting credit in payout → wait until enough credit in pool, assign using minimize-splits logic (fewest people taking one person's credit)
4. Conflicts or impossible preferences → fall back to minimize-splits, ignore preferences

**Manager view:**
- Current pool state (cash available: X, credit available: Y)
- Auto-generated distribution suggestion in editable textbox
- Suggestion updates live as pool changes
- Manager can override any allocation
- Validation: all allocations must sum to total remaining

**Player view:**
- AWAITING_DISTRIBUTION: "Waiting for credit to become available"
- Once distributed: see their actions

### Step 4: ACTION_LIST

After distribution is confirmed per player.

**Manager sees all actions:**
- "Give Alice 150 cash"
- "Bob owes 100 credit to Charlie and 50 credit to Dave"

**Each player sees only their actions:**
- Alice: "Receive 150 cash"
- Charlie: "Receive 100 credit from Bob"
- Bob: "Pay 100 to Charlie, pay 50 to Dave"

Game moves to CLOSED when all players are DONE and manager confirms.

### Mid-Game Checkout (during OPEN)

Any player can request checkout during an open game:
- Same per-player flow: submit chip count → manager validates → credit deducted → distribution → done
- Cash-only players requesting cash → paid immediately
- Credit players → proceed through full flow

### Core Math

Given: player has C cash buy-in, R credit buy-in, returns F final chips.

| Formula | Value |
|---------|-------|
| total_buy_in | C + R |
| profit_loss | F - (C + R) |
| credit_repaid | min(F, R) |
| credit_owed | max(0, R - F) |
| chips_after_credit | max(0, F - R) |
| cash_payout | determined in distribution (player preference + algorithm) |

### Examples

**Player: 100 cash + 100 credit = 200 buy-in**

| Returns | P/L | Credit Owed | Chips After Credit | Notes |
|---------|-----|-------------|-------------------|-------|
| 0 | -200 | 100 | 0 | Can't repay any credit |
| 50 | -150 | 50 | 0 | Partial credit repayment |
| 100 | -100 | 0 | 0 | Credit fully covered, nothing left |
| 150 | -50 | 0 | 50 | Gets 50 in cash/credit per preference |
| 200 | 0 | 0 | 100 | Break even |
| 250 | +50 | 0 | 150 | Profit |

### Data Model Changes

**Game model additions:**
- `settlement_state`: enum (null when OPEN, tracks sub-state when SETTLING)
- `cash_pool`: int (available cash for distribution)
- `credit_pool`: int (available credit from completed debtors)
- `frozen_at`: datetime (when settling started, buy-ins frozen)

**Player model additions:**
- `checkout_status`: enum (PENDING, SUBMITTED, VALIDATED, CREDIT_DEDUCTED, AWAITING_DISTRIBUTION, DISTRIBUTED, DONE)
- `submitted_chip_count`: int (what the player entered)
- `validated_chip_count`: int (what the manager approved)
- `preferred_cash`: int (how much they want in cash)
- `preferred_credit`: int (how much they'll take in credit)
- `chips_after_credit`: int (computed after credit deduction)
- `credit_repaid`: int (how much credit was covered by chips)
- `distribution`: object (final allocation — cash amount, credit assignments)
- `actions`: list (final action items for this player)
- `input_locked`: bool (true when manager inputs on behalf)
- `frozen_buy_in`: object (snapshot of cash/credit totals at settling start)

### API Endpoints (new)

**Settlement flow:**
- `POST /api/games/{id}/settle` — start settling (OPEN → SETTLING)
- `POST /api/games/{id}/players/{token}/submit-chips` — player submits chip count + preference
- `POST /api/games/{id}/players/{token}/validate-chips` — manager validates submission
- `POST /api/games/{id}/players/{token}/reject-chips` — manager rejects submission
- `POST /api/games/{id}/players/{token}/manager-input` — manager inputs on behalf (locks player)
- `GET /api/games/{id}/settlement/pool` — get current cash/credit pool state
- `GET /api/games/{id}/settlement/distribution` — get algorithm suggestion
- `PUT /api/games/{id}/settlement/distribution` — manager overrides distribution
- `POST /api/games/{id}/players/{token}/confirm-distribution` — confirm distribution for player
- `GET /api/games/{id}/players/{token}/actions` — get action list for player
- `POST /api/games/{id}/close` — close game (all players DONE)

**Mid-game checkout:**
- `POST /api/games/{id}/players/{token}/checkout-request` — player requests checkout during OPEN
- Same subsequent endpoints as above for the individual player flow
