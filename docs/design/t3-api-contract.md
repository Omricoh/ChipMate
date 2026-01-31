# T3: ChipMate v2 REST API Contract and System Architecture

**Document Version:** 1.0
**Date:** 2026-01-30
**Author:** Tech Lead Architect
**Status:** Draft for Review

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [API Endpoint Reference](#api-endpoint-reference)
3. [Request/Response Schemas](#requestresponse-schemas)
4. [Error Response Format](#error-response-format)
5. [Authentication Flows](#authentication-flows)
6. [System Architecture](#system-architecture)
7. [Middleware Stack](#middleware-stack)
8. [CORS Configuration](#cors-configuration)
9. [Endpoint-to-User-Story Mapping](#endpoint-to-user-story-mapping)
10. [Migration from V1](#migration-from-v1)

---

## Executive Summary

This document defines the complete REST API contract for ChipMate v2, a mobile-first poker game management web application. The system enables game managers to run live poker sessions where players join without registration, request chips (cash or credit), and managers approve/decline/edit requests. At game end, managers process checkouts and resolve credit debts.

**Key Design Principles:**

- **Mobile-First:** All endpoints optimized for mobile network conditions (small payloads, efficient polling)
- **Role-Based Access:** Three distinct roles with clear authorization boundaries
- **State Machine Clarity:** Explicit game and request state transitions with validation
- **Idempotency:** Critical operations (approve, checkout) are idempotent
- **Graceful Degradation:** Polling-based notifications with fallback support

**Technology Stack:**

- Backend: Python 3.10+ / FastAPI 0.100+
- Database: MongoDB 7+ with Motor (async driver)
- Auth: JWT (admin) + UUID tokens (players)
- API Style: RESTful with conventional HTTP verbs
- Documentation: Auto-generated OpenAPI 3.1 via FastAPI

**Scope:**

- 35 REST endpoints across 8 functional domains
- Comprehensive error taxonomy (24 error codes)
- Three authentication flows
- Five-layer architecture (Routes → Middleware → Services → DAL → MongoDB)

---

## API Endpoint Reference

### Endpoint Summary Table

| Group | Endpoint | Method | Auth | Roles | Description |
|-------|----------|--------|------|-------|-------------|
| **Auth** | `/api/v2/auth/admin/login` | POST | None | - | Admin JWT login |
| | `/api/v2/auth/validate` | GET | Token | All | Validate token and return user context |
| **Games** | `/api/v2/games` | POST | Token | Player | Create new game (creator becomes manager) |
| | `/api/v2/games/{game_id}` | GET | Token | All | Get game details by ID |
| | `/api/v2/games/code/{code}` | GET | None | - | Get game by join code (public) |
| | `/api/v2/games/{game_id}/status` | GET | Token | All | Get comprehensive game status/summary |
| | `/api/v2/games/{game_id}/qr` | GET | Token | Manager | Generate QR code for game join |
| | `/api/v2/games/{game_id}/close` | POST | Token | Manager,Admin | Close game (SETTLING → CLOSED) |
| **Players** | `/api/v2/games/{game_id}/players/join` | POST | None | - | Join game and receive player token |
| | `/api/v2/games/{game_id}/players/me` | GET | Token | Player,Manager | Get current player info |
| | `/api/v2/games/{game_id}/players` | GET | Token | Manager,Admin | List all players in game |
| | `/api/v2/games/{game_id}/players/{player_id}` | GET | Token | Manager,Admin | Get specific player details |
| | `/api/v2/games/{game_id}/players/me/leave` | POST | Token | Player | Leave game (soft delete) |
| **Chip Requests** | `/api/v2/games/{game_id}/chip-requests` | POST | Token | Player,Manager | Create chip request (supports on-behalf-of) |
| | `/api/v2/games/{game_id}/chip-requests/pending` | GET | Token | Manager,Admin | Get all pending requests |
| | `/api/v2/games/{game_id}/chip-requests/history` | GET | Token | Player,Manager,Admin | Get request history (filtered by role) |
| | `/api/v2/games/{game_id}/chip-requests/{request_id}` | GET | Token | Player,Manager,Admin | Get request details |
| | `/api/v2/games/{game_id}/chip-requests/{request_id}/approve` | POST | Token | Manager,Admin | Approve request (idempotent) |
| | `/api/v2/games/{game_id}/chip-requests/{request_id}/decline` | POST | Token | Manager,Admin | Decline request (idempotent) |
| | `/api/v2/games/{game_id}/chip-requests/{request_id}/edit-approve` | POST | Token | Manager,Admin | Edit amount and approve atomically |
| **Notifications** | `/api/v2/games/{game_id}/notifications` | GET | Token | Player,Manager | Get unread notifications (poll endpoint) |
| | `/api/v2/games/{game_id}/notifications/{notification_id}/read` | POST | Token | Player,Manager | Mark notification as read |
| | `/api/v2/games/{game_id}/notifications/read-all` | POST | Token | Player,Manager | Mark all notifications as read |
| **Checkout** | `/api/v2/games/{game_id}/checkout/player/{player_id}` | POST | Token | Manager,Admin | Checkout single player |
| | `/api/v2/games/{game_id}/checkout/whole-table` | POST | Token | Manager,Admin | Start whole-table checkout sequence |
| | `/api/v2/games/{game_id}/checkout/order` | GET | Token | Manager,Admin | Get checkout order (credit-debt first) |
| | `/api/v2/games/{game_id}/checkout/next` | POST | Token | Manager,Admin | Process next player in queue |
| **Settlement** | `/api/v2/games/{game_id}/settlement/summary` | GET | Token | Manager,Admin | Get settlement summary (who owes whom) |
| | `/api/v2/games/{game_id}/settlement/players/{player_id}/settle` | POST | Token | Manager,Admin | Mark player debt as settled |
| | `/api/v2/games/{game_id}/settlement/finalize` | POST | Token | Manager,Admin | Finalize settlement and transition to CLOSED |
| | `/api/v2/games/{game_id}/settlement/report` | GET | Token | Manager,Admin | Get final game report (CSV export) |
| **Admin** | `/api/v2/admin/games` | GET | JWT | Admin | List all games (with filters) |
| | `/api/v2/admin/games/{game_id}` | GET | JWT | Admin | Get any game (bypass ownership) |
| | `/api/v2/admin/games/{game_id}/force-close` | POST | JWT | Admin | Force close game (emergency) |
| | `/api/v2/admin/games/{game_id}/impersonate` | POST | JWT | Admin | Generate manager token for game |
| | `/api/v2/admin/games/{game_id}` | DELETE | JWT | Admin | Delete game and all data |
| | `/api/v2/admin/stats` | GET | JWT | Admin | System-wide statistics |
| **Health** | `/api/v2/health` | GET | None | - | Health check endpoint |

**Total Endpoints:** 37

---

## Request/Response Schemas

All schemas follow Pydantic v2 conventions. Required fields are marked with `*`. Timestamps are ISO 8601 strings.

### Common Types

```python
# Enums
GameStatus = Literal["OPEN", "SETTLING", "CLOSED"]
ChipRequestType = Literal["CASH", "CREDIT"]
ChipRequestStatus = Literal["PENDING", "APPROVED", "DECLINED", "EDITED"]
NotificationType = Literal[
    "REQUEST_CREATED", "REQUEST_APPROVED", "REQUEST_DECLINED",
    "REQUEST_EDITED", "CHECKOUT_READY", "GAME_CLOSING"
]

# Common embedded objects
class PlayerSummary(BaseModel):
    player_id: str  # UUID
    name: str
    is_manager: bool
    total_chips: int  # Current chip balance
    total_cash_in: int
    total_credit_in: int
    credits_owed: int

class ChipRequestSummary(BaseModel):
    request_id: str  # UUID
    player_id: str
    player_name: str
    type: ChipRequestType
    amount: int
    status: ChipRequestStatus
    created_at: str  # ISO 8601
    processed_at: str | None
    processed_by: str | None  # player_id of manager
```

---

### Auth Endpoints

#### `POST /api/v2/auth/admin/login`

**Description:** Authenticate admin user and receive JWT token.

**Request:**
```json
{
  "username": "string*",
  "password": "string*"
}
```

**Response 200:**
```json
{
  "access_token": "string",
  "token_type": "Bearer",
  "user": {
    "user_id": "admin",
    "role": "ADMIN",
    "username": "string"
  }
}
```

**Errors:** 401 (INVALID_CREDENTIALS)

---

#### `GET /api/v2/auth/validate`

**Description:** Validate token and return user context. Used on app startup.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "valid": true,
  "user": {
    "user_id": "string",  // UUID for player, "admin" for admin
    "role": "ADMIN" | "MANAGER" | "PLAYER",
    "player_id": "string | null",  // UUID if player/manager
    "game_id": "string | null",
    "game_code": "string | null",
    "is_manager": "boolean | null"
  }
}
```

**Errors:** 401 (INVALID_TOKEN, EXPIRED_TOKEN)

---

### Game Endpoints

#### `POST /api/v2/games`

**Description:** Create new game. Creator automatically becomes manager and receives player token with is_manager=true.

**Headers:** `Authorization: Bearer <token>` (optional - can create anonymous or authenticated)

**Request:**
```json
{
  "manager_name": "string*",  // 2-50 chars
  "max_players": "integer | null"  // Default 50, max 100
}
```

**Response 201:**
```json
{
  "game_id": "string",  // MongoDB ObjectId
  "game_code": "string",  // 6-char uppercase (e.g., "ABCD12")
  "manager_player_id": "string",  // UUID
  "player_token": "string",  // JWT with player_id + is_manager=true
  "created_at": "string"
}
```

**Errors:** 400 (INVALID_INPUT), 429 (RATE_LIMIT_EXCEEDED)

---

#### `GET /api/v2/games/{game_id}`

**Description:** Get game basic details.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "game_id": "string",
  "game_code": "string",
  "status": "GameStatus",
  "manager_name": "string",
  "manager_player_id": "string",
  "created_at": "string",
  "closed_at": "string | null",
  "player_count": "integer"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (UNAUTHORIZED)

---

#### `GET /api/v2/games/code/{code}`

**Description:** Get game by join code. Public endpoint (no auth).

**Response 200:**
```json
{
  "game_id": "string",
  "game_code": "string",
  "status": "GameStatus",
  "manager_name": "string",
  "player_count": "integer",
  "can_join": "boolean"  // false if SETTLING or CLOSED
}
```

**Errors:** 404 (GAME_NOT_FOUND)

---

#### `GET /api/v2/games/{game_id}/status`

**Description:** Comprehensive game status with financial summary.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "game": {
    "game_id": "string",
    "game_code": "string",
    "status": "GameStatus",
    "manager_name": "string",
    "created_at": "string"
  },
  "players": {
    "total": "integer",
    "active": "integer",
    "checked_out": "integer"
  },
  "chips": {
    "total_cash_in": "integer",
    "total_credit_in": "integer",
    "total_in_play": "integer",
    "total_checked_out": "integer"
  },
  "pending_requests": "integer",
  "credits_outstanding": "integer"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 403 (FORBIDDEN)

---

#### `GET /api/v2/games/{game_id}/qr`

**Description:** Generate QR code for game join link.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Query Params:**
- `size`: integer (default 256, max 512) - QR code size in pixels

**Response 200:**
```json
{
  "join_url": "string",  // e.g., https://app.chipmate.com/join/ABCD12
  "qr_code_data_url": "string"  // data:image/png;base64,...
}
```

**Errors:** 403 (FORBIDDEN), 404 (GAME_NOT_FOUND)

---

#### `POST /api/v2/games/{game_id}/close`

**Description:** Transition game from SETTLING to CLOSED. Validates all settlements complete.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "force": "boolean"  // Default false. If true, close even with outstanding credits.
}
```

**Response 200:**
```json
{
  "game_id": "string",
  "status": "CLOSED",
  "closed_at": "string",
  "final_summary": {
    "total_players": "integer",
    "total_chips_distributed": "integer",
    "outstanding_credits": "integer"
  }
}
```

**Errors:** 403 (FORBIDDEN), 409 (INVALID_STATE_TRANSITION), 400 (OUTSTANDING_CREDITS)

---

### Player Endpoints

#### `POST /api/v2/games/{game_id}/players/join`

**Description:** Join game and receive player token. No registration required.

**Request:**
```json
{
  "player_name": "string*"  // 2-50 chars
}
```

**Response 201:**
```json
{
  "player_id": "string",  // UUID
  "player_token": "string",  // JWT with player_id + game_id
  "game": {
    "game_id": "string",
    "game_code": "string",
    "manager_name": "string",
    "status": "GameStatus"
  }
}
```

**Errors:** 404 (GAME_NOT_FOUND), 409 (GAME_NOT_JOINABLE), 400 (DUPLICATE_NAME), 429 (RATE_LIMIT_EXCEEDED)

---

#### `GET /api/v2/games/{game_id}/players/me`

**Description:** Get current player's info and chip balance.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "player_id": "string",
  "name": "string",
  "is_manager": "boolean",
  "chips": {
    "current_balance": "integer",
    "total_cash_in": "integer",
    "total_credit_in": "integer",
    "credits_owed": "integer",
    "total_checked_out": "integer"
  },
  "status": {
    "is_active": "boolean",
    "checked_out": "boolean",
    "checked_out_at": "string | null"
  },
  "joined_at": "string"
}
```

**Errors:** 404 (PLAYER_NOT_FOUND), 401 (UNAUTHORIZED)

---

#### `GET /api/v2/games/{game_id}/players`

**Description:** List all players in game (manager/admin only).

**Headers:** `Authorization: Bearer <token>`

**Query Params:**
- `include_inactive`: boolean (default false) - Include players who left

**Response 200:**
```json
{
  "players": [
    {
      "player_id": "string",
      "name": "string",
      "is_manager": "boolean",
      "current_chips": "integer",
      "credits_owed": "integer",
      "is_active": "boolean",
      "checked_out": "boolean",
      "joined_at": "string"
    }
  ],
  "total_count": "integer"
}
```

**Errors:** 403 (FORBIDDEN), 404 (GAME_NOT_FOUND)

---

#### `GET /api/v2/games/{game_id}/players/{player_id}`

**Description:** Get specific player details (manager/admin only).

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "player_id": "string",
  "name": "string",
  "is_manager": "boolean",
  "chips": {
    "current_balance": "integer",
    "total_cash_in": "integer",
    "total_credit_in": "integer",
    "credits_owed": "integer"
  },
  "request_history": [
    "ChipRequestSummary"
  ],
  "joined_at": "string"
}
```

**Errors:** 403 (FORBIDDEN), 404 (PLAYER_NOT_FOUND)

---

#### `POST /api/v2/games/{game_id}/players/me/leave`

**Description:** Leave game (soft delete, player marked inactive).

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{
  "confirm": "boolean*"  // Must be true
}
```

**Response 200:**
```json
{
  "message": "Successfully left game",
  "player_id": "string",
  "left_at": "string"
}
```

**Errors:** 400 (INVALID_INPUT), 409 (CANNOT_LEAVE_WITH_CHIPS), 403 (MANAGER_CANNOT_LEAVE)

---

### Chip Request Endpoints

#### `POST /api/v2/games/{game_id}/chip-requests`

**Description:** Create chip request. Supports on-behalf-of for managers.

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{
  "type": "ChipRequestType*",
  "amount": "integer*",  // Must be > 0
  "on_behalf_of_player_id": "string | null",  // Manager only
  "note": "string | null"  // Max 500 chars
}
```

**Response 201:**
```json
{
  "request_id": "string",
  "type": "ChipRequestType",
  "amount": "integer",
  "status": "PENDING",
  "player_id": "string",
  "player_name": "string",
  "created_at": "string",
  "auto_approved": "boolean"  // true if manager created on-behalf-of
}
```

**Errors:** 400 (INVALID_AMOUNT), 403 (FORBIDDEN), 409 (GAME_NOT_OPEN)

---

#### `GET /api/v2/games/{game_id}/chip-requests/pending`

**Description:** Get all pending requests (manager/admin only).

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "requests": [
    {
      "request_id": "string",
      "player_id": "string",
      "player_name": "string",
      "type": "ChipRequestType",
      "amount": "integer",
      "status": "PENDING",
      "created_at": "string",
      "wait_time_seconds": "integer"
    }
  ],
  "total_count": "integer",
  "total_amount": {
    "cash": "integer",
    "credit": "integer"
  }
}
```

**Errors:** 403 (FORBIDDEN), 404 (GAME_NOT_FOUND)

---

#### `GET /api/v2/games/{game_id}/chip-requests/history`

**Description:** Get request history. Players see only their own, managers see all.

**Headers:** `Authorization: Bearer <token>`

**Query Params:**
- `player_id`: string (manager only) - Filter by player
- `status`: ChipRequestStatus (optional) - Filter by status
- `type`: ChipRequestType (optional) - Filter by type
- `limit`: integer (default 50, max 200)
- `offset`: integer (default 0)

**Response 200:**
```json
{
  "requests": [
    {
      "request_id": "string",
      "player_id": "string",
      "player_name": "string",
      "type": "ChipRequestType",
      "amount": "integer",
      "original_amount": "integer | null",  // If edited
      "status": "ChipRequestStatus",
      "created_at": "string",
      "processed_at": "string | null",
      "processed_by_name": "string | null",
      "note": "string | null"
    }
  ],
  "total_count": "integer",
  "pagination": {
    "limit": "integer",
    "offset": "integer",
    "has_more": "boolean"
  }
}
```

**Errors:** 401 (UNAUTHORIZED), 404 (GAME_NOT_FOUND)

---

#### `GET /api/v2/games/{game_id}/chip-requests/{request_id}`

**Description:** Get request details. Players can only view their own.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "request_id": "string",
  "game_id": "string",
  "player_id": "string",
  "player_name": "string",
  "type": "ChipRequestType",
  "amount": "integer",
  "original_amount": "integer | null",
  "status": "ChipRequestStatus",
  "created_at": "string",
  "processed_at": "string | null",
  "processed_by": {
    "player_id": "string",
    "name": "string"
  } | null,
  "note": "string | null"
}
```

**Errors:** 404 (REQUEST_NOT_FOUND), 403 (FORBIDDEN)

---

#### `POST /api/v2/games/{game_id}/chip-requests/{request_id}/approve`

**Description:** Approve chip request. Idempotent (repeated calls return success).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "note": "string | null"  // Optional approval note
}
```

**Response 200:**
```json
{
  "request_id": "string",
  "status": "APPROVED",
  "player": {
    "player_id": "string",
    "new_chip_balance": "integer",
    "new_credits_owed": "integer"
  },
  "processed_at": "string",
  "processed_by_name": "string"
}
```

**Errors:** 404 (REQUEST_NOT_FOUND), 403 (FORBIDDEN), 409 (ALREADY_PROCESSED)

---

#### `POST /api/v2/games/{game_id}/chip-requests/{request_id}/decline`

**Description:** Decline chip request. Idempotent.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "reason": "string | null"  // Optional decline reason
}
```

**Response 200:**
```json
{
  "request_id": "string",
  "status": "DECLINED",
  "processed_at": "string",
  "processed_by_name": "string"
}
```

**Errors:** 404 (REQUEST_NOT_FOUND), 403 (FORBIDDEN), 409 (ALREADY_PROCESSED)

---

#### `POST /api/v2/games/{game_id}/chip-requests/{request_id}/edit-approve`

**Description:** Edit request amount and approve atomically (prevents race conditions).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "new_amount": "integer*",  // Must be > 0
  "note": "string | null"
}
```

**Response 200:**
```json
{
  "request_id": "string",
  "status": "EDITED",
  "original_amount": "integer",
  "approved_amount": "integer",
  "player": {
    "player_id": "string",
    "new_chip_balance": "integer"
  },
  "processed_at": "string",
  "processed_by_name": "string"
}
```

**Errors:** 404 (REQUEST_NOT_FOUND), 403 (FORBIDDEN), 409 (ALREADY_PROCESSED), 400 (INVALID_AMOUNT)

---

### Notification Endpoints

#### `GET /api/v2/games/{game_id}/notifications`

**Description:** Get unread notifications. Poll every 3-5 seconds on active screens.

**Headers:** `Authorization: Bearer <token>`

**Query Params:**
- `since`: ISO 8601 timestamp (optional) - Only return notifications after this time

**Response 200:**
```json
{
  "notifications": [
    {
      "notification_id": "string",
      "type": "NotificationType",
      "message": "string",
      "data": {
        // Type-specific payload
        "request_id": "string | null",
        "amount": "integer | null",
        "player_name": "string | null"
      },
      "created_at": "string",
      "is_read": "boolean"
    }
  ],
  "unread_count": "integer",
  "server_time": "string"  // For client clock sync
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (UNAUTHORIZED)

---

#### `POST /api/v2/games/{game_id}/notifications/{notification_id}/read`

**Description:** Mark single notification as read.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "notification_id": "string",
  "is_read": true
}
```

**Errors:** 404 (NOTIFICATION_NOT_FOUND), 403 (FORBIDDEN)

---

#### `POST /api/v2/games/{game_id}/notifications/read-all`

**Description:** Mark all notifications as read.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "marked_count": "integer"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (UNAUTHORIZED)

---

### Checkout Endpoints

#### `POST /api/v2/games/{game_id}/checkout/player/{player_id}`

**Description:** Checkout single player. Calculates credit repayment automatically.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "chip_count": "integer*",  // Must match player's stated chip count
  "override_cash_amount": "integer | null",  // Manager override (e.g., bank shortage)
  "override_credit_amount": "integer | null"
}
```

**Response 200:**
```json
{
  "checkout_id": "string",
  "player_id": "string",
  "player_name": "string",
  "chip_count": "integer",
  "breakdown": {
    "credits_repaid": "integer",
    "remaining_credits": "integer",
    "cash_out": "integer",
    "chips_not_convertible": "integer"  // If bank cash insufficient
  },
  "checked_out_at": "string"
}
```

**Errors:** 404 (PLAYER_NOT_FOUND), 403 (FORBIDDEN), 409 (ALREADY_CHECKED_OUT), 400 (INVALID_CHIP_COUNT)

---

#### `POST /api/v2/games/{game_id}/checkout/whole-table`

**Description:** Start whole-table checkout. Transitions game to SETTLING and generates checkout order.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "force": "boolean"  // Default false. If true, start even with pending requests.
}
```

**Response 200:**
```json
{
  "game_id": "string",
  "status": "SETTLING",
  "checkout_order": [
    {
      "position": "integer",
      "player_id": "string",
      "player_name": "string",
      "priority": "CREDIT_DEBT" | "REGULAR",
      "credits_owed": "integer"
    }
  ],
  "started_at": "string"
}
```

**Errors:** 403 (FORBIDDEN), 409 (INVALID_STATE_TRANSITION), 400 (PENDING_REQUESTS_EXIST)

---

#### `GET /api/v2/games/{game_id}/checkout/order`

**Description:** Get checkout order. Credit-debt players first, then join order.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Response 200:**
```json
{
  "order": [
    {
      "position": "integer",
      "player_id": "string",
      "player_name": "string",
      "priority": "CREDIT_DEBT" | "REGULAR",
      "credits_owed": "integer",
      "checked_out": "boolean"
    }
  ],
  "progress": {
    "total_players": "integer",
    "checked_out": "integer",
    "remaining": "integer"
  }
}
```

**Errors:** 404 (GAME_NOT_FOUND), 403 (FORBIDDEN), 409 (GAME_NOT_SETTLING)

---

#### `POST /api/v2/games/{game_id}/checkout/next`

**Description:** Process next player in checkout queue (for streamlined flow).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "chip_count": "integer*",
  "override_cash_amount": "integer | null",
  "override_credit_amount": "integer | null"
}
```

**Response 200:**
```json
{
  "checkout_id": "string",
  "player": {
    "player_id": "string",
    "player_name": "string"
  },
  "breakdown": {
    "credits_repaid": "integer",
    "cash_out": "integer",
    "remaining_credits": "integer"
  },
  "next_player": {
    "player_id": "string",
    "player_name": "string",
    "priority": "string"
  } | null,
  "is_complete": "boolean"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 403 (FORBIDDEN), 409 (NO_MORE_PLAYERS)

---

### Settlement Endpoints

#### `GET /api/v2/games/{game_id}/settlement/summary`

**Description:** Get settlement summary (who owes whom, outstanding credits).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Response 200:**
```json
{
  "game_id": "string",
  "status": "GameStatus",
  "credits_outstanding": {
    "total": "integer",
    "by_player": [
      {
        "player_id": "string",
        "player_name": "string",
        "amount_owed": "integer",
        "is_settled": "boolean"
      }
    ]
  },
  "checkout_progress": {
    "total_players": "integer",
    "checked_out": "integer",
    "remaining": "integer"
  }
}
```

**Errors:** 404 (GAME_NOT_FOUND), 403 (FORBIDDEN)

---

#### `POST /api/v2/games/{game_id}/settlement/players/{player_id}/settle`

**Description:** Mark player's credit debt as settled (offline payment confirmed).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "settlement_method": "string*",  // e.g., "Venmo", "Cash", "Bank Transfer"
  "amount_settled": "integer*",
  "note": "string | null"
}
```

**Response 200:**
```json
{
  "player_id": "string",
  "player_name": "string",
  "amount_settled": "integer",
  "previous_owed": "integer",
  "remaining_owed": "integer",
  "settled_at": "string",
  "settlement_method": "string"
}
```

**Errors:** 404 (PLAYER_NOT_FOUND), 403 (FORBIDDEN), 400 (INVALID_AMOUNT)

---

#### `POST /api/v2/games/{game_id}/settlement/finalize`

**Description:** Finalize settlement and close game. Validates all players checked out and credits settled.

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Request:**
```json
{
  "force": "boolean"  // Default false. If true, finalize even with outstanding credits.
}
```

**Response 200:**
```json
{
  "game_id": "string",
  "status": "CLOSED",
  "closed_at": "string",
  "final_summary": {
    "total_players": "integer",
    "total_chips_in": "integer",
    "total_chips_out": "integer",
    "outstanding_credits": "integer",
    "duration_minutes": "integer"
  }
}
```

**Errors:** 403 (FORBIDDEN), 409 (OUTSTANDING_CHECKOUTS), 400 (OUTSTANDING_CREDITS)

---

#### `GET /api/v2/games/{game_id}/settlement/report`

**Description:** Generate final game report (CSV or JSON).

**Headers:** `Authorization: Bearer <token>` (Manager or Admin)

**Query Params:**
- `format`: "json" | "csv" (default "json")

**Response 200 (JSON):**
```json
{
  "game": {
    "game_id": "string",
    "game_code": "string",
    "manager_name": "string",
    "created_at": "string",
    "closed_at": "string",
    "duration_minutes": "integer"
  },
  "players": [
    {
      "player_name": "string",
      "total_cash_in": "integer",
      "total_credit_in": "integer",
      "total_cash_out": "integer",
      "credits_repaid": "integer",
      "credits_outstanding": "integer",
      "net_profit_loss": "integer"
    }
  ],
  "totals": {
    "total_cash_in": "integer",
    "total_credit_in": "integer",
    "total_cash_out": "integer",
    "bank_final_cash": "integer"
  }
}
```

**Response 200 (CSV):**
```
Content-Type: text/csv
Content-Disposition: attachment; filename="chipmate-game-ABCD12-2026-01-30.csv"

Player,Cash In,Credit In,Cash Out,Credits Repaid,Credits Outstanding,Net P/L
Alice,500,200,750,200,0,+50
Bob,300,0,250,0,0,-50
...
```

**Errors:** 404 (GAME_NOT_FOUND), 403 (FORBIDDEN), 409 (GAME_NOT_CLOSED)

---

### Admin Endpoints

#### `GET /api/v2/admin/games`

**Description:** List all games with filters and pagination.

**Headers:** `Authorization: Bearer <JWT>`

**Query Params:**
- `status`: GameStatus (optional)
- `created_after`: ISO 8601 timestamp (optional)
- `created_before`: ISO 8601 timestamp (optional)
- `limit`: integer (default 50, max 200)
- `offset`: integer (default 0)

**Response 200:**
```json
{
  "games": [
    {
      "game_id": "string",
      "game_code": "string",
      "manager_name": "string",
      "status": "GameStatus",
      "player_count": "integer",
      "created_at": "string",
      "closed_at": "string | null"
    }
  ],
  "total_count": "integer",
  "pagination": {
    "limit": "integer",
    "offset": "integer",
    "has_more": "boolean"
  }
}
```

**Errors:** 401 (INVALID_JWT), 403 (ADMIN_REQUIRED)

---

#### `GET /api/v2/admin/games/{game_id}`

**Description:** Get any game details (bypasses ownership check).

**Headers:** `Authorization: Bearer <JWT>`

**Response 200:**
```json
{
  // Same as GET /api/v2/games/{game_id}/status
  // Plus internal fields for debugging
  "_internal": {
    "db_id": "string",
    "created_by_ip": "string",
    "auto_close_at": "string"
  }
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (INVALID_JWT)

---

#### `POST /api/v2/admin/games/{game_id}/force-close`

**Description:** Force close game immediately (emergency use).

**Headers:** `Authorization: Bearer <JWT>`

**Request:**
```json
{
  "reason": "string*",  // Required audit log
  "notify_manager": "boolean"  // Default true
}
```

**Response 200:**
```json
{
  "game_id": "string",
  "status": "CLOSED",
  "forced_at": "string",
  "reason": "string"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (INVALID_JWT)

---

#### `POST /api/v2/admin/games/{game_id}/impersonate`

**Description:** Generate manager player token for admin support.

**Headers:** `Authorization: Bearer <JWT>`

**Request:**
```json
{
  "reason": "string*"  // Required audit log
}
```

**Response 200:**
```json
{
  "player_token": "string",  // JWT with is_manager=true
  "manager_player_id": "string",
  "expires_at": "string"
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (INVALID_JWT)

---

#### `DELETE /api/v2/admin/games/{game_id}`

**Description:** Permanently delete game and all related data (GDPR compliance).

**Headers:** `Authorization: Bearer <JWT>`

**Request:**
```json
{
  "confirm": "boolean*",  // Must be true
  "reason": "string*"
}
```

**Response 200:**
```json
{
  "game_id": "string",
  "deleted_at": "string",
  "deleted_records": {
    "players": "integer",
    "chip_requests": "integer",
    "notifications": "integer"
  }
}
```

**Errors:** 404 (GAME_NOT_FOUND), 401 (INVALID_JWT), 400 (CONFIRMATION_REQUIRED)

---

#### `GET /api/v2/admin/stats`

**Description:** System-wide statistics dashboard.

**Headers:** `Authorization: Bearer <JWT>`

**Response 200:**
```json
{
  "system": {
    "version": "string",
    "uptime_seconds": "integer",
    "environment": "string"
  },
  "games": {
    "total": "integer",
    "by_status": {
      "OPEN": "integer",
      "SETTLING": "integer",
      "CLOSED": "integer"
    },
    "created_last_24h": "integer",
    "created_last_7d": "integer"
  },
  "players": {
    "total": "integer",
    "active": "integer",
    "avg_per_game": "float"
  },
  "chip_requests": {
    "total": "integer",
    "pending": "integer",
    "approved_last_24h": "integer"
  },
  "performance": {
    "avg_request_approve_time_seconds": "float",
    "avg_checkout_time_seconds": "float"
  }
}
```

**Errors:** 401 (INVALID_JWT), 403 (ADMIN_REQUIRED)

---

### Health Endpoint

#### `GET /api/v2/health`

**Description:** Health check for load balancers and monitoring.

**Response 200:**
```json
{
  "status": "healthy",
  "timestamp": "string",  // ISO 8601
  "version": "string",
  "checks": {
    "database": "ok" | "degraded" | "down",
    "cache": "ok" | "down"
  }
}
```

**Response 503 (Unhealthy):**
```json
{
  "status": "unhealthy",
  "timestamp": "string",
  "checks": {
    "database": "down",
    "cache": "ok"
  }
}
```

---

## Error Response Format

All errors follow a consistent structure for easy client handling.

### Standard Error Response

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      // Optional field-specific errors
      "field_name": "validation message"
    },
    "request_id": "uuid",  // For support debugging
    "timestamp": "ISO 8601"
  }
}
```

### Error Code Catalog

| HTTP Status | Error Code | Description | Retry Safe |
|-------------|-----------|-------------|-----------|
| 400 | INVALID_INPUT | Request validation failed | No |
| 400 | INVALID_AMOUNT | Amount must be positive integer | No |
| 400 | INVALID_CHIP_COUNT | Chip count validation failed | No |
| 400 | DUPLICATE_NAME | Player name already exists in game | No |
| 400 | CONFIRMATION_REQUIRED | Missing required confirmation flag | No |
| 400 | OUTSTANDING_CREDITS | Cannot proceed with outstanding credits | No |
| 400 | PENDING_REQUESTS_EXIST | Cannot proceed with pending requests | No |
| 401 | UNAUTHORIZED | Authentication required | No |
| 401 | INVALID_TOKEN | Token is malformed or invalid | No |
| 401 | EXPIRED_TOKEN | Token has expired | No |
| 401 | INVALID_CREDENTIALS | Username or password incorrect | No |
| 401 | INVALID_JWT | Admin JWT invalid or expired | No |
| 403 | FORBIDDEN | Insufficient permissions for resource | No |
| 403 | ADMIN_REQUIRED | Admin role required | No |
| 403 | MANAGER_CANNOT_LEAVE | Manager cannot leave active game | No |
| 404 | GAME_NOT_FOUND | Game does not exist | No |
| 404 | PLAYER_NOT_FOUND | Player does not exist | No |
| 404 | REQUEST_NOT_FOUND | Chip request does not exist | No |
| 404 | NOTIFICATION_NOT_FOUND | Notification does not exist | No |
| 409 | GAME_NOT_JOINABLE | Game is SETTLING or CLOSED | No |
| 409 | GAME_NOT_OPEN | Game must be OPEN for this operation | No |
| 409 | GAME_NOT_SETTLING | Game must be SETTLING for this operation | No |
| 409 | INVALID_STATE_TRANSITION | Invalid game state transition | No |
| 409 | ALREADY_PROCESSED | Request already approved/declined | Yes |
| 409 | ALREADY_CHECKED_OUT | Player already checked out | Yes |
| 409 | CANNOT_LEAVE_WITH_CHIPS | Must cash out before leaving | No |
| 409 | OUTSTANDING_CHECKOUTS | All players must be checked out | No |
| 409 | NO_MORE_PLAYERS | No more players in checkout queue | No |
| 429 | RATE_LIMIT_EXCEEDED | Too many requests, slow down | Yes (after delay) |
| 500 | INTERNAL_SERVER_ERROR | Unexpected server error | Yes (after delay) |
| 503 | SERVICE_UNAVAILABLE | Service temporarily unavailable | Yes (after delay) |

### Validation Error Details

For 400 errors with field-level validation failures:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Request validation failed",
    "details": {
      "manager_name": "Must be between 2 and 50 characters",
      "amount": "Must be a positive integer"
    },
    "request_id": "abc-123",
    "timestamp": "2026-01-30T12:00:00Z"
  }
}
```

---

## Authentication Flows

### Flow 1: Admin Login

```
Client                          Server
  |                               |
  |--POST /api/v2/auth/admin/login-|
  |  {username, password}         |
  |                               |
  |<------------- JWT ------------|
  |                               |
  |-- All admin requests -------->|
  |  Authorization: Bearer JWT    |
  |                               |
```

**Implementation Notes:**
- JWT contains: `{"user_id": "admin", "role": "ADMIN", "exp": timestamp}`
- Token expires after 24 hours
- No refresh tokens (admin must re-login)
- Rate limit: 5 failed attempts per IP per 15 minutes

---

### Flow 2: Player Join and Token

```
Client                                    Server
  |                                         |
  |--POST /api/v2/games/{id}/players/join--|
  |  {player_name}                          |
  |                                         |
  |<-------- Player Token -----------------|
  |  {player_id, game_id, is_manager}      |
  |                                         |
  |-- All player requests ---------------->|
  |  Authorization: Bearer Token           |
  |                                         |
```

**Implementation Notes:**
- Player token JWT contains: `{"player_id": "uuid", "game_id": "string", "is_manager": false, "exp": timestamp}`
- Token expires when game closes + 7 days (for report access)
- No refresh needed (long-lived token)
- Rate limit: 10 joins per IP per game per hour (anti-spam)

---

### Flow 3: Game Creation (Manager Token)

```
Client                          Server
  |                               |
  |--POST /api/v2/games----------|
  |  {manager_name}               |
  |                               |
  |<-- Game + Manager Token ------|
  |  {game_id, player_token}      |
  |                               |
  |-- Manager requests --------->|
  |  Authorization: Bearer Token  |
  |  (is_manager: true)           |
  |                               |
```

**Implementation Notes:**
- Manager token JWT contains: `{"player_id": "uuid", "game_id": "string", "is_manager": true, "exp": timestamp}`
- Manager is also a player (can make chip requests, checkout themselves)
- Manager cannot leave game while game is OPEN or SETTLING
- Rate limit: 5 games per IP per hour

---

### Flow 4: Admin Impersonation

```
Admin Client                     Server
  |                                |
  |--POST /admin/games/{id}/impersonate|
  |  Authorization: Bearer JWT     |
  |  {reason}                      |
  |                                |
  |<---- Manager Player Token -----|
  |                                |
  |--Use token as manager-------->|
  |  Authorization: Bearer Token   |
  |  (is_manager: true)            |
  |                                |
```

**Implementation Notes:**
- Impersonation token is a regular player token with is_manager=true
- All actions logged with `impersonated_by: "admin"` flag
- Token expires after 1 hour (shorter than regular manager token)
- Audit log records: admin_user_id, game_id, reason, timestamp

---

### Token Validation Middleware Flow

```
Request with Token
      |
      v
  Extract JWT from Authorization header
      |
      v
  Verify signature + expiration
      |
      +--INVALID--> 401 INVALID_TOKEN
      |
      +--EXPIRED--> 401 EXPIRED_TOKEN
      |
      v
  Decode claims (user_id, role, game_id, player_id)
      |
      v
  Attach to request context
      |
      v
  Route handler (checks role permissions)
```

---

## System Architecture

ChipMate v2 follows a clean layered architecture optimized for FastAPI and async operations.

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Layer                           │
│  (React Web App - Mobile Browsers, Desktop)                 │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTPS / REST
┌────────────────────────────▼────────────────────────────────┐
│                     API Gateway                             │
│  (Railway / Nginx Reverse Proxy)                            │
│  - TLS Termination                                          │
│  - Rate Limiting (global)                                   │
│  - Request Logging                                          │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   FastAPI Application                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Middleware Stack                        │  │
│  │  1. CORS Handler                                     │  │
│  │  2. Request ID Generator                             │  │
│  │  3. Structured Logger                                │  │
│  │  4. Auth Token Validator                             │  │
│  │  5. Rate Limiter (per-user)                          │  │
│  │  6. Exception Handler                                │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                         │
│  ┌────────────────▼─────────────────────────────────────┐  │
│  │              Route Handlers                          │  │
│  │  /api/v2/auth/*                                      │  │
│  │  /api/v2/games/*                                     │  │
│  │  /api/v2/games/{id}/players/*                        │  │
│  │  /api/v2/games/{id}/chip-requests/*                  │  │
│  │  /api/v2/games/{id}/notifications/*                  │  │
│  │  /api/v2/games/{id}/checkout/*                       │  │
│  │  /api/v2/games/{id}/settlement/*                     │  │
│  │  /api/v2/admin/*                                     │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                         │
│  ┌────────────────▼─────────────────────────────────────┐  │
│  │            Service Layer                             │  │
│  │  - GameService                                       │  │
│  │  - PlayerService                                     │  │
│  │  - ChipRequestService                                │  │
│  │  - NotificationService                               │  │
│  │  - CheckoutService                                   │  │
│  │  - SettlementService                                 │  │
│  │  - AdminService                                      │  │
│  │  - AuthService                                       │  │
│  │  (Business Logic, State Transitions, Validation)    │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                         │
│  ┌────────────────▼─────────────────────────────────────┐  │
│  │        Data Access Layer (DAL)                       │  │
│  │  - GameRepository                                    │  │
│  │  - PlayerRepository                                  │  │
│  │  - ChipRequestRepository                             │  │
│  │  - NotificationRepository                            │  │
│  │  - CheckoutRepository                                │  │
│  │  (MongoDB Query Abstraction)                         │  │
│  └────────────────┬─────────────────────────────────────┘  │
└────────────────────┼─────────────────────────────────────────┘
                     │ Motor (Async)
┌────────────────────▼─────────────────────────────────────┐
│                   MongoDB 7+                             │
│  Collections:                                            │
│  - games                                                 │
│  - players                                               │
│  - chip_requests                                         │
│  - notifications                                         │
│  - checkouts                                             │
│  - admin_audit_log                                       │
└──────────────────────────────────────────────────────────┘

External Dependencies:
  - Redis (optional, future caching layer)
  - QR Code Generator (in-process library: qrcode)
```

### Layer Responsibilities

**1. Route Handlers** (`src/api/v2/routes/`)
- Parse and validate request schemas (Pydantic)
- Extract auth context from middleware
- Call appropriate service methods
- Format response schemas
- Handle HTTP-specific concerns (status codes, headers)
- NO business logic

**2. Service Layer** (`src/services/`)
- Implement business logic
- Enforce state machine rules (game states, request states)
- Coordinate multiple repositories (e.g., checkout updates player + creates checkout record)
- Generate notifications
- Validate business rules (e.g., "manager cannot leave game")
- Transaction boundaries (if using multi-document transactions)

**3. Data Access Layer** (`src/dal/`)
- MongoDB query construction
- CRUD operations
- Index management
- Query optimization
- Data mapping (MongoDB documents ↔ Python domain models)
- NO business logic

**4. Models** (`src/models/`)
- Pydantic models for API request/response
- Domain models (optional, for service layer)
- Enums and constants

**5. Middleware** (`src/middleware/`)
- Cross-cutting concerns (auth, logging, errors)
- Request context enrichment
- See Middleware Stack section below

---

### Database Schema (MongoDB Collections)

#### `games` Collection

```python
{
  "_id": ObjectId,
  "game_code": str,  # Index: unique
  "manager_player_id": str,  # UUID
  "manager_name": str,
  "status": str,  # OPEN | SETTLING | CLOSED
  "max_players": int,
  "created_at": datetime,
  "closed_at": datetime | None,
  "auto_close_at": datetime,  # created_at + 24h
  "created_by_ip": str,  # Audit

  # Denormalized counters (for performance)
  "player_count": int,
  "pending_request_count": int,

  # Metadata
  "version": int,  # Optimistic locking
}

# Indexes
- game_code (unique)
- status + created_at (for admin queries)
- auto_close_at (for cleanup job)
```

#### `players` Collection

```python
{
  "_id": ObjectId,
  "player_id": str,  # UUID, Index: unique
  "game_id": ObjectId,  # Index
  "name": str,
  "is_manager": bool,
  "is_active": bool,
  "joined_at": datetime,
  "left_at": datetime | None,

  # Chip tracking (denormalized for performance)
  "current_chips": int,
  "total_cash_in": int,
  "total_credit_in": int,
  "credits_owed": int,

  # Checkout
  "checked_out": bool,
  "checked_out_at": datetime | None,
  "checkout_id": ObjectId | None,

  # Metadata
  "join_ip": str,
  "version": int,
}

# Indexes
- player_id (unique)
- game_id + is_active
- game_id + name (for duplicate check)
```

#### `chip_requests` Collection

```python
{
  "_id": ObjectId,
  "request_id": str,  # UUID, Index: unique
  "game_id": ObjectId,  # Index
  "player_id": str,  # UUID
  "player_name": str,  # Denormalized

  "type": str,  # CASH | CREDIT
  "amount": int,
  "original_amount": int | None,  # If edited
  "status": str,  # PENDING | APPROVED | DECLINED | EDITED

  "created_at": datetime,
  "created_by": str,  # player_id (may differ if on-behalf-of)

  "processed_at": datetime | None,
  "processed_by": str | None,  # player_id of manager
  "processed_by_name": str | None,

  "note": str | None,
  "auto_approved": bool,  # True if manager created on-behalf-of

  # Metadata
  "version": int,
}

# Indexes
- request_id (unique)
- game_id + status + created_at
- game_id + player_id + created_at
```

#### `notifications` Collection

```python
{
  "_id": ObjectId,
  "notification_id": str,  # UUID, Index: unique
  "game_id": ObjectId,  # Index
  "recipient_player_id": str,  # UUID, Index

  "type": str,  # NotificationType enum
  "message": str,
  "data": dict,  # Type-specific payload

  "created_at": datetime,
  "is_read": bool,
  "read_at": datetime | None,

  # TTL: Auto-delete 7 days after game closes
  "expires_at": datetime,  # game.closed_at + 7 days
}

# Indexes
- notification_id (unique)
- game_id + recipient_player_id + is_read + created_at
- expires_at (TTL index)
```

#### `checkouts` Collection

```python
{
  "_id": ObjectId,
  "checkout_id": str,  # UUID, Index: unique
  "game_id": ObjectId,  # Index
  "player_id": str,  # UUID
  "player_name": str,

  "chip_count": int,
  "breakdown": {
    "credits_repaid": int,
    "remaining_credits": int,
    "cash_out": int,
    "chips_not_convertible": int,
  },

  "checked_out_at": datetime,
  "processed_by": str,  # player_id of manager

  # Override tracking
  "overridden": bool,
  "override_cash_amount": int | None,
  "override_credit_amount": int | None,
}

# Indexes
- checkout_id (unique)
- game_id + checked_out_at
- player_id (unique per player)
```

#### `admin_audit_log` Collection

```python
{
  "_id": ObjectId,
  "action": str,  # e.g., "FORCE_CLOSE", "IMPERSONATE", "DELETE_GAME"
  "admin_user_id": str,
  "game_id": ObjectId | None,
  "target_player_id": str | None,
  "reason": str,
  "timestamp": datetime,
  "ip_address": str,
  "user_agent": str,
}

# Indexes
- admin_user_id + timestamp
- game_id + timestamp
```

---

## Middleware Stack

Middleware executes in order for requests, reverse order for responses.

### 1. CORS Middleware

**Purpose:** Allow cross-origin requests from frontend.

**Configuration:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chipmate.app",
        "https://www.chipmate.app",
        "http://localhost:3000",  # Dev only
        "http://localhost:5173",  # Vite dev
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
    max_age=600,  # Cache preflight for 10 minutes
)
```

**Notes:**
- Wildcard `*` NOT allowed in production (security)
- `allow_credentials=True` required for cookie support (future)
- OPTIONS preflight cached to reduce latency

---

### 2. Request ID Middleware

**Purpose:** Assign unique ID to each request for tracing.

**Implementation:**
```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

**Usage:**
- Frontend can send `X-Request-ID` for idempotency
- All logs include request_id
- Error responses include request_id

---

### 3. Structured Logging Middleware

**Purpose:** Log all requests with structured data.

**Configuration:**
```python
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("chipmate.api")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()

        logger.info(
            "Request started",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host,
            }
        )

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Request completed",
            extra={
                "request_id": request.state.request_id,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        )

        return response
```

**Log Format:** JSON (for production)
```json
{
  "timestamp": "2026-01-30T12:00:00.123Z",
  "level": "INFO",
  "message": "Request completed",
  "request_id": "abc-123",
  "method": "POST",
  "path": "/api/v2/games",
  "status_code": 201,
  "duration_ms": 45.2
}
```

---

### 4. Authentication Middleware

**Purpose:** Validate tokens and attach user context to request.

**Implementation:**
```python
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import jwt

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Skip auth for public endpoints
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Extract token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "UNAUTHORIZED", "message": "Missing token"}}
            )

        token = auth_header.split(" ")[1]

        # Verify and decode
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "EXPIRED_TOKEN", "message": "Token expired"}}
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid token"}}
            )

        # Attach to request
        request.state.auth = {
            "user_id": payload["user_id"],
            "role": payload.get("role", "PLAYER"),
            "player_id": payload.get("player_id"),
            "game_id": payload.get("game_id"),
            "is_manager": payload.get("is_manager", False),
        }

        return await call_next(request)

PUBLIC_PATHS = {
    "/api/v2/health",
    "/api/v2/auth/admin/login",
    "/api/v2/games/code/{code}",  # Pattern match in actual implementation
}
```

**Request Context:**
- All authenticated routes access `request.state.auth`
- Route handlers check role permissions explicitly

---

### 5. Rate Limiting Middleware

**Purpose:** Prevent abuse and DoS attacks.

**Implementation Strategy:**

**Option A: In-Memory (Simple, Single Instance)**
```python
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """
        key: IP address or user_id
        limit: max requests
        window: time window in seconds
        """
        async with self.lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=window)

            # Clean old requests
            self.requests[key] = [
                ts for ts in self.requests[key] if ts > cutoff
            ]

            # Check limit
            if len(self.requests[key]) >= limit:
                return False

            # Record request
            self.requests[key].append(now)
            return True

# Apply to middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.limiter = RateLimiter()

    async def dispatch(self, request, call_next):
        # Use user_id if authenticated, else IP
        key = request.state.auth.get("user_id", request.client.host)

        # Different limits per endpoint category
        limit, window = self.get_limits(request.url.path)

        if not await self.limiter.is_allowed(key, limit, window):
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "RATE_LIMIT_EXCEEDED"}}
            )

        return await call_next(request)

    def get_limits(self, path: str) -> tuple[int, int]:
        if "/auth/" in path:
            return (5, 60)  # 5 per minute
        elif "/admin/" in path:
            return (100, 60)  # 100 per minute
        elif "/notifications" in path:
            return (60, 60)  # 60 per minute (high poll rate)
        else:
            return (30, 60)  # 30 per minute default
```

**Option B: Redis (Distributed, Production)**
```python
import redis.asyncio as redis

class RedisRateLimiter:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        result = await pipe.execute()

        count = result[0]
        return count <= limit
```

**Rate Limit Headers:**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1706616060
```

---

### 6. Exception Handler Middleware

**Purpose:** Catch all exceptions and return consistent error responses.

**Implementation:**
```python
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("chipmate.api")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log error with full context
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={
            "request_id": request.state.request_id,
            "path": request.url.path,
            "method": request.method,
        }
    )

    # Return generic error (don't leak internals)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "request_id": request.state.request_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Structured errors from our code
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                **exc.detail,  # Our error dict
                "request_id": request.state.request_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }
    )
```

---

## CORS Configuration

### Production CORS Policy

**Allowed Origins:**
- `https://chipmate.app`
- `https://www.chipmate.app`
- Railway preview deployments: `https://*.up.railway.app` (wildcard subdomain)

**Allowed Methods:**
- GET, POST, PUT, DELETE, OPTIONS

**Allowed Headers:**
- `Authorization`: Bearer tokens
- `Content-Type`: application/json
- `X-Request-ID`: Client-side request IDs

**Exposed Headers:**
- `X-Request-ID`: For client logging
- `X-RateLimit-Remaining`: Rate limit feedback

**Credentials:**
- `allow_credentials=true` (for future cookie support)

**Preflight Cache:**
- `max_age=600` (10 minutes)

---

### Mobile Browser Considerations

**Issue 1: Preflight Requests (OPTIONS)**
- Mobile browsers on slow networks pay high cost for preflight
- Solution: Cache preflight for 10 minutes, use simple requests where possible

**Issue 2: Token Storage**
- localStorage is preferred over cookies (no CSRF concerns, simpler)
- Tokens stored in localStorage, sent via `Authorization` header

**Issue 3: Network Reliability**
- Mobile networks drop connections frequently
- Solution: All mutations are idempotent (use request IDs)

---

### Environment-Specific Configuration

**Development:**
```python
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
]
```

**Staging:**
```python
CORS_ORIGINS = [
    "https://staging.chipmate.app",
    "https://*.up.railway.app",  # Railway preview
]
```

**Production:**
```python
CORS_ORIGINS = [
    "https://chipmate.app",
    "https://www.chipmate.app",
]
```

---

## Endpoint-to-User-Story Mapping

This section traces every endpoint to its corresponding user story, ensuring complete coverage.

### User Story 1: Create Game
**As a game manager**, I want to create a new game so players can join.

**Endpoints:**
- `POST /api/v2/games` - Create game

---

### User Story 2: Join Game
**As a player**, I want to join a game via link or QR code without registration.

**Endpoints:**
- `GET /api/v2/games/code/{code}` - Lookup game by code
- `POST /api/v2/games/{game_id}/players/join` - Join game
- `GET /api/v2/games/{game_id}/qr` - Generate QR code (manager)

---

### User Story 3: Request Chips (Player)
**As a player**, I want to request chips (cash or credit) and see approval status.

**Endpoints:**
- `POST /api/v2/games/{game_id}/chip-requests` - Create request
- `GET /api/v2/games/{game_id}/chip-requests/history` - View my requests
- `GET /api/v2/games/{game_id}/chip-requests/{request_id}` - Check request status

---

### User Story 4: Approve/Decline Requests (Manager)
**As a manager**, I want to approve, decline, or edit chip requests.

**Endpoints:**
- `GET /api/v2/games/{game_id}/chip-requests/pending` - View pending queue
- `POST /api/v2/games/{game_id}/chip-requests/{request_id}/approve` - Approve
- `POST /api/v2/games/{game_id}/chip-requests/{request_id}/decline` - Decline
- `POST /api/v2/games/{game_id}/chip-requests/{request_id}/edit-approve` - Edit + approve

---

### User Story 5: Request On Behalf Of (Manager)
**As a manager**, I want to create chip requests on behalf of any player.

**Endpoints:**
- `POST /api/v2/games/{game_id}/chip-requests` - With `on_behalf_of_player_id`

---

### User Story 6: Receive Notifications
**As a player**, I want to receive notifications when my requests are processed.

**Endpoints:**
- `GET /api/v2/games/{game_id}/notifications` - Poll for new notifications
- `POST /api/v2/games/{game_id}/notifications/{notification_id}/read` - Mark read
- `POST /api/v2/games/{game_id}/notifications/read-all` - Dismiss all

---

### User Story 7: View Game Status (Manager)
**As a manager**, I want to see game summary (players, chips in play, credits owed).

**Endpoints:**
- `GET /api/v2/games/{game_id}/status` - Comprehensive status
- `GET /api/v2/games/{game_id}/players` - Player list with balances

---

### User Story 8: Checkout Single Player (Manager)
**As a manager**, I want to checkout a player and calculate their cash/credit settlement.

**Endpoints:**
- `POST /api/v2/games/{game_id}/checkout/player/{player_id}` - Checkout

---

### User Story 9: Whole-Table Checkout (Manager)
**As a manager**, I want to start end-of-game checkout with credit-debt priority.

**Endpoints:**
- `POST /api/v2/games/{game_id}/checkout/whole-table` - Start SETTLING phase
- `GET /api/v2/games/{game_id}/checkout/order` - View checkout order
- `POST /api/v2/games/{game_id}/checkout/next` - Process next in queue

---

### User Story 10: Settlement and Close (Manager)
**As a manager**, I want to mark credit debts as settled and close the game.

**Endpoints:**
- `GET /api/v2/games/{game_id}/settlement/summary` - View outstanding credits
- `POST /api/v2/games/{game_id}/settlement/players/{player_id}/settle` - Mark settled
- `POST /api/v2/games/{game_id}/settlement/finalize` - Finalize settlement
- `POST /api/v2/games/{game_id}/close` - Close game
- `GET /api/v2/games/{game_id}/settlement/report` - Export final report

---

### User Story 11: Admin Oversight
**As an admin**, I want to view all games, force-close games, and access system stats.

**Endpoints:**
- `GET /api/v2/admin/games` - List all games
- `GET /api/v2/admin/games/{game_id}` - View any game
- `POST /api/v2/admin/games/{game_id}/force-close` - Emergency close
- `POST /api/v2/admin/games/{game_id}/impersonate` - Generate manager token
- `DELETE /api/v2/admin/games/{game_id}` - Delete game
- `GET /api/v2/admin/stats` - System statistics

---

### User Story 12: Player Self-Service
**As a player**, I want to view my chip balance and leave the game.

**Endpoints:**
- `GET /api/v2/games/{game_id}/players/me` - My info + balance
- `POST /api/v2/games/{game_id}/players/me/leave` - Leave game

---

### User Story 13: Token Validation
**As a client app**, I want to validate my token on startup.

**Endpoints:**
- `GET /api/v2/auth/validate` - Validate token + get user context

---

### Coverage Analysis

**Total User Stories:** 13
**Total Endpoints:** 37
**Coverage:** 100% (all stories mapped to endpoints)

---

## Migration from V1

### Breaking Changes

1. **Base Path Change:** `/api/*` → `/api/v2/*`
2. **Authentication:** Mixed auth → JWT (admin) + UUID tokens (players)
3. **Game Status:** `active` → `OPEN`, no status → `SETTLING`, `ended` → `CLOSED`
4. **Transaction Model:** `buyin_cash`/`buyin_register` → unified `chip_requests` with `type` field
5. **Player IDs:** Numeric user_id → UUID player_id
6. **Response Structure:** Flat objects → Nested schemas with clear namespacing

---

### V1 to V2 Endpoint Mapping

| V1 Endpoint | V2 Endpoint | Notes |
|------------|------------|-------|
| `POST /api/auth/login` | `POST /api/v2/auth/admin/login` | Admin only, returns JWT |
| (none) | `GET /api/v2/auth/validate` | New endpoint |
| `POST /api/games` | `POST /api/v2/games` | Returns player_token |
| `POST /api/games/join` | `POST /api/v2/games/{id}/players/join` | RESTful path |
| `GET /api/games/{id}` | `GET /api/v2/games/{id}` | Similar |
| `GET /api/games/{id}/status` | `GET /api/v2/games/{id}/status` | Similar |
| `GET /api/games/{code}/link` | `GET /api/v2/games/{id}/qr` | Manager auth required |
| `GET /api/games/{id}/players` | `GET /api/v2/games/{id}/players` | Similar |
| (none) | `GET /api/v2/games/{id}/players/me` | New endpoint |
| `POST /api/transactions/buyin` | `POST /api/v2/games/{id}/chip-requests` | Unified model |
| `POST /api/transactions/cashout` | `POST /api/v2/games/{id}/checkout/player/{pid}` | Different concept |
| `GET /api/games/{id}/transactions/pending` | `GET /api/v2/games/{id}/chip-requests/pending` | Similar |
| `POST /api/transactions/{id}/approve` | `POST /api/v2/games/{id}/chip-requests/{rid}/approve` | RESTful |
| `POST /api/transactions/{id}/reject` | `POST /api/v2/games/{id}/chip-requests/{rid}/decline` | Renamed |
| (none) | `POST /api/v2/games/{id}/chip-requests/{rid}/edit-approve` | New endpoint |
| (none) | `GET /api/v2/games/{id}/notifications` | New polling endpoint |
| `POST /api/games/{id}/host-buyin` | `POST /api/v2/games/{id}/chip-requests` | Use on_behalf_of |
| `POST /api/games/{id}/host-cashout` | `POST /api/v2/games/{id}/checkout/player/{pid}` | Merged |
| `POST /api/games/{id}/end` | `POST /api/v2/games/{id}/close` | Renamed |
| `GET /api/games/{id}/settlement` | `GET /api/v2/games/{id}/settlement/summary` | Enhanced |
| `POST /api/games/{id}/settlement/start` | `POST /api/v2/games/{id}/checkout/whole-table` | Renamed concept |
| `GET /api/games/{id}/report` | `GET /api/v2/games/{id}/settlement/report` | Similar |
| `GET /api/admin/games` | `GET /api/v2/admin/games` | Similar |
| `GET /api/admin/stats` | `GET /api/v2/admin/stats` | Similar |
| `DELETE /api/admin/games/{id}/destroy` | `DELETE /api/v2/admin/games/{id}` | Renamed |

---

### Data Migration Strategy

**Option 1: Clean Slate (Recommended)**
- V2 launches as new product
- No migration of V1 data
- V1 remains available read-only for 30 days
- Users export reports manually

**Option 2: One-Time Migration**
- Write migration script: V1 MongoDB → V2 MongoDB
- Map old schemas to new schemas
- Challenges:
  - Convert numeric user_id to UUID (maintain mapping)
  - Reconstruct game states from transaction history
  - Regenerate tokens for active games

**Recommendation:** Clean slate. V1 has minimal production usage.

---

### Versioning Strategy

**Current Plan:** Dual versioning (parallel V1 + V2)
- V1: `/api/*` (frozen, no new features)
- V2: `/api/v2/*` (active development)

**Deprecation Timeline:**
- Day 0: V2 launches
- Day 30: V1 marked deprecated (warning banner)
- Day 90: V1 read-only (no new games)
- Day 180: V1 sunset

**Future Versions:**
- V3: `/api/v3/*` (if breaking changes needed)
- Always maintain N and N-1 versions simultaneously

---

## Appendix A: Non-Functional Requirements

### Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| P50 latency (read) | < 100ms | CloudWatch |
| P95 latency (read) | < 300ms | CloudWatch |
| P50 latency (write) | < 200ms | CloudWatch |
| P95 latency (write) | < 500ms | CloudWatch |
| Throughput | 100 req/sec per instance | Load test |
| Concurrent games | 1000+ | Stress test |
| Players per game | 100 max | Configurable |

### Scalability

**Horizontal Scaling:**
- FastAPI app is stateless (except in-memory rate limiter)
- Use Redis for distributed rate limiting in production
- MongoDB supports read replicas (not needed for MVP)

**Database Scaling:**
- Proper indexes on all query patterns (see schema section)
- Denormalized counters to avoid aggregation queries
- TTL indexes for auto-cleanup (notifications, old games)

**Caching Strategy (Future):**
- Cache game status (5 second TTL)
- Cache pending requests (invalidate on approve/decline)
- Use Redis with pub/sub for cache invalidation

---

### Security Requirements

**Authentication:**
- JWT tokens with HS256 (symmetric key)
- Secret key: 256-bit random, rotated every 90 days
- No refresh tokens for players (long-lived tokens)

**Authorization:**
- Role-based access control (ADMIN, MANAGER, PLAYER)
- Manager can only access their game
- Admin can access all games

**Input Validation:**
- All inputs validated via Pydantic
- Max string lengths enforced
- SQL injection: N/A (MongoDB)
- NoSQL injection: Prevented via Motor parameterized queries

**Rate Limiting:**
- Global: 1000 req/min per IP (DDoS protection)
- Per-user: 30 req/min (prevents abuse)
- Auth endpoints: 5 req/min (brute force protection)

**Data Privacy:**
- No PII collected (only first names)
- IP addresses logged for abuse detection (30-day retention)
- GDPR: Admin delete endpoint for right to erasure

**HTTPS Only:**
- All production traffic over TLS 1.3
- HSTS header: `max-age=31536000; includeSubDomains`

---

### Observability

**Logging:**
- Structured JSON logs (CloudWatch)
- Log levels: DEBUG (dev), INFO (prod), ERROR (always)
- No secrets in logs

**Metrics:**
- Request count by endpoint
- Request latency (P50, P95, P99)
- Error rate by endpoint
- Active games count
- Database connection pool stats

**Tracing:**
- Request ID propagation
- Correlate logs across services (future microservices)

**Alerting:**
- P95 latency > 1s for 5 minutes
- Error rate > 1% for 5 minutes
- Database connection pool exhausted
- Disk space < 10%

---

## Appendix B: Future Enhancements

**Phase 2 (Post-MVP):**
1. WebSocket notifications (replace polling)
2. Multi-currency support (chips + real currency)
3. Player avatars
4. Game templates (preset buy-in amounts, blinds)
5. Manager assistant role (delegate approvals)

**Phase 3 (Advanced):**
1. Tournament mode (multi-table)
2. Real-time leaderboard
3. Player statistics (lifetime stats)
4. Export integrations (Venmo, PayPal for settlements)
5. Mobile native apps (React Native)

**Technical Debt Backlog:**
1. Replace in-memory rate limiter with Redis
2. Add database replica for read scaling
3. Implement request caching
4. Add OpenTelemetry tracing
5. Write comprehensive integration tests

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Tech Lead Architect | Initial draft |

---

**End of Document**

This API contract is ready for review by the backend engineer, frontend engineer, and QA team. Please provide feedback on:

1. Missing endpoints or user stories
2. Schema ambiguities
3. Security concerns
4. Performance bottlenecks
5. Migration risks

Next steps:
1. Review and approve contract (Supervisor + stakeholders)
2. Generate OpenAPI spec from this document
3. Backend Engineer: Implement FastAPI routes + services
4. Frontend Engineer: Generate TypeScript client from OpenAPI
5. QA Engineer: Write test plan based on endpoint catalog
