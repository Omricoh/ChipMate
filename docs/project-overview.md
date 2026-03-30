# ChipMate Project Overview

## What This Project Is

ChipMate is a mobile-first web app for running live poker games. It lets a host create and manage a game, lets players join without accounts, tracks cash and credit buy-ins, and supports a structured end-of-game settlement flow.

The codebase has three actor types:

- `Admin`: system-level operator with access to admin login and global game oversight.
- `Host`: the manager of a specific poker game.
- `Player`: participant in a specific poker game.

The host workflow is the core product flow. Admin exists for support and operations, not for running normal games.

## Current Stack

- Backend: FastAPI, async Motor/MongoDB, Pydantic
- Frontend: React 18, TypeScript, Vite, TailwindCSS
- Database: MongoDB
- Tests: Pytest with `mongomock-motor`
- Deployment: Docker locally, Railway in production

## High-Level Architecture

### Backend

The backend follows a layered structure:

- `backend/app/routes/`: HTTP API handlers
- `backend/app/services/`: business logic
- `backend/app/dal/`: MongoDB data access
- `backend/app/models/`: domain and response models
- `backend/app/auth/`: admin JWT and player-token auth
- `backend/app/tasks/`: background tasks such as game expiry

The main application entry point is [`backend/app/main.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/main.py).

### Frontend

The frontend is a React SPA with route-based screens and game/admin contexts:

- `frontend/src/pages/`: route-level pages
- `frontend/src/components/game/`: host/player game UI
- `frontend/src/components/common/`: shared UI primitives
- `frontend/src/api/`: typed API client functions
- `frontend/src/hooks/`: polling and data-fetching hooks
- `frontend/src/context/`: auth and game state

The route map is defined in [`frontend/src/App.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/App.tsx).

## Main User Flows

### 1. Host creates a game

- A host enters a display name.
- The app creates a game and manager player record.
- The host lands in the game dashboard with share tools and player list.

### 2. Players join

- Players can join from a direct link, QR code, or manual code entry.
- Players are identified by a generated player token, not a registered account.

### 3. Players request buy-ins

- Players request chips as `CASH` or `CREDIT`.
- Requests start as `PENDING`.
- The host can approve, decline, or edit-and-approve pending requests.

### 4. Host manages transactions

- Approved chip requests become the source of truth for applied transactions.
- The host dashboard now includes a `Transactions` box showing applied transactions ordered by time.
- While a game is `OPEN`, the host can:
  - change transaction method
  - change transaction amount
  - remove a transaction
- These actions rebuild the real bank totals and player credit balances from the transaction history.

### 5. Settlement and checkout

- When the host starts settling, the game moves out of normal buy-in mode.
- Player checkout and distribution logic runs through the settlement services.
- Once settlement is complete, the game is closed.

## Actor Model

### Admin

Admin is authenticated separately and has system-wide access.

Current admin capabilities include:

- admin login
- viewing game stats and game details
- impersonating a host
- force-closing games

Admin UI lives primarily in [`frontend/src/pages/AdminDashboard.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/pages/AdminDashboard.tsx).

### Host

Host is a player with `is_manager = true` inside a specific game.

Key host capabilities:

- create and share a game
- view players and pending requests
- approve, decline, or edit pending requests
- add buy-ins on behalf of players
- manage applied transactions
- initiate and manage settlement

The main host UI is [`frontend/src/components/game/ManagerDashboard.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/components/game/ManagerDashboard.tsx).

### Player

Players join a specific game and operate through their player token.

Key player capabilities:

- join a game
- request chips
- view request history
- see game state and personal chip state
- participate in checkout/settlement flow

## Core Domain Concepts

### Game

A game stores:

- lifecycle state: `OPEN`, `SETTLING`, `CLOSED`
- manager player token
- timestamps
- embedded bank totals
- settlement state fields

Defined in [`backend/app/models/game.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/models/game.py).

### Player

A player record is scoped to a single game and includes:

- display name
- manager flag
- active/checked-out state
- credits owed
- settlement-related fields

Defined in [`backend/app/models/player.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/models/player.py).

### Chip Request / Transaction

ChipMate uses `chip_requests` as the canonical buy-in/transaction record.

Important fields:

- `request_type`: `CASH` or `CREDIT`
- `status`: `PENDING`, `APPROVED`, `DECLINED`, `EDITED`
- `amount`
- `edited_amount`
- `player_token`
- `requested_by`

Applied transactions are requests whose effective amount is non-zero:

- `APPROVED` uses `amount`
- `EDITED` uses `edited_amount`

Defined in [`backend/app/models/chip_request.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/models/chip_request.py).

## Financial Rules

### Cash

Cash buy-ins affect:

- `bank.total_cash_in`
- `bank.cash_balance`
- `bank.total_chips_issued`
- `bank.chips_in_play`

### Credit

Credit buy-ins affect:

- `bank.total_credits_issued`
- `bank.total_chips_issued`
- `bank.chips_in_play`
- `player.credits_owed`

### Transaction edits/removals

When the host edits or removes an applied transaction, the backend recalculates:

- `bank.total_cash_in`
- `bank.cash_balance`
- `bank.total_credits_issued`
- `bank.total_chips_issued`
- `bank.chips_in_play`
- each player’s `credits_owed`

That logic lives in [`backend/app/services/request_service.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/services/request_service.py).

## Important API Areas

### Auth

- Admin login
- Player token validation
- Manager/player/admin dependency guards

See [`backend/app/routes/auth.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/auth.py) and [`backend/app/auth/`](/Users/b/Documents/GitHub/ChipMate/backend/app/auth).

### Games

- create game
- join game
- get game state
- player list and status

See [`backend/app/routes/games.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/games.py).

### Chip Requests / Transactions

- create request
- get pending requests
- get request history
- approve / decline / edit pending request
- update applied transaction
- delete applied transaction

See [`backend/app/routes/chip_requests.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/chip_requests.py).

### Settlement

- start settling
- checkout inputs and validation
- distribution and completion

See [`backend/app/routes/settlement.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/settlement.py).

### Admin

- dashboard stats
- list games
- game detail
- force close
- impersonation

See [`backend/app/routes/admin.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/admin.py).

## Frontend Route Map

- `/`: home
- `/create`: create game
- `/join` and `/join/:gameCode`: join game
- `/game/:gameId`: player/host game view
- `/admin`: admin login
- `/admin/dashboard`: admin dashboard

## Key Files to Start With

If you need to understand the code quickly, start here:

- [`README.md`](/Users/b/Documents/GitHub/ChipMate/README.md)
- [`backend/app/main.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/main.py)
- [`backend/app/routes/games.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/games.py)
- [`backend/app/routes/chip_requests.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/routes/chip_requests.py)
- [`backend/app/services/request_service.py`](/Users/b/Documents/GitHub/ChipMate/backend/app/services/request_service.py)
- [`frontend/src/App.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/App.tsx)
- [`frontend/src/components/game/ManagerDashboard.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/components/game/ManagerDashboard.tsx)
- [`frontend/src/pages/GameView.tsx`](/Users/b/Documents/GitHub/ChipMate/frontend/src/pages/GameView.tsx)

## Tests

Backend tests are extensive and are the fastest way to validate behavior changes.

Relevant areas:

- `backend/tests/test_requests/`
- `backend/tests/test_services/`
- `backend/tests/test_settlement/`
- `backend/tests/test_admin/`

## Notes on Current State

- The codebase is beyond the original scaffold stage described in the README.
- The host transaction-management flow is now implemented in the normal game dashboard.
- Frontend build in this workspace currently depends on installing frontend dependencies first.

