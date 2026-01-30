# ChipMate - Poker Game Management System

## Project Overview

ChipMate is a comprehensive, full-stack poker game management system designed to streamline the complex financial tracking of poker games. It provides a complete solution for managing buy-ins, cashouts, credit tracking, and end-game settlements in both casual and organized poker games.

### The Problem ChipMate Solves

Traditional poker games face several challenges:
- **Manual Cash Tracking**: Hosts must manually track who brought cash and how much
- **Credit Management**: Difficult to track who owes money and to whom
- **Settlement Complexity**: End-game settlements become messy when players leave at different times
- **Trust Issues**: Lack of transparent, real-time tracking leads to disputes
- **Host Burden**: Game hosts spend excessive time managing finances instead of playing

### ChipMate's Solution

ChipMate provides a centralized, automated banking system that:
- **Tracks every transaction** with approval workflows
- **Manages credits systematically** through a virtual bank
- **Automates settlements** with a two-phase process
- **Provides real-time visibility** to all players
- **Reduces host workload** through automation and clear interfaces

### Architecture Overview

ChipMate is built as a modern, three-tier web application:

**Frontend Layer:**
- **Angular 17+** single-page application
- **Bootstrap 5** for responsive, mobile-friendly UI
- **TypeScript** for type-safe client code
- **Real-time updates** via REST API polling

**Backend Layer:**
- **Python 3.8+** with Flask framework
- **RESTful API** with 30+ endpoints
- **Business logic separation** (BL/Service/DAL architecture)
- **Pydantic** models for data validation

**Data Layer:**
- **MongoDB** for flexible document storage
- **Data Access Layer (DAL)** for database abstraction
- Collections: Games, Players, Transactions, Bank, Unpaid Credits

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Angular 17+ | Modern SPA framework |
| | TypeScript 5.2+ | Type-safe development |
| | Bootstrap 5.3 | Responsive UI components |
| | RxJS 7.8 | Reactive programming |
| | QRCode library | QR code generation |
| **Backend** | Python 3.8+ | Server-side logic |
| | Flask 3.0 | Web framework & REST API |
| | Pydantic 2.7 | Data validation |
| | Gunicorn 21.2 | Production WSGI server |
| **Database** | MongoDB | Document database |
| | PyMongo | MongoDB driver |
| **DevOps** | Railway | Cloud hosting platform |
| | Nixpacks | Build system |
| **Testing** | Pytest | Python testing framework |
| | Jasmine/Karma | Angular testing |
| | Mongomock | MongoDB mocking |

---

## Core Features

### Feature 1: Game Creation and Management

**Purpose**: Allow hosts to create and manage poker games with unique identification.

**How It Works:**
- Host creates a new game by entering their name
- System generates a unique 6-character game code (e.g., "ABC123")
- Game starts in "active" status
- Host receives host privileges for the entire game lifecycle

**Technical Details:**
- Endpoint: `POST /api/games`
- Creates Game document in MongoDB
- Initializes Bank entity with zero balances
- Assigns incremental user_id to host
- Game code stored for player joining

**User Experience:**
```
Host: "Create New Game"
├─ Enter Name: "John"
├─ System generates: Code "XYZ789"
└─ Game Created! Share code with players
```

**Database Schema:**
```javascript
Game {
  _id: ObjectId,
  host_id: int,
  host_name: string,
  status: "active" | "ending" | "settled" | "expired",
  settlement_phase: null | "credit_settlement" | "final_cashout" | "completed",
  created_at: datetime,
  ended_at: datetime | null,
  players: [user_id],
  code: string (6 chars)
}
```

---

### Feature 2: Player Joining System

**Purpose**: Enable players to join games easily using a shared game code.

**How It Works:**
- Player receives game code from host (e.g., via QR code or text)
- Player enters code and their name
- System verifies game exists and is active
- Player added to game with unique user_id

**Technical Details:**
- Endpoint: `POST /api/games/join`
- Validates game code existence
- Checks game status is "active"
- Creates Player document
- Assigns sequential user_id within game
- Returns game_id and player info

**User Experience:**
```
Player: "Join Game"
├─ Enter Code: "ABC123"
├─ Enter Name: "Sarah"
├─ Validation...
└─ Joined! Ready to buy-in
```

**Database Schema:**
```javascript
Player {
  _id: ObjectId,
  game_id: string,
  user_id: int (sequential per game),
  name: string,
  credits_owed: int (default: 0),
  final_chips: int | null,
  quit: bool (default: false),
  is_host: bool,
  active: bool (default: true),
  cashed_out: bool (default: false),
  cashout_time: datetime | null
}
```

---

### Feature 3: QR Code Generation for Game Joining

**Purpose**: Provide a frictionless way for players to join games using their mobile devices.

**How It Works:**
- Host requests QR code for their game
- System generates QR code containing join link
- Players scan QR code with camera
- Automatically redirects to join page with game code pre-filled

**Technical Details:**
- Endpoint: `GET /api/games/<code>/link`
- Uses Python `qrcode` library with PIL
- Generates base64-encoded PNG image
- Embeds app URL + game code
- Returns both link and QR image

**User Experience:**
```
Host: "Show QR Code"
├─ QR Code displayed
├─ Player scans with phone
├─ Opens: https://chipmate.app/join?code=ABC123
└─ Player just enters name and joins
```

**Implementation:**
```python
# Backend generates
qr_code_url = f"{APP_URL}/join?code={game_code}"
qr_image = qrcode.make(qr_code_url)
# Convert to base64 PNG
```

---

### Feature 4: Cash Buy-In System

**Purpose**: Track players bringing cash to the game and receiving chips.

**How It Works:**
1. Player selects "Cash Buy-In"
2. Enters amount (e.g., $100)
3. Transaction created in "pending" state
4. Host sees pending transaction
5. Host approves transaction
6. **Bank receives cash** and issues chips to player

**Technical Details:**
- Endpoint: `POST /api/transactions/buyin`
- Creates Transaction with type="buyin_cash"
- Approval endpoint: `POST /api/transactions/<id>/approve`
- Bank updates:
  - `cash_balance += amount`
  - `total_cash_in += amount`
  - `total_chips_issued += amount`
  - `chips_in_play += amount`

**Critical Flow:**
```
Player brings $100 cash
├─ Transaction created (pending)
├─ Host approves
├─ Bank: cash_balance: 0 → 100
├─ Bank: chips_in_play: 0 → 100
└─ Player has 100 chips
```

**Database Schema:**
```javascript
Transaction {
  _id: ObjectId,
  game_id: string,
  user_id: int,
  type: "buyin_cash" | "buyin_register" | "cashout",
  amount: int,
  confirmed: bool (default: false),
  rejected: bool (default: false),
  at: datetime
}
```

**Bank Entity:**
```javascript
Bank {
  game_id: string,
  cash_balance: int,        // Current cash in bank
  total_cash_in: int,       // Total cash received
  total_cash_out: int,      // Total cash paid out
  total_chips_issued: int,  // Total chips given to players
  total_chips_returned: int,// Total chips returned
  chips_in_play: int,       // Current chips with players
  total_credits_issued: int,
  total_credits_repaid: int
}
```

---

### Feature 5: Credit Buy-In System

**Purpose**: Allow players to buy chips on credit when they don't have cash available.

**How It Works:**
1. Player selects "Credit Buy-In"
2. Enters amount (e.g., $50)
3. Transaction created in "pending" state
4. Host approves transaction
5. **Bank issues chips on credit**
6. Player's `credits_owed` increases by amount

**Technical Details:**
- Endpoint: `POST /api/transactions/buyin` with type="buyin_register"
- Creates pending transaction
- On approval:
  - Updates `Player.credits_owed += amount`
  - Bank updates:
    - `total_credits_issued += amount`
    - `total_chips_issued += amount`
    - `chips_in_play += amount`
  - **No cash enters bank**

**Critical Flow:**
```
Player requests $50 credit
├─ Transaction created (pending)
├─ Host approves
├─ Bank: chips_in_play: 100 → 150
├─ Bank: total_credits_issued: 0 → 50
├─ Player: credits_owed: 0 → 50
└─ Player has 50 chips (owes $50 to bank)
```

**Key Difference from Cash Buy-In:**
- **Cash Buy-In**: Bank receives cash → issues chips
- **Credit Buy-In**: Bank issues chips → player owes debt

---

### Feature 6: Transaction Approval Workflow

**Purpose**: Ensure host has control over all money movements in the game.

**How It Works:**
1. All transactions start in "pending" state
2. Host receives real-time list of pending transactions
3. Host can approve or reject each transaction
4. Only approved transactions affect bank balances
5. Rejected transactions are marked but don't execute

**Technical Details:**
- Endpoint: `POST /api/transactions/<id>/approve`
- Endpoint: `POST /api/transactions/<id>/reject`
- Get pending: `GET /api/games/<id>/transactions/pending`
- Approval triggers bank operations via TransactionService
- Rejection sets `transaction.rejected = true`

**User Experience:**
```
Host View:
├─ Pending Transactions (3)
│  ├─ Sarah - Cash Buy-In $100 [Approve] [Reject]
│  ├─ Mike - Credit Buy-In $50 [Approve] [Reject]
│  └─ Lisa - Cashout 75 chips [Approve] [Reject]
```

**Transaction States:**
```
Created → Pending
         ├─ Approved → Executed
         └─ Rejected → Cancelled
```

---

### Feature 7: Cashout System with Credit Repayment

**Purpose**: Allow players to convert chips back to cash or credit repayment.

**How It Works:**
1. Player enters chip count to cash out
2. System calculates:
   - How much goes to credit repayment
   - How much becomes cash (if bank has cash)
3. Transaction created
4. Host approves
5. Bank executes cashout

**Technical Details:**
- Endpoint: `POST /api/transactions/cashout`
- Calculation logic:
  ```python
  chips_returned = player_input
  credits_to_repay = min(chips_returned, player.credits_owed)
  remaining_chips = chips_returned - credits_to_repay
  cash_payment = min(remaining_chips, bank.cash_balance)
  ```
- Bank updates on approval:
  - `chips_in_play -= chips_returned`
  - `total_chips_returned += chips_returned`
  - `player.credits_owed -= credits_to_repay`
  - `cash_balance -= cash_payment`

**Example Scenario:**
```
Player Stats:
├─ Current chips: 200
├─ Credits owed: 50
└─ Wants to cash out: 200 chips

Calculation:
├─ First: Repay credits (200 - 50 = 150 remaining)
├─ Bank has: $120 cash
├─ Player receives: $120 cash
└─ Player still has: 30 chip value (no cash available)
```

**Critical Rule:**
**Credits are ALWAYS repaid first before any cash is given.**

---

### Feature 8: Real-Time Game Status

**Purpose**: Provide all players with up-to-date information about the game state.

**How It Works:**
- Frontend polls game status every few seconds
- Backend aggregates data from multiple sources
- Returns comprehensive game state
- Players see live updates without refresh

**Technical Details:**
- Endpoint: `GET /api/games/<id>/status`
- Returns:
  - Game metadata (code, host, status)
  - All players with current chip counts
  - Bank status (cash balance, credits owed)
  - Pending transactions count
  - Settlement phase (if ending)

**Response Structure:**
```json
{
  "game": {
    "id": "...",
    "code": "ABC123",
    "host_name": "John",
    "status": "active",
    "created_at": "2024-01-15T10:30:00Z"
  },
  "players": [
    {
      "user_id": 1,
      "name": "Sarah",
      "credits_owed": 50,
      "active": true,
      "cashed_out": false
    }
  ],
  "bank": {
    "cash_balance": 200,
    "chips_in_play": 500,
    "total_credits_issued": 100,
    "outstanding_credits": 75
  },
  "pending_transactions": 2
}
```

---

### Feature 9: Player Summary and Transaction History

**Purpose**: Give players detailed view of their financial activity in the game.

**How It Works:**
- Player views their profile in game
- System calculates total buy-ins and cashouts
- Shows current credit owed
- Lists all transactions chronologically

**Technical Details:**
- Endpoint: `GET /api/games/<id>/players/<user_id>/summary`
- Aggregates from Transactions collection
- Calculates:
  - `total_cash_buyins` = sum of approved cash buy-ins
  - `total_credit_buyins` = sum of approved credit buy-ins
  - `total_cashouts` = sum of approved cashouts
  - `current_credits_owed` = from Player document

**User Experience:**
```
Sarah's Summary:
├─ Total Cash Buy-Ins: $100
├─ Total Credit Buy-Ins: $50
├─ Total Cashouts: $75
├─ Currently Owes: $25
└─ Net Position: -$50 (brought $100, took $75, owes $25)
```

---

### Feature 10: Bank Monitoring and Validation

**Purpose**: Ensure bank integrity and prevent impossible transactions.

**How It Works:**
- Bank validates all operations before execution
- Prevents negative cash balance
- Tracks all inflows and outflows
- Maintains invariants

**Technical Details:**
- Validation in Bank model:
  ```python
  def validate_cashout(self, chips_returned, cash_requested, credits_to_repay):
      if cash_requested > self.cash_balance:
          return False, "Insufficient cash in bank"
      if chips_returned <= 0:
          return False, "Must return chips to cashout"
      return True, "Valid"
  ```

**Critical Invariants:**
1. `cash_balance >= 0` (always)
2. `chips_in_play = total_chips_issued - total_chips_returned`
3. `total_cash_in - total_cash_out = cash_balance`
4. `outstanding_credits = total_credits_issued - total_credits_repaid`

**Endpoint:**
- `GET /api/games/<id>/bank` - Get bank status

---

### Feature 11: Host-Initiated Buy-Ins and Cashouts

**Purpose**: Allow host to create transactions on behalf of players (e.g., for cash games where host handles physical cash).

**How It Works:**
1. Host selects player
2. Host creates buy-in or cashout for that player
3. Transaction is pre-approved (host initiated)
4. Bank operations execute immediately

**Technical Details:**
- Endpoint: `POST /api/games/<id>/host-buyin`
- Endpoint: `POST /api/games/<id>/host-cashout`
- Bypasses approval workflow
- Creates transaction with `confirmed=true`
- Executes bank operations immediately

**Use Case:**
```
Physical cash game:
├─ Player hands $100 cash to host
├─ Host enters: "Sarah - Cash Buy-In - $100"
├─ Transaction approved automatically
└─ Sarah gets 100 chips
```

---

### Feature 12: Two-Phase Settlement System

**Purpose**: Handle end-game settlements in an organized, fair manner when players have outstanding credits.

**Overview:**
Traditional poker games struggle with settlements when:
- Some players left early and owe money
- Remaining players need to be paid
- Credits need to be transferred or written off

ChipMate uses a two-phase settlement:
1. **Phase 1 - Credit Settlement**: Players repay credits owed
2. **Phase 2 - Final Cashout**: Remaining players cash out with option to claim unpaid credits

**Technical Details:**
- Triggered by: `POST /api/games/<id>/settlement/start`
- Game status changes: `active` → `ending`
- Settlement phase: `null` → `credit_settlement`

---

### Feature 13: Phase 1 - Credit Settlement

**Purpose**: Allow players to repay their outstanding credits before final cashout.

**How It Works:**
1. Host starts settlement
2. System creates `UnpaidCredit` records for all players with `credits_owed > 0`
3. Players can make partial or full credit repayments
4. Each repayment updates player's `credits_owed`

**Technical Details:**
- Endpoint: `POST /api/games/<id>/settlement/repay-credit`
- Creates UnpaidCredit documents:
  ```javascript
  UnpaidCredit {
    game_id: string,
    debtor_user_id: int,
    debtor_name: string,
    amount: int (total owed),
    amount_available: int (not yet claimed),
    created_at: datetime
  }
  ```
- On repayment:
  - `player.credits_owed -= amount`
  - `bank.total_credits_repaid += amount`
  - `bank.chips_in_play -= amount`

**User Experience:**
```
Settlement Phase 1:
├─ Players with Credits Owed:
│  ├─ Mike owes: $50
│  └─ Lisa owes: $75
├─ Mike repays: $30
├─ Updated: Mike owes $20
└─ Complete Phase 1 when ready
```

---

### Feature 14: Phase 2 - Final Cashout with Unpaid Credit Claims

**Purpose**: Allow remaining players to cash out and optionally claim unpaid credits from players who didn't repay.

**How It Works:**
1. Phase 1 completes
2. Settlement phase changes to `final_cashout`
3. Players request final cashout
4. Players can choose to claim unpaid credits
5. System transfers credit responsibility

**Technical Details:**
- Endpoint: `POST /api/games/<id>/settlement/final-cashout`
- Request format:
  ```json
  {
    "chips": 400,
    "credits_repayment": 50,
    "cash_requested": 200,
    "unpaid_credits_claimed": [
      {"debtor_user_id": 3, "amount": 150}
    ]
  }
  ```
- Creates `UnpaidCreditClaim`:
  ```javascript
  UnpaidCreditClaim {
    game_id: string,
    creditor_user_id: int,
    debtor_user_id: int,
    amount: int,
    created_at: datetime
  }
  ```

**Example:**
```
Final Cashout:
├─ Sarah has 400 chips
├─ Sarah owes 50 credits
├─ Calculation:
│  ├─ Repay own credits: 50
│  ├─ Remaining: 350 chips
│  ├─ Bank has: 200 cash
│  └─ Unpaid credit available: Mike owes 150
├─ Sarah chooses:
│  ├─ Take: $200 cash
│  └─ Claim: Mike's $150 debt
└─ Result: Sarah receives $200 cash + Mike owes her $150
```

**Credit Transfer:**
- Before: Mike owes $150 to bank
- After: Mike owes $150 to Sarah
- Bank no longer tracks Mike's debt

---

### Feature 15: Game Status Lifecycle

**Purpose**: Track games through their lifecycle from creation to completion.

**States:**

1. **active** - Game in progress
   - Players can join
   - Buy-ins and cashouts allowed
   - Normal gameplay

2. **ending** - Settlement in progress
   - No new players
   - Settlement phases active
   - Limited transactions

3. **settled** - Settlement complete
   - All credits resolved
   - Final summaries available
   - Read-only state

4. **expired** - Game timeout/abandoned
   - No activity for extended period
   - Can be cleaned up

**Technical Details:**
- State transitions:
  ```
  active → ending (host starts settlement)
  ending → settled (phase 2 complete)
  active → expired (timeout)
  ```

**Settlement Phases (when status=ending):**
```
null → credit_settlement (Phase 1)
credit_settlement → final_cashout (Phase 2)
final_cashout → completed (Done)
```

---

### Feature 16: Admin Dashboard

**Purpose**: Provide administrative oversight of all games and system statistics.

**How It Works:**
- Admin logs in with credentials
- Views all games across system
- Can destroy/cleanup games
- Sees aggregate statistics

**Technical Details:**
- Endpoint: `POST /api/auth/login` (with username/password)
- Endpoint: `GET /api/admin/games` - List all games
- Endpoint: `GET /api/admin/stats` - System statistics
- Endpoint: `DELETE /api/admin/games/<id>/destroy` - Remove game

**Admin Stats:**
```json
{
  "total_games": 47,
  "active_games": 12,
  "total_players": 234,
  "total_cash_in_system": 15600,
  "total_credits_owed": 2300,
  "games_today": 5
}
```

**Admin Capabilities:**
- View all game details
- Monitor bank balances
- Destroy abandoned games
- View player transaction history
- Audit trail access

---

### Feature 17: Game Report Generation

**Purpose**: Provide comprehensive game summary for record-keeping and analysis.

**How It Works:**
- Host requests game report
- System aggregates all game data
- Generates detailed financial summary
- Includes all players, transactions, and final state

**Technical Details:**
- Endpoint: `GET /api/games/<id>/report`
- Returns:
  - Game metadata
  - All players with final positions
  - All transactions (chronological)
  - Bank final state
  - Settlement details
  - Credit claims

**Report Structure:**
```json
{
  "game_info": {
    "code": "ABC123",
    "host": "John",
    "created": "2024-01-15T10:00:00Z",
    "ended": "2024-01-15T14:30:00Z",
    "duration_hours": 4.5
  },
  "players": [
    {
      "name": "Sarah",
      "total_buyins": 150,
      "total_cashouts": 200,
      "final_credits_owed": 0,
      "net_profit": 50
    }
  ],
  "bank_summary": {
    "total_cash_in": 500,
    "total_cash_out": 450,
    "final_cash_balance": 50,
    "total_credits_issued": 200,
    "total_credits_repaid": 175,
    "outstanding_credits": 25
  },
  "transactions": [...]
}
```

---

### Feature 18: Credit Tracking and Outstanding Debts

**Purpose**: Maintain accurate records of all credits owed in the system.

**How It Works:**
- Each player has `credits_owed` field
- Updated on credit buy-ins and credit repayments
- Visible to host and player
- Tracked through settlement

**Technical Details:**
- Endpoint: `GET /api/games/<id>/credits` - List all credits
- Returns players with `credits_owed > 0`
- Shows total outstanding credits
- Links to settlement workflow

**Response:**
```json
{
  "players_with_credits": [
    {
      "user_id": 2,
      "name": "Mike",
      "credits_owed": 50
    }
  ],
  "total_outstanding": 50,
  "settlement_phase": "credit_settlement"
}
```

---

### Feature 19: Responsive Mobile Interface

**Purpose**: Provide full functionality on mobile devices for players and hosts.

**How It Works:**
- Angular app is fully responsive
- Bootstrap grid system adapts to screen sizes
- Touch-optimized controls
- QR code scanning via mobile camera

**Technical Details:**
- Bootstrap breakpoints:
  - xs: < 576px (phones)
  - sm: ≥ 576px (phones landscape)
  - md: ≥ 768px (tablets)
  - lg: ≥ 992px (desktops)
- Mobile-first CSS
- Touch event handling
- Camera API for QR scanning

**Mobile Features:**
- Simplified navigation
- Large touch targets
- Swipe gestures
- Offline-ready (with limitations)

---

### Feature 20: CORS and Multi-Origin Support

**Purpose**: Enable frontend and backend to be hosted separately while maintaining security.

**How It Works:**
- Flask CORS middleware configured
- Whitelisted origins for Railway deployment
- Preflight request handling
- Credential support

**Technical Details:**
```python
# Development Configuration
CORS(app, origins=["http://localhost:4200", "*"])

# Production Configuration (recommended)
CORS(app, origins=["https://chipmate.up.railway.app"])
```

**Security Considerations:**
- Production: **MUST** use specific origins only - never use wildcard "*"
- Development: Wildcard allowed for local testing only
- ⚠️ **WARNING**: Never deploy with wildcard CORS - this is a security vulnerability
- Credentials: Cookies/headers supported
- Methods: GET, POST, DELETE allowed

---

### Feature 21: Error Handling and Validation

**Purpose**: Provide clear error messages and prevent invalid operations.

**How It Works:**
- Pydantic model validation
- HTTP status codes
- User-friendly error messages
- Logging for debugging

**Technical Details:**
- Validation errors: 400 Bad Request
- Not found: 404 Not Found
- Auth failures: 401 Unauthorized
- Server errors: 500 Internal Server Error

**Example Errors:**
```json
{
  "error": "Game code not found",
  "code": "GAME_NOT_FOUND"
}

{
  "error": "Insufficient cash in bank",
  "details": {
    "requested": 200,
    "available": 150
  }
}
```

---

### Feature 22: Transaction History and Audit Trail

**Purpose**: Maintain complete history of all financial operations for transparency and dispute resolution.

**How It Works:**
- Every transaction stored permanently
- Timestamps on all operations
- Approval/rejection tracking
- Never deleted, only marked

**Technical Details:**
- All transactions have `at` timestamp
- `confirmed` and `rejected` flags
- Transaction types clearly labeled
- Immutable after creation

**Audit Capabilities:**
- Who created transaction
- When created
- When approved/rejected
- By whom (host)
- Final state

---

### Feature 23: Bank Consistency Validation

**Purpose**: Ensure mathematical consistency of bank operations at all times.

**How It Works:**
- Automatic validation on every operation
- Consistency checks:
  - `chips_in_play = total_chips_issued - total_chips_returned`
  - `cash_balance = total_cash_in - total_cash_out`
  - `outstanding_credits = total_credits_issued - total_credits_repaid`

**Technical Details:**
- Validation in Bank model
- Assertions in tests
- Runtime checks in production
- Alerts on inconsistency

---

### Feature 24: Player Status Tracking

**Purpose**: Track player state throughout game lifecycle.

**States:**
- **active** - In game, can transact
- **quit** - Left game early
- **cashed_out** - Completed final cashout
- **inactive** - No longer participating

**Technical Details:**
```javascript
Player {
  active: bool,
  quit: bool,
  cashed_out: bool,
  cashout_time: datetime | null
}
```

**State Transitions:**
```
active → quit (player leaves)
active → cashed_out (final cashout)
cashed_out → inactive (settlement complete)
```

---

### Feature 25: Environment Configuration

**Purpose**: Support different configurations for development, testing, and production.

**How It Works:**
- Environment variables for sensitive config
- Different settings per environment
- Defaults for development

**Configuration:**

**Backend:**
```bash
MONGO_URL=mongodb://localhost:27017/  # Database connection
```

**Frontend:**
```typescript
environment = {
  production: false,
  apiUrl: 'http://localhost:5000/api',
  appUrl: 'http://localhost:4200'
}
```

**Deployment (Railway):**
- `Procfile` for process management
- `runtime.txt` for Python version
- `nixpacks.toml` for build configuration

---

### Feature 26: Settlement Status Monitoring

**Purpose**: Track progress through settlement phases and provide visibility.

**How It Works:**
- Endpoint provides current settlement state
- Shows which phase is active
- Lists players who completed each phase
- Indicates when ready to progress

**Technical Details:**
- Endpoint: `GET /api/games/<id>/settlement/status`
- Returns:
  ```json
  {
    "game_status": "ending",
    "settlement_phase": "credit_settlement",
    "players_with_credits": [...],
    "players_completed_repayment": [...],
    "can_proceed_to_phase2": true
  }
  ```

---

### Feature 27: Unpaid Credit Claim System

**Purpose**: Enable players to claim unpaid credits from other players during final settlement.

**How It Works:**
- When player doesn't repay credits, debt becomes "unpaid credit"
- Other players can claim these during final cashout
- Credit responsibility transfers from bank to claiming player
- Claiming player becomes new creditor

**Technical Details:**
- UnpaidCredit document tracks available credits
- UnpaidCreditClaim records who claimed from whom
- Amount deducted from `amount_available`
- Both creditor and debtor notified

**Database:**
```javascript
UnpaidCreditClaim {
  game_id: string,
  creditor_user_id: int,    // Who is owed the money
  debtor_user_id: int,      // Who owes the money
  amount: int,
  created_at: datetime
}
```

---

### Feature 28: Buy-In Summary for Players

**Purpose**: Show players detailed breakdown of their buy-in history.

**How It Works:**
- Lists all buy-in transactions
- Separates cash vs credit
- Shows approval status
- Calculates totals

**Technical Details:**
- Endpoint: `GET /api/games/<id>/players/<user_id>/buyin-summary`
- Filters transactions by type: `buyin_cash`, `buyin_register`
- Returns chronological list with amounts
- Includes pending buy-ins

---

### Feature 29: Former Host Cashout Handling

**Purpose**: Handle special case when original host cashes out and transfers host role.

**How It Works:**
- Host can cash out during game
- System marks cashout as `former_host_cashout`
- Host role transfers to another player
- Former host remains in game but without host privileges

**Technical Details:**
- Flag: `transaction.former_host_cashout = true`
- Host transfer logic in game service
- Former host treated as regular player after transfer

---

### Feature 30: Production Server with Gunicorn

**Purpose**: Serve application in production with proper WSGI server.

**How It Works:**
- Development: Flask development server
- Production: Gunicorn WSGI server
- Multiple worker processes
- Better performance and stability

**Technical Details:**
```python
# production_server.py
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

**Procfile:**
```
web: gunicorn src.api.production_server:app
```

**Workers:**
- Calculated based on CPU cores
- Handles concurrent requests
- Process management

---

## API Endpoints Reference

### Authentication
- `POST /api/auth/login` - Login (player or admin)

### Games
- `POST /api/games` - Create new game
- `POST /api/games/join` - Join existing game
- `GET /api/games/<id>` - Get game details
- `GET /api/games/<id>/status` - Get game status
- `GET /api/games/<id>/players` - List all players
- `GET /api/games/<id>/bank` - Get bank status
- `POST /api/games/<id>/end` - End game (deprecated, use settlement)
- `GET /api/games/<code>/link` - Get join link and QR code
- `GET /api/games/<id>/report` - Get game report

### Transactions
- `POST /api/transactions/buyin` - Create buy-in transaction
- `POST /api/transactions/cashout` - Create cashout transaction
- `GET /api/games/<id>/transactions/pending` - Get pending transactions
- `POST /api/transactions/<id>/approve` - Approve transaction
- `POST /api/transactions/<id>/reject` - Reject transaction
- `POST /api/transactions/<id>/resolve` - Resolve transaction

### Players
- `GET /api/games/<id>/players/<user_id>/summary` - Get player summary
- `GET /api/games/<id>/players/<user_id>/buyin-summary` - Get buy-in summary

### Credits
- `GET /api/games/<id>/credits` - Get all outstanding credits
- `GET /api/games/<id>/settlement` - Get settlement data

### Host Operations
- `POST /api/games/<id>/host-buyin` - Host creates buy-in for player
- `POST /api/games/<id>/host-cashout` - Host creates cashout for player

### Settlement
- `POST /api/games/<id>/settlement/start` - Start settlement process
- `GET /api/games/<id>/settlement/status` - Get settlement status
- `POST /api/games/<id>/settlement/repay-credit` - Repay credit (Phase 1)
- `POST /api/games/<id>/settlement/complete-phase1` - Complete Phase 1
- `POST /api/games/<id>/settlement/final-cashout` - Final cashout (Phase 2)

### Admin
- `GET /api/admin/games` - List all games
- `GET /api/admin/stats` - Get system statistics
- `DELETE /api/admin/games/<id>/destroy` - Destroy game

---

## Database Schema

### Collections

**games**
```javascript
{
  _id: ObjectId,
  host_id: int,              // Primary host identifier
  host_user_id: int,         // Alias for host_id (backwards compatibility)
  host_name: string,
  status: string,            // "active" | "ending" | "settled" | "expired"
  settlement_phase: string | null,  // null | "credit_settlement" | "final_cashout" | "completed"
  created_at: datetime,
  ended_at: datetime | null,
  players: [int],            // Array of user_ids in the game
  code: string               // 6-character game code
}
```

**Note**: `host_id` and `host_user_id` are kept in sync for backwards compatibility. New code should use `host_id`.

**players**
```javascript
{
  _id: ObjectId,
  game_id: string,
  user_id: int,
  name: string,
  credits_owed: int,
  final_chips: int | null,
  quit: bool,
  is_host: bool,
  active: bool,
  cashed_out: bool,
  cashout_time: datetime | null
}
```

**transactions**
```javascript
{
  _id: ObjectId,
  game_id: string,
  user_id: int,
  type: string,
  amount: int,
  confirmed: bool,
  rejected: bool,
  at: datetime,
  former_host_cashout: bool (optional)
}
```

**banks**
```javascript
{
  _id: ObjectId,
  game_id: string,
  cash_balance: int,
  total_cash_in: int,
  total_cash_out: int,
  total_credits_issued: int,
  total_credits_repaid: int,
  total_chips_issued: int,
  total_chips_returned: int,
  chips_in_play: int,
  created_at: datetime,
  updated_at: datetime
}
```

**unpaid_credits**
```javascript
{
  _id: ObjectId,
  game_id: string,
  debtor_user_id: int,
  debtor_name: string,
  amount: int,
  amount_available: int,
  created_at: datetime
}
```

**unpaid_credit_claims**
```javascript
{
  _id: ObjectId,
  game_id: string,
  creditor_user_id: int,
  debtor_user_id: int,
  amount: int,
  created_at: datetime
}
```

---

## Installation and Setup

### Prerequisites
- **Node.js 18+** and npm
- **Python 3.8+**
- **MongoDB** (local or remote)

### Backend Setup

```bash
# Clone repository
git clone https://github.com/Omricoh/ChipMate.git
cd ChipMate

# Install Python dependencies
pip install -r requirements.txt

# Set MongoDB URL (optional)
export MONGO_URL="mongodb://localhost:27017/"

# Start development server
python src/api/web_api.py

# Or start production server
gunicorn src.api.production_server:app
```

Backend runs on: `http://localhost:5000`

### Frontend Setup

```bash
# Navigate to web-ui
cd web-ui

# Install dependencies
npm install

# Start development server
npm start

# Or build for production
npm run build
```

Frontend runs on: `http://localhost:4200`

### MongoDB Setup

**Local:**
```bash
# Install MongoDB
# Start MongoDB
mongod

# Database will be created automatically
```

**Remote (MongoDB Atlas):**
```bash
export MONGO_URL="mongodb+srv://username:password@cluster.mongodb.net/"
```

---

## Development Workflow

### Running in Development

**Terminal 1 - MongoDB:**
```bash
mongod
```

**Terminal 2 - Backend:**
```bash
cd ChipMate
python src/api/web_api.py
```

**Terminal 3 - Frontend:**
```bash
cd ChipMate/web-ui
npm start
```

### Testing

**Backend Tests:**
```bash
# Run all tests
pytest

# Run specific test
pytest test_settlement_flow.py

# Run with coverage
pytest --cov=src
```

**Frontend Tests:**
```bash
cd web-ui
npm test
```

### Building for Production

```bash
# Build frontend
cd web-ui
npm run build

# Output: web-ui/dist/chipmate-web/

# Backend uses Gunicorn (see Procfile)
```

---

## Deployment

### Railway Deployment

**Configuration Files:**
- `Procfile` - Defines web process
- `runtime.txt` - Python version
- `nixpacks.toml` - Build configuration
- `railway.json` - Railway-specific settings

**Environment Variables:**
```bash
MONGO_URL=<your-mongodb-connection-string>
```

**Build Command:**
```bash
npm run build && pip install -r requirements.txt
```

**Start Command:**
```bash
gunicorn src.api.production_server:app
```

---

## Architecture Deep Dive

### Three-Layer Architecture

**1. Data Access Layer (DAL)**
- Direct database operations
- CRUD operations
- No business logic
- Files: `src/dal/*.py`

**2. Business Logic Layer (BL)**
- Game rules
- Validation
- Calculations
- Files: `src/bl/*.py`

**3. Service Layer**
- Orchestrates BL and DAL
- Transaction management
- External API interface
- Files: `src/services/*.py`

### Data Flow Example: Buy-In Transaction

```
1. Player clicks "Buy In" (Frontend)
   ├─ Angular component
   └─ Calls API service

2. HTTP Request (API)
   ├─ POST /api/transactions/buyin
   └─ Flask route handler

3. Service Layer
   ├─ TransactionService.create_buyin_transaction()
   ├─ Validates game exists
   └─ Creates transaction

4. Business Logic Layer
   ├─ transaction_bl.create_buyin()
   └─ Builds Transaction model

5. Data Access Layer
   ├─ TransactionsDAL.create()
   └─ Inserts to MongoDB

6. Approval Flow
   ├─ Host approves
   ├─ TransactionService.approve_transaction()
   ├─ BankDAL.record_cash_buyin()
   └─ Updates bank and player

7. Response
   ├─ Success/error returned
   ├─ JSON response
   └─ Frontend updates UI
```

### Bank System Design

**Central Bank Entity:**
- Single source of truth for game finances
- All money flows through bank
- Prevents inconsistencies

**Key Principles:**
1. **Host Approval Required** - No automatic money movement
2. **Credit Tracking** - Per-player credits_owed field
3. **Cash Conservation** - Bank balance can't go negative
4. **Chip Accounting** - chips_in_play always matches issued - returned

**Money Flow Diagram:**
```
Player ──cash──> Bank ──chips──> Player
Player <─chips── Bank <─cash──── Player (if available)
Player <─chips── Bank           Player.credits_owed++ (if no cash)
```

---

## Testing and Validation

### Test Coverage

**Backend Tests:**
- `test_settlement_flow.py` - Settlement phases
- `test_settlement_simple.py` - Basic settlement
- `test_settlement_chips_in_play_verification.py` - Bank consistency

**Test Scenarios:**
- Multiple players with different buy-in types
- Sequential cashouts
- Credit repayment calculations
- Bank balance validation
- Settlement phase transitions

### Running Verification

```bash
# Run settlement verification
python test_settlement_chips_in_play_verification.py

# View visual verification
open visual_verification.html
```

---

## Security Considerations

### Authentication
- Admin credentials for admin access
- User session management
- Game code as authorization

### Data Validation
- Pydantic models validate all input
- Type checking
- Range validation

### Financial Integrity
- Bank validation prevents negative balances
- Transactions require host approval
- Immutable transaction history

### CORS Policy
- Whitelisted origins in production
- Credentials support
- Secure headers

---

## Troubleshooting

### Common Issues

**1. MongoDB Connection Failed**
```
Error: Cannot connect to MongoDB
Solution: Ensure MongoDB is running and MONGO_URL is correct
```

**2. CORS Errors**
```
Error: CORS policy blocked
Solution: Check Flask CORS configuration includes your frontend URL
```

**3. Port Already in Use**
```
Error: Port 5000 already in use
Solution: Kill process or use different port
```

**4. QR Code Generation Failed**
```
Error: Cannot generate QR code
Solution: Install qrcode and pillow packages
```

### Debug Mode

**Backend:**
```python
# In web_api.py
app.run(debug=True)  # Enables debug mode
```

**Frontend:**
```bash
ng serve --verbose  # Verbose output
```

### Logging

```python
# Backend logging
import logging
logger = logging.getLogger("chipbot")
logger.setLevel(logging.DEBUG)
```

---

## Future Enhancements

Potential features for future development:

1. **Multi-Currency Support** - Handle games with different currencies
2. **Game Templates** - Pre-configured game types (tournament, cash game)
3. **Player Statistics** - Long-term player tracking across games
4. **Push Notifications** - Real-time alerts for transactions
5. **Payment Integration** - Venmo, PayPal integration for settlements
6. **Advanced Analytics** - Game statistics and insights
7. **Mobile Apps** - Native iOS/Android applications
8. **Multi-Game Support** - Players in multiple simultaneous games
9. **Tournament Mode** - Structured tournament with blinds and levels
10. **Export Features** - Export game data to CSV/PDF

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style
- **Python**: PEP 8
- **TypeScript**: Angular style guide
- **Commits**: Conventional commits format

---

## License

This project is licensed under the MIT License.

---

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub: https://github.com/Omricoh/ChipMate/issues
- Check existing documentation in the repository

---

## Acknowledgments

Built with modern web technologies and best practices in software architecture.

**Key Technologies:**
- Angular Team - Frontend framework
- Flask Team - Backend framework
- MongoDB - Database
- Bootstrap - UI framework

---

**ChipMate** - Making poker game management simple, transparent, and fair.
