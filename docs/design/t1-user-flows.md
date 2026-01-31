# T1 -- User Flows & Screen Map

## ChipMate v2 Design Document

**Version:** 1.0
**Date:** 2026-01-30
**Status:** Draft

---

## Table of Contents

1. [User Flows](#1-user-flows)
2. [Screen Inventory](#2-screen-inventory)
3. [Screen Transition Diagram](#3-screen-transition-diagram)
4. [Edge Cases](#4-edge-cases)
5. [Navigation Design](#5-navigation-design)
6. [Mobile Considerations](#6-mobile-considerations)

---

## 1. User Flows

### 1.1 Game Creation (Manager)

**Precondition:** User is on the home screen, not currently in a game.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Home | Taps "New Game" | Navigates to Create Game screen |
| 2 | Create Game | Enters display name in text field | Name validated (1-20 chars, trimmed) |
| 3 | Create Game | Taps "Create Game" button | POST `/api/games` -- spinner on button |
| 4 | Game Lobby | -- | Game created. Screen shows: game code (large, copyable), QR code, share link, player list (manager listed as first player). Game status: OPEN |
| 5 | Game Lobby | Taps "Copy Link" or "Share" | Join URL copied to clipboard / native share sheet opened |
| 6 | Game Lobby | Taps QR code | QR code expands to full-screen overlay for easy scanning |

**Error paths:**
- Empty name: inline validation error "Display name is required" shown below the input field.
- Network failure: toast notification "Could not create game. Check your connection." with a "Retry" action.

---

### 1.2 Player Join

Players can join by three methods: scanning a QR code, opening a shared link, or entering a game code manually.

#### 1.2a Via Shared Link or QR Code

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | (External) | Player scans QR code or taps shared link | Browser opens `/join?code=XXXX`. Code is pre-filled |
| 2 | Join Game | Player enters display name | Name validated (1-20 chars, trimmed) |
| 3 | Join Game | Taps "Join Game" | POST `/api/games/join` -- spinner on button |
| 4 | Player Game View | -- | Player is added to the game. Player Game View loads with the player's bankroll card, activity feed, and request chips button |

#### 1.2b Via Manual Code Entry

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Home | Taps "Join Game" | Navigates to Join Game screen |
| 2 | Join Game | Enters 4-6 character game code (auto-uppercased) | Input accepts alphanumeric characters only |
| 3 | Join Game | Enters display name | Name validated (1-20 chars, trimmed) |
| 4 | Join Game | Taps "Join Game" | POST `/api/games/join` -- spinner on button |
| 5 | Player Game View | -- | Same as 1.2a step 4 |

**Error paths:**
- Invalid code: inline error "Game not found. Check the code and try again."
- Game is CLOSED: inline error "This game has ended."
- Game is SETTLING: inline error "This game is settling and no longer accepting players."
- Duplicate name in game: inline error "That name is already taken. Choose another."
- Empty name: inline validation "Display name is required."

---

### 1.3 Chip Request (Player Requests Cash or Credit Buy-in)

**Precondition:** Player is in an active (OPEN) game.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Player Game View | Taps "Request Chips" button (primary action, bottom of screen) | Bottom sheet slides up with chip request form |
| 2 | Chip Request Sheet | Selects type: "Cash" or "Credit" via segmented toggle | Selection is highlighted; default is "Cash" |
| 3 | Chip Request Sheet | Enters chip amount using numeric keypad | Input shows chip amount. Numeric keyboard triggered via `inputmode="numeric"` |
| 4 | Chip Request Sheet | Taps "Send Request" | POST `/api/transactions/buyin` -- button shows spinner. Sheet dismisses |
| 5 | Player Game View | -- | Toast: "Request sent to manager." Pending request appears in activity feed with "Pending" badge. Poll picks up approval/rejection |
| 6 | Player Game View | (Poll detects approval) | Toast: "Your [amount] chip [cash/credit] buy-in was approved." Bankroll card updates. Activity item shows "Approved" badge |
| 6a | Player Game View | (Poll detects rejection) | Toast: "Your [amount] chip request was declined." Activity item shows "Declined" badge |

**Error paths:**
- Zero or negative amount: inline validation "Enter an amount greater than 0."
- Non-numeric input: prevented by `inputmode="numeric"` and input filtering.
- Network failure: toast "Request failed. Try again." Sheet stays open for retry.

---

### 1.4 On-Behalf-Of Request (Player Requests for Another Player)

**Precondition:** Player is in an active (OPEN) game with at least one other player.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Player Game View | Taps "Request Chips" button | Bottom sheet slides up |
| 2 | Chip Request Sheet | Taps "For another player" toggle/link below the amount field | Player picker appears: scrollable list of other active players in the game |
| 3 | Chip Request Sheet | Selects target player from list | Selected player name shown as a chip/tag: "For: [PlayerName]" |
| 4 | Chip Request Sheet | Selects type (Cash / Credit), enters amount | Same as standard request |
| 5 | Chip Request Sheet | Taps "Send Request" | POST `/api/transactions/buyin` with target player's `user_id`. Sheet dismisses |
| 6 | Player Game View | -- | Toast: "Request sent for [PlayerName]." |
| 7 | (Target player's view) | (Poll cycle) | Notification badge or inline notice: "[RequesterName] requested [amount] chips on your behalf. Awaiting manager approval." |
| 8 | (Manager's view) | (Poll cycle) | Pending request appears with label: "[amount] [cash/credit] for [TargetPlayer] (requested by [RequesterName])" |

**Error paths:**
- No other players in game: "For another player" option is hidden.
- Target player has left: error toast "That player is no longer in the game."

---

### 1.5 Manager Approval (Approve / Decline / Edit Request)

**Precondition:** Manager is viewing the game dashboard. One or more pending requests exist.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Manager Game Dashboard | Notification badge shows pending request count on "Requests" section | Badge shows count (e.g., "3") |
| 2 | Manager Game Dashboard | Taps pending request card or "Requests" section | Pending Requests list is shown / expanded |
| 3 | Pending Requests | Views request card showing: player name, type (cash/credit), amount, timestamp, and who requested it (if on-behalf-of) | Each card has three action buttons |
| 4a | Pending Requests | Taps "Approve" (checkmark button) | POST `/api/transactions/{id}/approve`. Card animates out. Toast: "Approved [amount] for [Player]." |
| 4b | Pending Requests | Taps "Decline" (X button) | Confirmation dialog: "Decline [amount] chip request from [Player]?" with "Decline" and "Cancel" buttons. On confirm: POST `/api/transactions/{id}/reject`. Card animates out. Toast: "Request declined." |
| 4c | Pending Requests | Taps "Edit" (pencil button) | Inline edit: amount field becomes editable with numeric keypad. Manager changes amount and taps "Approve with [new amount]." System creates new transaction with edited amount, approves it, and rejects original |
| 5 | Manager Game Dashboard | All requests handled | "Requests" section shows "No pending requests" empty state |

**Batch handling:** If multiple requests are pending, the manager can swipe through them or handle them sequentially from the list. Approve/decline actions are immediate (no multi-select).

---

### 1.6 Single Player Checkout (Manager Enters Final Chips)

**Precondition:** Game is OPEN. Manager wants to check out one player.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Manager Game Dashboard | Taps on a player row in the player list | Player Detail sheet slides up: shows player name, total buy-ins (cash + credit breakdown), credits owed |
| 2 | Player Detail Sheet | Taps "Check Out" button | Checkout form appears: single numeric input labeled "Final chip count" with numeric keypad |
| 3 | Player Detail Sheet | Enters player's final chip count | System calculates breakdown in real-time below the input: total buy-ins, final chips, net result (profit/loss), credit repayment if applicable, cash to receive/return |
| 4 | Player Detail Sheet | Reviews breakdown, taps "Confirm Checkout" | POST `/api/games/{id}/host-cashout`. Spinner on button |
| 5 | Player Detail Sheet | -- | Success state: breakdown summary shown with green checkmark. Player marked as "Checked Out" |
| 6 | Manager Game Dashboard | Sheet dismisses (tap "Done" or swipe down) | Player row now shows "Checked Out" badge, greyed out. Final chips displayed |

**Breakdown logic displayed to manager:**
```
Final chips:            250
Total buy-ins:         -200  (150 cash + 50 credit)
--------------------------------------------
Net result:             +50  (profit)

Credit owed:             50
Repaid from chips:      -50
--------------------------------------------
Remaining credit:         0

Cash to player:         200  (250 chips - 50 credit repaid)
```

**Error paths:**
- Player already checked out: "Check Out" button replaced with "Checked Out" label.
- Negative final chips entered: validation "Chip count cannot be negative."

---

### 1.7 Whole-Table Checkout (Credit-Debt Players First)

**Precondition:** Game is OPEN. Manager wants to check out all remaining players.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Manager Game Dashboard | Taps "Check Out All" button (appears when 2+ active players remain) | Whole-Table Checkout screen loads |
| 2 | Whole-Table Checkout | Screen shows ordered list of all unchecked players. **Players with credit debt are sorted to the top** with a visual indicator (e.g., "Has credit debt: 50 chips"). Players without debt follow alphabetically | Manager reviews order |
| 3 | Whole-Table Checkout | For each player (starting at top): enters final chip count in the numeric field next to their name | Real-time breakdown shows beside each entry (net result, credit repayment) |
| 4 | Whole-Table Checkout | After entering all amounts, taps "Confirm All Checkouts" | Confirmation dialog: "Check out [N] players? This cannot be undone." |
| 5 | Whole-Table Checkout | Taps "Confirm" in dialog | Sequential POST `/api/games/{id}/host-cashout` for each player (credit-debt players processed first). Progress indicator: "Checking out 1 of N..." |
| 6 | Whole-Table Checkout | All processed | Success screen: summary table of all players with final results. "Continue to Settlement" button appears if credit debts remain. "Close Game" button appears if no debts |
| 7 | Manager Game Dashboard | Taps "Done" or back | Dashboard updated: all players show "Checked Out" |

**Why credit-debt first:** Processing credit-debt players first ensures their chip repayments are applied to the bank before distributing cash to other players, preventing bank shortfall scenarios.

---

### 1.8 Settlement (Mark Debts Settled, Close Game)

**Precondition:** All players are checked out. Game transitions to SETTLING.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Manager Game Dashboard | Taps "Begin Settlement" (appears after all players checked out) | POST `/api/games/{id}/settlement/start`. Game status changes to SETTLING |
| 2 | Settlement Screen -- Phase 1: Credit Resolution | Screen shows list of players with outstanding credit debt. Each row shows: player name, credit owed, repayment status | Manager reviews debts |
| 3 | Settlement Screen | For a player with debt: taps "Mark Settled" button | Confirmation: "[Player] owes [amount] chips in credit. Mark as settled?" |
| 4 | Settlement Screen | Taps "Confirm" | POST `/api/games/{id}/settlement/repay-credit`. Row updates to show "Settled" with checkmark |
| 5 | Settlement Screen | Repeats for each debtor, or taps "Mark All Settled" | All debts marked as resolved |
| 6 | Settlement Screen | Taps "Complete Settlement" (enabled when all debts resolved or explicitly skipped) | POST `/api/games/{id}/settlement/complete`. Game status changes to CLOSED |
| 7 | Game Summary | -- | Final game summary screen: all players listed with net results, total cash flow, credit summary, game duration. "Share Summary" button available |
| 8 | Game Summary | Taps "Share Summary" | Native share sheet with text summary, or copy-to-clipboard |
| 9 | Game Summary | Taps "Done" or back | Returns to Home screen. Game appears in history (if implemented) |

**Player view during SETTLING:**
- Player Game View shows banner: "Game is settling. The manager is resolving final balances."
- Player can view their own summary (total buy-ins, cashout, net, credits owed/settled).
- No new requests can be made.

---

### 1.9 Admin Login and Dashboard

**Precondition:** User knows admin credentials.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Home | Taps "Admin" link (small, in footer or settings) | Navigates to Admin Login screen |
| 2 | Admin Login | Enters username and password | Fields validated for non-empty |
| 3 | Admin Login | Taps "Log In" | POST `/api/auth/login` with credentials. Spinner on button |
| 4 | Admin Dashboard | -- | Dashboard loads with system stats: total games, active games, total players, total transactions, total credits outstanding |
| 5 | Admin Dashboard | Views "Active Games" list | List of all active games: game code, manager name, player count, created timestamp |
| 6 | Admin Dashboard | Views "All Games" with status filter tabs (Active / Settled / Closed / All) | Filtered game list loads via GET `/api/admin/games?status=X` |
| 7 | Admin Dashboard | Taps on a game row | Game Detail (Admin View) loads: full game report with player list, transaction history, bank status |

**Error paths:**
- Invalid credentials: inline error "Invalid username or password."
- Network failure: toast "Login failed. Check your connection."

---

### 1.10 Admin Impersonation (Enter Game as Manager)

**Precondition:** Admin is logged in and viewing a game detail.

| Step | Screen | User Action | System Response |
|------|--------|-------------|-----------------|
| 1 | Game Detail (Admin View) | Taps "Enter as Manager" button | Confirmation dialog: "You will enter this game as the manager. The original manager will retain access. Continue?" |
| 2 | Game Detail (Admin View) | Taps "Continue" | System grants admin the manager role for this game. Navigates to Manager Game Dashboard |
| 3 | Manager Game Dashboard | Admin sees full manager view with a persistent banner: "Admin mode -- managing on behalf of [ManagerName]" | Admin can perform all manager actions (approve requests, check out players, settle) |
| 4 | Manager Game Dashboard | Taps "Exit Admin Mode" in the banner | Returns to Admin Dashboard. Manager role revoked for admin |

**Safeguards:**
- Admin actions are logged with an `admin_override: true` flag.
- Original manager is not disrupted -- they retain full access simultaneously.
- The persistent banner prevents the admin from forgetting they are impersonating.

---

## 2. Screen Inventory

| # | Screen Name | URL Path | Role(s) | Purpose | States |
|---|-------------|----------|---------|---------|--------|
| 1 | Home | `/` | All | Entry point. Create or join a game. Admin access link | **Populated:** Buttons visible. **Loading:** Skeleton shimmer on buttons (brief). **Error:** N/A (static) |
| 2 | Create Game | `/create` | Manager | Enter display name to create a new game | **Default:** Empty name field, "Create Game" button disabled. **Validating:** Inline error on name field. **Submitting:** Button spinner. **Error:** Toast with retry |
| 3 | Join Game | `/join?code=XXXX` | Player | Enter code (pre-filled if from link) and display name to join | **Default:** Code field (empty or pre-filled), name field empty. **Validating:** Inline errors. **Submitting:** Button spinner. **Error:** Inline error (game not found, closed, name taken) |
| 4 | Game Lobby | `/game/:gameId/lobby` | Manager | Post-creation view: share game code, QR, link; see who has joined | **Empty:** No players besides manager. **Populated:** Player list growing. **Loading:** Skeleton on player list. **Error:** Failed to load game data |
| 5 | Manager Game Dashboard | `/game/:gameId/manage` | Manager | Primary manager view: player list, pending requests, game controls, bank status | **Empty:** No players/requests. **Populated:** Player cards, request badges. **Loading:** Skeleton cards. **Error:** Failed to load game. **Settling:** Settlement banner, limited actions |
| 6 | Pending Requests | `/game/:gameId/manage` (section) | Manager | View and action pending chip requests | **Empty:** "No pending requests" illustration. **Populated:** Request cards with actions. **Loading:** Skeleton cards |
| 7 | Player Detail Sheet | (Bottom sheet overlay) | Manager | View player stats and initiate checkout | **Populated:** Player stats, buy-in breakdown. **Checkout mode:** Numeric input, live breakdown. **Checked out:** Summary with green checkmark |
| 8 | Whole-Table Checkout | `/game/:gameId/checkout-all` | Manager | Enter final chip counts for all unchecked players | **Default:** Ordered player list with empty inputs. **Partial:** Some fields filled. **Submitting:** Progress bar. **Complete:** Summary table |
| 9 | Settlement Screen | `/game/:gameId/settle` | Manager | Resolve credit debts, close game | **Phase 1:** Credit debtors listed with action buttons. **Phase 2:** Final cashout forms. **Complete:** All resolved, "Close Game" enabled |
| 10 | Game Summary | `/game/:gameId/summary` | Manager, Player | Final game results: all players, net outcomes, credits | **Populated:** Full results table. **Loading:** Skeleton table |
| 11 | Player Game View | `/game/:gameId/play` | Player | Primary player view: bankroll card, activity feed, request button | **Empty:** "No activity yet" + request chips prompt. **Populated:** Bankroll stats, activity list. **Loading:** Skeleton card + list. **Error:** Failed to load. **Settling:** Read-only banner. **Checked out:** Checkout summary |
| 12 | Chip Request Sheet | (Bottom sheet overlay) | Player | Request chips (cash/credit), optionally for another player | **Default:** Type toggle (Cash selected), empty amount. **For-other mode:** Player picker visible. **Submitting:** Button spinner. **Error:** Inline validation |
| 13 | Admin Login | `/admin/login` | Admin | Username/password login for admin | **Default:** Empty fields. **Validating:** Inline error. **Submitting:** Button spinner. **Error:** "Invalid credentials" |
| 14 | Admin Dashboard | `/admin` | Admin | System overview: stats, game list, filters | **Populated:** Stats cards, game list. **Empty:** "No games yet." **Loading:** Skeleton cards + list. **Error:** Failed to load stats |
| 15 | Game Detail (Admin) | `/admin/game/:gameId` | Admin | Full game report with impersonation option | **Populated:** Game info, player list, transactions, bank status. **Loading:** Skeleton. **Error:** Game not found |
| 16 | Notification Badge/Indicator | (Inline component, not a route) | Player, Manager | Shows unread notification count via polling | **No notifications:** Hidden. **Has notifications:** Badge with count |
| 17 | QR Full-Screen Overlay | (Modal overlay) | Manager | Enlarged QR code for easy scanning | **Populated:** QR code at maximum readable size |

---

## 3. Screen Transition Diagram

```
                                HOME (/)
                              /    |    \
                            /      |      \
                          v        v        v
                   Create Game   Join Game   Admin Login
                   (/create)     (/join)     (/admin/login)
                       |             |             |
                       v             |             v
                  Game Lobby         |       Admin Dashboard
                  (/game/:id/       |        (/admin)
                    lobby)           |          |    \
                       |             |          |     v
                       v             |          |   Game Detail (Admin)
              Manager Game           |          |   (/admin/game/:id)
              Dashboard              |          |       |
              (/game/:id/manage)     |          |       v
              /     |     \          |          |   [Enter as Manager]
             /      |      \         |          |       |
            v       v       v        v          |       v
     Pending   Player    Whole-    Player       |   Manager Game
     Requests  Detail    Table     Game View    |   Dashboard
     (section) Sheet     Checkout  (/game/      |   (with admin banner)
        |       |        (/game/    :id/play)   |
        |       |         :id/       |          |
        |       |       checkout-    v          |
        |       |        all)   Chip Request    |
        |       v           |   Sheet           |
        |   [Checkout       |   (overlay)       |
        |    confirmed]     |                   |
        |       |           v                   |
        |       v      [All checked out]        |
        |   Dashboard       |                   |
        |   updated         v                   |
        |              Settlement               |
        |              (/game/:id/settle)       |
        |                   |                   |
        |                   v                   |
        |              Game Summary             |
        |              (/game/:id/summary) <----+
        |                   |
        v                   v
   [All handled]         HOME (/)
        |
        v
   Dashboard updated
```

### Transition Triggers

| From | To | Trigger |
|------|----|---------|
| Home | Create Game | Tap "New Game" |
| Home | Join Game | Tap "Join Game" |
| Home | Join Game (pre-filled) | Open shared link or scan QR |
| Home | Admin Login | Tap "Admin" footer link |
| Create Game | Game Lobby | Successful game creation |
| Join Game | Player Game View | Successful join |
| Game Lobby | Manager Game Dashboard | Tap "Start Managing" or automatic after first player joins |
| Manager Game Dashboard | Pending Requests | Tap requests section / notification badge |
| Manager Game Dashboard | Player Detail Sheet | Tap player row |
| Manager Game Dashboard | Whole-Table Checkout | Tap "Check Out All" |
| Manager Game Dashboard | Settlement Screen | Tap "Begin Settlement" (after all checked out) |
| Player Detail Sheet | Manager Game Dashboard | Checkout confirmed, tap "Done" |
| Whole-Table Checkout | Manager Game Dashboard | All checkouts confirmed, tap "Done" |
| Whole-Table Checkout | Settlement Screen | Tap "Continue to Settlement" |
| Settlement Screen | Game Summary | Settlement completed |
| Game Summary | Home | Tap "Done" |
| Player Game View | Chip Request Sheet | Tap "Request Chips" |
| Chip Request Sheet | Player Game View | Request submitted or sheet dismissed |
| Admin Login | Admin Dashboard | Successful login |
| Admin Dashboard | Game Detail (Admin) | Tap game row |
| Game Detail (Admin) | Manager Game Dashboard | Tap "Enter as Manager" |
| Manager Game Dashboard (admin) | Admin Dashboard | Tap "Exit Admin Mode" |

---

## 4. Edge Cases

### 4.1 Player Leaves Mid-Game (Browser Closed / Navigates Away)

**Scenario:** A player closes their browser or navigates away during an active game.

**Handling:**
- The player's session is preserved via `localStorage` (player ID, game ID, role).
- When the player returns and opens the app, the system checks `localStorage` for an active session.
- If the game is still OPEN: player is returned to Player Game View with current data. No re-join needed.
- If the game is SETTLING: player sees the settling banner with their summary.
- If the game is CLOSED: player sees the Game Summary screen.
- Player is never auto-removed from the game. The manager must explicitly check them out (with 0 chips if they abandoned).
- Poll continues to mark the player as "idle" if no poll activity for 5+ minutes (visual indicator for manager: "Last seen 10 min ago").

### 4.2 Manager Phone Dies / Disconnects

**Scenario:** The manager's phone dies or loses connectivity during the game.

**Handling:**
- Game state is fully server-side. No data is lost.
- Manager session is in `localStorage`. When the manager returns and reopens the app, they are returned to Manager Game Dashboard.
- Pending requests remain pending until the manager returns.
- Players see requests stuck in "Pending" state. The app does not show a "manager offline" indicator (polling model makes this unreliable), but requests older than 5 minutes could show "Sent 5 min ago" timestamps so players can verbally follow up.
- If the manager cannot return, an admin can impersonate the manager role to continue the game (see flow 1.10).
- The 24-hour auto-close acts as a safety net.

### 4.3 Duplicate Join Attempt

**Scenario:** A player tries to join a game they are already in, or a second browser tab tries to join with the same name.

**Handling:**
- **Same player ID, same game:** The API detects the player is already in the game (via `user_id` match). Instead of creating a duplicate, the system returns the existing session and navigates to Player Game View. Toast: "You're already in this game."
- **Different player ID, same display name:** The API rejects with HTTP 400. Inline error on Join Game screen: "That name is already taken. Choose another."
- **Same player, different browser/device:** The player can have the game open on multiple devices simultaneously. All views show the same data via polling. Actions from any device are reflected everywhere.

### 4.4 Request After SETTLING

**Scenario:** A player attempts to request chips after the game has entered SETTLING status.

**Handling:**
- When the game enters SETTLING, the Player Game View hides the "Request Chips" button entirely.
- A banner replaces it: "Game is settling. No new requests."
- If a stale client somehow sends a POST to `/api/transactions/buyin`, the API checks game status and returns HTTP 400: "Game is no longer accepting requests."
- The next poll cycle will update the client to reflect the SETTLING state.

### 4.5 Player Joins Closed Game

**Scenario:** A player opens an old join link or enters a code for a game that has already closed.

**Handling:**
- The Join Game screen sends the code to the API.
- The API checks game status. If CLOSED, it returns HTTP 400 with a specific error code.
- Join Game screen shows: "This game has ended." with a single "Go Home" button.
- The QR code and share link remain functional (they don't expire) but lead to this dead-end message.
- No option to join -- the game is immutable once closed.

### 4.6 24-Hour Auto-Close While Active

**Scenario:** A game has been running for 24 hours and the system auto-closes it.

**Handling:**
- A background job (or checked on each API call) evaluates game age.
- When 24 hours elapse:
  1. Game status changes to SETTLING (not directly to CLOSED), giving the manager a chance to handle checkouts.
  2. All pending requests are auto-declined with reason: "Game expired after 24 hours."
  3. Manager receives a prominent banner on next poll: "This game has been open for 24 hours and is now settling. Please check out all players."
  4. Players receive a banner: "Game is settling (24-hour limit reached)."
- The manager can still perform checkouts and settlement normally from SETTLING state.
- If the manager never returns, a second timeout (48 hours total) closes the game entirely:
  - All unchecked players are marked with final chips = 0.
  - Game status changes to CLOSED.
  - Credit debts remain recorded but unresolved.

### 4.7 On-Behalf-Of Request for Player Not in Game

**Scenario:** A player tries to make an on-behalf-of request, but references a player who is not in the game (edge case if player list is stale).

**Handling:**
- The Chip Request Sheet shows only players currently in the game (fetched fresh when the sheet opens).
- If the target player was removed between the sheet opening and form submission:
  - The API validates the target `user_id` against the game's player list.
  - Returns HTTP 400: "That player is no longer in this game."
  - The sheet remains open. The player list refreshes. Toast: "Player not found. They may have left."
- The player picker does not show checked-out players (they cannot receive chips).

---

## 5. Navigation Design

### 5.1 Design Principle: 2-Tap Maximum

Every primary action for each role is reachable within 2 taps from their main screen.

### 5.2 Manager -- Primary Actions (from Manager Game Dashboard)

| Action | Taps | Path |
|--------|------|------|
| View pending requests | 1 | Tap "Requests" section (on-screen, not hidden) |
| Approve a request | 2 | Tap "Requests" section (1) then tap "Approve" on card (2) |
| Decline a request | 2 | Tap "Requests" section (1) then tap "Decline" on card (2) |
| View player detail | 1 | Tap player row |
| Check out a player | 2 | Tap player row (1) then tap "Check Out" (2) |
| Check out all players | 1 | Tap "Check Out All" button |
| Share game code | 1 | Tap share/copy icon in header |
| Begin settlement | 1 | Tap "Begin Settlement" button |

### 5.3 Player -- Primary Actions (from Player Game View)

| Action | Taps | Path |
|--------|------|------|
| Request chips | 1 | Tap "Request Chips" button (fixed at bottom) |
| Submit chip request | 2 | Tap "Request Chips" (1) then enter amount and tap "Send" (2) |
| Request for another player | 2 | Tap "Request Chips" (1) then toggle "For another player," select player, tap "Send" (2) |
| View own bankroll | 0 | Visible on main screen (bankroll card at top) |
| View activity history | 0 | Visible on main screen (activity feed below bankroll) |
| View game code | 1 | Tap game code in header (copies to clipboard) |

### 5.4 Admin -- Primary Actions (from Admin Dashboard)

| Action | Taps | Path |
|--------|------|------|
| View system stats | 0 | Visible on dashboard |
| View game list | 0 | Visible on dashboard (below stats) |
| Filter games by status | 1 | Tap filter tab |
| View game detail | 1 | Tap game row |
| Enter game as manager | 2 | Tap game row (1) then tap "Enter as Manager" (2) |
| Destroy game | 2 | Tap game row (1) then tap "Destroy Game" (2, with confirmation) |

### 5.5 Navigation Structure

**Manager Game Dashboard Layout:**
```
+----------------------------------+
|  [<-]  Game XXXX       [Share]   |  <- Header: back, game code, share
+----------------------------------+
|  Bank: 500 chips  |  Players: 6  |  <- Stats bar
+----------------------------------+
|  [!] 3 Pending Requests    [>]   |  <- Requests section (tappable)
+----------------------------------+
|  PLAYERS                         |
|  +----------------------------+  |
|  | Alice       150 chips   [>]|  |  <- Player rows
|  | Bob (credit) 80 chips  [>]|  |
|  | Carol     Checked Out   -- |  |
|  +----------------------------+  |
+----------------------------------+
|        [ Check Out All ]         |  <- Primary action (when applicable)
+----------------------------------+
```

**Player Game View Layout:**
```
+----------------------------------+
|  [<-]  Game XXXX                 |  <- Header: back, game code
+----------------------------------+
|  +----------------------------+  |
|  |  YOUR BANKROLL              |  |
|  |  Total: 250 chips           |  |  <- Bankroll card
|  |  Cash: 150 | Credit: 100   |  |
|  +----------------------------+  |
+----------------------------------+
|  ACTIVITY                        |
|  +----------------------------+  |
|  | Cash buy-in: 150  Approved  |  |
|  | Credit buy-in: 100 Approved |  |  <- Activity feed
|  | ...                         |  |
|  +----------------------------+  |
+----------------------------------+
|       [ Request Chips ]          |  <- Fixed bottom button (primary)
+----------------------------------+
```

---

## 6. Mobile Considerations

### 6.1 Viewport & Layout

- **Minimum viewport:** 375px wide (iPhone SE / small Android devices).
- **Design approach:** Mobile-first. Single-column layout at all breakpoints below 768px. No horizontal scrolling.
- **Safe area insets:** Respect `env(safe-area-inset-*)` for devices with notches and home indicators. Bottom buttons must clear the home indicator.
- **Orientation:** Portrait primary. Landscape is supported but not optimized (content reflows, no layout changes).

### 6.2 Touch Targets

All interactive elements meet or exceed minimum touch target sizes:

| Element | Minimum Size | Notes |
|---------|-------------|-------|
| Buttons (primary) | 48px height, full-width | Large, easy to tap with thumb |
| Buttons (secondary) | 44x44px | Approve/decline action buttons |
| List rows (tappable) | 56px minimum height | Player rows, request cards |
| Input fields | 48px height | Comfortable for text entry |
| Toggle controls | 44x44px tap area | Cash/Credit segmented control |
| Icon buttons (share, copy) | 44x44px | Includes padding beyond visual icon |
| Bottom sheet drag handle | 44x20px + 12px padding above | Easy to grab for dismissal |
| Close / back buttons | 44x44px | Header navigation |

Reference: WCAG 2.2 Success Criterion 2.5.8 (Target Size Minimum) requires at least 24x24px; we exceed this with 44px minimum following Apple HIG and Material Design guidance.

### 6.3 Thumb Zone Optimization

The app is designed for one-handed use at a poker table (the other hand holds cards).

```
+----------------------------------+
|                                  |  <- "Stretch zone" (header only,
|                                  |     infrequent actions: back, share)
|                                  |
|  [Content area: read-mostly]     |  <- "Natural zone" (scrollable
|                                  |     content: player list, activity)
|                                  |
|                                  |
+----------------------------------+
|  [PRIMARY ACTION BUTTON]         |  <- "Easy zone" (most frequent action
+----------------------------------+     fixed at bottom of viewport)
```

- **Primary actions at the bottom:** "Request Chips" (player), "Check Out All" (manager) are pinned to the bottom of the viewport in the easy thumb zone.
- **Notification badge / pending requests:** Positioned in the upper-middle of the scrollable area, not the top of the screen, so it scrolls into the natural zone quickly.
- **Destructive actions** (decline, destroy) require deliberate reach to confirmation dialogs, reducing accidental taps.

### 6.4 Numeric Input

All chip-amount inputs use `inputmode="numeric"` (not `type="number"`) to trigger the numeric keypad on mobile while avoiding the browser's native number input spinners and validation quirks.

```html
<input
  inputmode="numeric"
  pattern="[0-9]*"
  placeholder="0"
  autocomplete="off"
  aria-label="Chip amount"
/>
```

- `pattern="[0-9]*"` triggers the numeric-only keypad on iOS (no decimal point, no negative sign).
- `autocomplete="off"` prevents autofill suggestions over the keypad.
- No currency symbols or formatting -- chips are always whole numbers.

### 6.5 Swipe Gestures

Swipe gestures are used sparingly and always have a tap alternative:

| Gesture | Screen | Action | Tap Alternative |
|---------|--------|--------|-----------------|
| Swipe down on bottom sheet | Chip Request Sheet, Player Detail Sheet | Dismiss sheet | Tap outside sheet or "X" button |
| Swipe left on request card | Pending Requests | Reveal "Decline" action | Tap "Decline" button |
| Swipe right on request card | Pending Requests | Reveal "Approve" action | Tap "Approve" button |
| Pull down on any list | Any screen with data | Refresh data (bypasses poll interval) | No dedicated button; poll handles updates |

**No critical actions rely on swipe.** All swipe actions have visible button equivalents. Swipe affordance is indicated via subtle animation on first view (teach gesture).

### 6.6 Keyboard & Focus Management

- **Auto-focus:** When the Chip Request Sheet opens, the amount field is auto-focused and the numeric keypad appears immediately. No extra tap needed.
- **Form submission:** Pressing "Done" / "Go" on the mobile keyboard triggers form submission (via `enterkeyhint="done"`).
- **Bottom sheet + keyboard:** When the keyboard is open inside a bottom sheet, the sheet content scrolls so the active input is visible above the keyboard. The sheet does not resize -- it pushes content up.
- **Focus trap in modals:** When a bottom sheet or dialog is open, focus is trapped within it. Tab/Shift+Tab cycles through interactive elements inside the overlay. `Escape` key dismisses it.

### 6.7 Performance & Perceived Performance

- **Polling interval:** 5 seconds for active game screens (Manager Dashboard, Player Game View). 30 seconds for inactive screens (Game Summary, Admin Dashboard).
- **Skeleton screens:** All data-dependent screens show skeleton loading states (shimmer placeholders matching content layout) on initial load. Subsequent polls update in place with no skeleton.
- **Optimistic UI:** When a player submits a chip request, the request appears immediately in their activity feed as "Pending" before the server confirms. If the server call fails, the item is removed and an error toast shown.
- **Transition animations:** Bottom sheets slide up at 300ms with ease-out easing. Cards animate out at 200ms on approval/decline. All animations respect `prefers-reduced-motion: reduce` by switching to instant opacity transitions.

### 6.8 Offline & Poor Connectivity

- **No offline mode.** The app requires connectivity to function (all state is server-side).
- **Connectivity loss:** If a poll or action request fails 3 consecutive times, a non-blocking banner appears at the top: "Connection lost. Retrying..." The banner clears automatically when connectivity returns.
- **Retry logic:** Failed actions (chip request, checkout) show a toast with a "Retry" button. The form state is preserved so the user does not need to re-enter data.
- **Request deduplication:** Each action request includes a client-generated idempotency key to prevent duplicate transactions if a retry succeeds twice.

---

## Appendix A: Game State Machine

```
         create_game()
              |
              v
   +----------+----------+
   |                      |
   |        OPEN          |  <-- Players join, request chips,
   |                      |      manager approves/declines,
   +----------+----------+      checkouts happen
              |
              |  begin_settlement() OR 24h timeout
              v
   +----------+----------+
   |                      |
   |      SETTLING        |  <-- No new joins or requests.
   |                      |      Credit resolution, final cashouts.
   +----------+----------+
              |
              |  complete_settlement() OR 48h hard timeout
              v
   +----------+----------+
   |                      |
   |       CLOSED         |  <-- Immutable. Read-only summary.
   |                      |
   +----------------------+
```

## Appendix B: Polling Strategy

| Screen | Poll Endpoint | Interval | Data Refreshed |
|--------|--------------|----------|----------------|
| Manager Game Dashboard | GET `/api/games/:id/status` + GET `/api/games/:id/transactions/pending` | 5s | Player list, bank, pending requests |
| Player Game View | GET `/api/games/:id/players/:uid/summary` + GET `/api/games/:id/status` | 5s | Bankroll, game status, request statuses |
| Game Lobby | GET `/api/games/:id/players` | 5s | Player join list |
| Admin Dashboard | GET `/api/admin/stats` + GET `/api/admin/games` | 30s | System stats, game list |
| Settlement Screen | GET `/api/games/:id/settlement/status` | 5s | Debt resolution status |
| Game Summary | None (static once loaded) | -- | -- |

Polling uses `setInterval` with automatic pause when the browser tab is not visible (`document.visibilityState === 'hidden'`) and resumes with an immediate fetch when the tab becomes visible again.

## Appendix C: Accessibility Notes

- All screens use semantic HTML landmarks: `<header>`, `<main>`, `<nav>`, `<footer>`.
- Bottom sheets use `role="dialog"` with `aria-modal="true"` and an `aria-label` describing the dialog purpose.
- Live regions (`aria-live="polite"`) announce: toast notifications, request approval/decline status changes, bankroll updates.
- The pending request count badge uses `aria-label="3 pending requests"` (not just the number).
- Color is never the sole indicator of state. All statuses (Pending, Approved, Declined, Checked Out) use text labels alongside color.
- Focus indicators are visible (2px solid outline, offset by 2px) on all interactive elements. Never suppressed.
- Game code is displayed in a monospace font at large size with letter-spacing for readability, and is announced character-by-character to screen readers via `aria-label="Game code: A, B, C, D"`.
