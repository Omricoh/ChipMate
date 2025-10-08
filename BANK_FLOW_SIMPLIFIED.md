# Simplified Bank Flow

## Changes from Previous System

### REMOVED:
- `debt_dal` - No more debt tracking with statuses, transfers, etc.
- Complex debt settlement logic
- Automatic debt transfers between players
- "Debt" terminology throughout

### ADDED:
- `Player.credits_owed` - Simple integer tracking what player owes bank
- Simplified cashout where player CHOOSES: cash OR credits from inactive players
- Bank-centric terminology

## New Flow

### BUY-IN FLOW

**Cash Buy-in:**
1. Player brings cash
2. Creates transaction (buyin_cash)
3. HOST APPROVES
4. Bank receives cash (`bank.cash_balance += amount`)
5. Bank issues chips (`bank.chips_in_play += amount`)
6. Player gets chips

**Credit Buy-in:**
1. Player wants credit
2. Creates transaction (buyin_register)
3. HOST APPROVES
4. Bank issues chips (`bank.chips_in_play += amount`)
5. Player owes credit (`player.credits_owed += amount`)
6. Bank tracks total (`bank.total_credits_issued += amount`)

### CASHOUT FLOW (SIMPLIFIED)

1. Player returns chips to bank
2. System calculates:
   - How much of their own credit to repay (from chips)
   - Remaining chips value
3. **Player CHOOSES** for remaining value:
   - Option A: Take CASH from bank (if available)
   - Option B: Take CREDIT from inactive player (become creditor)
4. HOST APPROVES the cashout request
5. Bank executes:
   - Receives chips back
   - Reduces player's credits_owed
   - Pays cash OR transfers inactive player's credit
6. Player cashed out

### Example Scenario

**Setup:**
- Player A: 100 cash + 100 credit buy-in (owes 100 to bank)
- Player B: 100 cash + 100 credit buy-in (owes 100 to bank)
- Bank has: 200 cash, 200 credits issued

**Player B cashes out for 0:**
- Returns 0 chips
- Still owes 100 credit to bank
- Gets nothing
- Bank: 200 cash, 200 outstanding credits

**Player A cashes out for 400:**
- Returns 400 chips
- First: Repays own 100 credit (400 - 100 = 300 remaining)
- Then: Chooses to take 200 cash + take over B's 100 credit
- Bank pays: 200 cash (bank now has 0 cash)
- A becomes creditor: B owes 100 to A (not to bank anymore)
- Bank: 0 cash, 100 outstanding credits (only B's credit)

## API Changes Needed

### Cashout Request Format:
```json
{
  "chips": 400,
  "credits_repayment": 100,
  "cash_requested": 200,
  "credits_takeover": [
    {"from_player_id": 123, "amount": 100}
  ]
}
```

### Host Approval:
- Host sees the breakdown
- Approves or rejects
- If approved, bank executes exactly as requested
