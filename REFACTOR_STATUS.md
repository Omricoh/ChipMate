# Refactor Status - Bank System Simplification

## ✅ COMPLETED

### 1. Bank Model Updated
- `Bank.outstanding_debt` → `Bank.total_credits_issued` / `total_credits_repaid`
- `record_cashout()` now takes `credits_repaid` instead of `debt_settled`
- Added `validate_cashout()` method
- Simplified to track credits per-player

### 2. Player Model Updated
- Added `Player.credits_owed` field to track credit owed to bank

### 3. BankDAL Updated
- `record_credit_buyin()` - issues credits without separate debt table
- `record_cashout()` - tracks credit repayment

### 4. TransactionService Partially Updated
- Removed `debt_dal` import and initialization
- `approve_transaction()` updates `Player.credits_owed` instead of creating debt records
- `process_cashout_with_debt_settlement()` - SIMPLIFIED (no automatic debt transfers)
- `execute_cashout_debt_operations()` - SIMPLIFIED (updates Player.credits_owed)
- `get_player_transaction_summary()` - returns `credits_owed` instead of debt

## ⏳ REMAINING WORK

### 1. TransactionService Cleanup
- [ ] Remove or replace `get_game_debts_formatted()` (line 357)
- [ ] Update `process_host_cashout()` (line 383) to use new simplified logic
- [ ] Check for any other debt_dal references

### 2. GameService Updates
- [ ] Remove debt_dal import
- [ ] Update `get_game_status()` to show player credits instead of debts
- [ ] Remove debt-related status calculations

### 3. AdminService Updates
- [ ] Remove debt_dal import and initialization
- [ ] Update `destroy_game_completely()` to not delete debts collection

### 4. API Updates (web_api.py)
- [ ] Remove `/api/games/<game_id>/debts` endpoint
- [ ] Update game status endpoint to return credits instead of debts
- [ ] Consider adding `/api/games/<game_id>/credits` endpoint to show player credits

### 5. Test Updates
- [ ] Update `test_cashout_scenarios.py` to work without debt_dal
- [ ] Tests currently expect debt tracking - need to update to check Player.credits_owed
- [ ] Remove debt assertions, add credit assertions

### 6. Remove debt_dal Files (LAST STEP)
- [ ] Delete `src/dal/debt_dal.py`
- [ ] Delete `src/models/debt.py` (if exists)

## 🐛 ADMIN FIX

### Issue
Admin enters game and sees: "Player OMRI_C not found in game. Please rejoin the game."

### Root Cause
Frontend expects logged-in user to be in players list. Admin is not a player.

### Solution (Frontend Fix)
In `web-ui/src/app/components/game/game.component.ts` around line 764:

```typescript
// BEFORE:
} else {
  const attemptedName = this.currentUser.username || this.currentUser.name;
  console.warn('Current player not found in players list...');
  this.showError(`Player "${attemptedName}" not found in game. Please rejoin the game.`);
}

// AFTER:
} else {
  // Check if user is admin viewing the game
  if (this.isAdminViewing()) {
    // Set up admin as viewer with host privileges
    this.currentPlayer = {
      name: 'Admin',
      user_id: this.currentUser.id,
      is_host: true,
      active: true,
      // ... other required fields
    };
    this.isHost = true;
  } else {
    const attemptedName = this.currentUser.username || this.currentUser.name;
    console.warn('Current player not found in players list...');
    this.showError(`Player "${attemptedName}" not found in game. Please rejoin the game.`);
  }
}
```

Add method to detect admin viewing:
```typescript
isAdminViewing(): boolean {
  // Check if route has admin parameter or user has admin role
  return this.route.snapshot.queryParams['admin'] === 'true' ||
         this.currentUser?.role === 'admin';
}
```

## 📋 NEXT STEPS

1. Complete TransactionService cleanup
2. Update GameService and AdminService
3. Update API endpoints
4. Fix tests
5. Remove debt_dal files
6. Apply admin frontend fix
7. Test complete flow
