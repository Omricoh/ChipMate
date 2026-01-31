# T2 -- ChipMate v2 MongoDB Schema Design

**Ticket:** T2
**Author:** Data Architect
**Date:** 2026-01-30
**Status:** PROPOSED
**Database:** MongoDB 7+ with Motor (async Python driver)
**ODM/Validation:** Pydantic v2

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Embedded vs. Referenced Decisions](#2-embedded-vs-referenced-decisions)
3. [Collection Definitions](#3-collection-definitions)
   - 3.1 [games](#31-games-collection)
   - 3.2 [players](#32-players-collection)
   - 3.3 [chip_requests](#33-chip_requests-collection)
   - 3.4 [notifications](#34-notifications-collection)
4. [Index Definitions](#4-index-definitions)
5. [Example Queries](#5-example-queries)
6. [TTL / Auto-Close Strategy](#6-ttl--auto-close-strategy)
7. [Pydantic v2 Models](#7-pydantic-v2-models)
8. [Migration Notes from V1](#8-migration-notes-from-v1)

---

## 1. Design Principles

| Principle | Rationale |
|---|---|
| **Single-game scope** | Every query is scoped to one game. `game_id` is the universal partition key. |
| **UUID tokens, not user accounts** | Players are ephemeral and identified by a UUID token issued on join. No registration, no passwords. |
| **Explicit status enums** | V1 used boolean pairs (`confirmed`/`rejected`). V2 uses a single `status` field with well-defined enum values. |
| **Embed what is read together** | Bank data is always read with the game. Embed it. Player lists are queried independently and can grow. Reference them. |
| **Integers for chip amounts** | All monetary/chip values are integers (no floating point). The smallest unit is 1 chip. |
| **UTC timestamps everywhere** | All `datetime` fields are stored in UTC. |

---

## 2. Embedded vs. Referenced Decisions

### 2.1 Bank Data -- EMBEDDED in `games`

**Decision:** Embed bank as a sub-document inside the `games` collection.

**Justification:**
- Bank is a 1:1 relationship with a game. There is exactly one bank per game, always.
- Bank data is read on virtually every game status poll (the manager dashboard shows cash balance, chips in play, etc.).
- Bank data is updated atomically with game state (e.g., when a chip request is approved, the bank totals and the request status must be consistent).
- Embedding eliminates a separate collection, a separate query, and a separate index. This reduces latency and operational complexity.
- The bank sub-document is small and bounded (fixed set of integer counters). It will never grow unboundedly.
- V1 had bank as a separate collection (`banks`), which caused an extra round-trip on every game status fetch. Embedding fixes this.

**Trade-off:** If bank logic were to become shared across multiple games (e.g., a "house bank"), this would need to be extracted. That is not in scope for v2.

### 2.2 Player List -- REFERENCED (separate `players` collection)

**Decision:** Store players in a separate `players` collection, referenced by `game_id`.

**Justification:**
- Players are queried independently: "get my player record by token", "list all players in a game", "update a single player's checkout state".
- The player list can grow (typical game: 4-12 players, but no hard upper bound in the domain).
- Players have mutable per-game state (credits_owed, final_chips, checked_out) that is updated independently of the game document.
- Embedding players inside the game document would require array manipulation (`$elemMatch`, `$` positional updates) which is fragile, harder to index, and slower for targeted reads.
- Separate collection allows clean compound indexes on `(game_id, player_token)` for O(1) lookups.

**Trade-off:** Requires a second query to fetch players alongside game data. This is acceptable because the player list endpoint is separate from the game status endpoint in the API.

### 2.3 Chip Request History -- REFERENCED (separate `chip_requests` collection)

**Decision:** Store chip requests in a separate `chip_requests` collection, referenced by `game_id`.

**Justification:**
- Chip requests are an unbounded, append-only log. A single game can have dozens to hundreds of requests.
- Requests are queried with different filters: pending (manager view), by player (player activity view), all approved (settlement aggregation).
- Requests have their own lifecycle (PENDING -> APPROVED/DECLINED/EDITED) with independent status transitions.
- Embedding in the game document would bloat the game document and make filtered queries impractical.
- Embedding in the player document would complicate on-behalf-of requests (where `requested_by` differs from `player_token`).

**Trade-off:** Aggregation queries (game summary totals) require scanning the chip_requests collection. This is mitigated by proper indexes and the fact that per-game request counts are small (hundreds, not millions).

---

## 3. Collection Definitions

### 3.1 `games` Collection

Represents a poker session. Created when the manager starts a game. Contains embedded bank data.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `_id` | `ObjectId` | auto | auto-generated | MongoDB document ID. |
| `code` | `str` | yes | -- | 6-character uppercase alphanumeric game code for join link/QR. Unique among OPEN games. |
| `status` | `str` | yes | `"OPEN"` | Game lifecycle state. Enum: `OPEN`, `SETTLING`, `CLOSED`. |
| `manager_player_token` | `str` (UUID) | yes | -- | The `player_token` of the player who created the game (the manager). |
| `created_at` | `datetime` | yes | `utcnow()` | When the game was created. |
| `closed_at` | `datetime` | no | `null` | When the game was closed (manually or by TTL). |
| `expires_at` | `datetime` | yes | `created_at + 24h` | Used for TTL auto-close. Set to `created_at + 24 hours` on creation. |
| `bank` | `object` | yes | (see below) | Embedded bank sub-document. |

**Embedded `bank` sub-document:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `bank.cash_balance` | `int` | yes | `0` | Current cash held by the bank (cash_in minus cash_out). |
| `bank.total_cash_in` | `int` | yes | `0` | Cumulative cash received from cash buy-ins. |
| `bank.total_cash_out` | `int` | yes | `0` | Cumulative cash paid out during cashouts. |
| `bank.total_credits_issued` | `int` | yes | `0` | Cumulative chips issued on credit across all players. |
| `bank.total_credits_repaid` | `int` | yes | `0` | Cumulative credits repaid by players. |
| `bank.total_chips_issued` | `int` | yes | `0` | Total chips ever issued (cash + credit buy-ins). |
| `bank.total_chips_returned` | `int` | yes | `0` | Total chips returned via cashouts. |
| `bank.chips_in_play` | `int` | yes | `0` | Current chips with players (`issued - returned`). |

**Example document:**

```json
{
  "_id": ObjectId("665f1a2b3c4d5e6f7a8b9c0d"),
  "code": "ABC123",
  "status": "OPEN",
  "manager_player_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": ISODate("2026-01-30T20:00:00Z"),
  "closed_at": null,
  "expires_at": ISODate("2026-01-31T20:00:00Z"),
  "bank": {
    "cash_balance": 500,
    "total_cash_in": 800,
    "total_cash_out": 300,
    "total_credits_issued": 200,
    "total_credits_repaid": 50,
    "total_chips_issued": 1000,
    "total_chips_returned": 300,
    "chips_in_play": 700
  }
}
```

---

### 3.2 `players` Collection

Represents a player's participation in a specific game. One document per player per game.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `_id` | `ObjectId` | auto | auto-generated | MongoDB document ID. |
| `game_id` | `str` | yes | -- | String representation of the game's `_id`. Foreign key to `games`. |
| `player_token` | `str` (UUID) | yes | -- | UUID v4 token identifying this player. Issued on join. Used in all subsequent requests. |
| `display_name` | `str` | yes | -- | Player-chosen display name (entered on join). |
| `is_manager` | `bool` | yes | `false` | Whether this player is the game manager (host). Exactly one per game. |
| `is_active` | `bool` | yes | `true` | Whether the player is currently active in the game. Set to `false` on checkout or quit. |
| `credits_owed` | `int` | yes | `0` | Outstanding credit this player owes to the bank. |
| `checked_out` | `bool` | yes | `false` | Whether the manager has processed this player's final checkout. |
| `final_chip_count` | `int` | no | `null` | Final chip count entered by manager during checkout. `null` until checkout. |
| `profit_loss` | `int` | no | `null` | Calculated P/L: `final_chip_count - total_buy_ins`. `null` until checkout. |
| `joined_at` | `datetime` | yes | `utcnow()` | When the player joined the game. |
| `checked_out_at` | `datetime` | no | `null` | When the player was checked out. |

**Example document:**

```json
{
  "_id": ObjectId("665f1b2c3c4d5e6f7a8b9c0e"),
  "game_id": "665f1a2b3c4d5e6f7a8b9c0d",
  "player_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "display_name": "Danny",
  "is_manager": true,
  "is_active": true,
  "credits_owed": 0,
  "checked_out": false,
  "final_chip_count": null,
  "profit_loss": null,
  "joined_at": ISODate("2026-01-30T20:00:00Z"),
  "checked_out_at": null
}
```

---

### 3.3 `chip_requests` Collection

Represents a buy-in request (cash or credit) from a player. Replaces v1's `transactions` collection.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `_id` | `ObjectId` | auto | auto-generated | MongoDB document ID. |
| `game_id` | `str` | yes | -- | String representation of the game's `_id`. Foreign key to `games`. |
| `player_token` | `str` (UUID) | yes | -- | The player this request is for (the recipient of chips). |
| `requested_by` | `str` (UUID) | yes | -- | The player who submitted the request. Same as `player_token` for self-requests. Different for on-behalf-of requests (e.g., manager submits for a player). |
| `request_type` | `str` | yes | -- | Type of buy-in. Enum: `CASH`, `CREDIT`. |
| `amount` | `int` | yes | -- | Number of chips requested. Must be > 0. |
| `status` | `str` | yes | `"PENDING"` | Request lifecycle state. Enum: `PENDING`, `APPROVED`, `DECLINED`, `EDITED`. |
| `edited_amount` | `int` | no | `null` | If status is `EDITED`, the manager-adjusted amount. `null` unless edited. |
| `created_at` | `datetime` | yes | `utcnow()` | When the request was submitted. |
| `resolved_at` | `datetime` | no | `null` | When the manager approved/declined/edited. `null` while PENDING. |
| `resolved_by` | `str` (UUID) | no | `null` | The `player_token` of the manager who resolved the request. |

**Status Transitions:**

```
PENDING --> APPROVED    (manager approves as-is)
PENDING --> DECLINED    (manager declines)
PENDING --> EDITED      (manager changes amount, then implicitly approves at edited_amount)
```

**Effective amount logic:** If `status == "EDITED"`, the effective chip amount is `edited_amount`. Otherwise if `status == "APPROVED"`, it is `amount`. Declined and pending requests contribute 0 chips.

**Example document (self-request, approved):**

```json
{
  "_id": ObjectId("665f1c3d4e5f6a7b8c9d0e1f"),
  "game_id": "665f1a2b3c4d5e6f7a8b9c0d",
  "player_token": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "requested_by": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "request_type": "CASH",
  "amount": 100,
  "status": "APPROVED",
  "edited_amount": null,
  "created_at": ISODate("2026-01-30T20:15:00Z"),
  "resolved_at": ISODate("2026-01-30T20:16:00Z"),
  "resolved_by": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Example document (on-behalf-of, edited):**

```json
{
  "_id": ObjectId("665f1d4e5f6a7b8c9d0e1f20"),
  "game_id": "665f1a2b3c4d5e6f7a8b9c0d",
  "player_token": "c3d4e5f6-a7b8-9012-cdef-345678901234",
  "requested_by": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_type": "CREDIT",
  "amount": 200,
  "status": "EDITED",
  "edited_amount": 150,
  "created_at": ISODate("2026-01-30T20:20:00Z"),
  "resolved_at": ISODate("2026-01-30T20:21:00Z"),
  "resolved_by": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

### 3.4 `notifications` Collection

Poll-based notifications for players. Created by backend events; consumed by player clients polling their unread notifications.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `_id` | `ObjectId` | auto | auto-generated | MongoDB document ID. |
| `game_id` | `str` | yes | -- | String representation of the game's `_id`. Foreign key to `games`. |
| `player_token` | `str` (UUID) | yes | -- | The player who should see this notification. |
| `notification_type` | `str` | yes | -- | Enum: `REQUEST_APPROVED`, `REQUEST_DECLINED`, `REQUEST_EDITED`, `ON_BEHALF_SUBMITTED`, `CHECKOUT_COMPLETE`, `GAME_SETTLING`, `GAME_CLOSED`. |
| `message` | `str` | yes | -- | Human-readable notification text. |
| `related_id` | `str` | no | `null` | Optional reference to a related entity (e.g., chip_request `_id` as string). |
| `is_read` | `bool` | yes | `false` | Whether the player has dismissed/acknowledged this notification. |
| `created_at` | `datetime` | yes | `utcnow()` | When the notification was created. |

**Notification trigger rules:**

| Event | Recipient (`player_token`) | `notification_type` |
|---|---|---|
| Manager approves a request | The player whose request was approved | `REQUEST_APPROVED` |
| Manager declines a request | The player whose request was declined | `REQUEST_DECLINED` |
| Manager edits a request | The player whose request was edited | `REQUEST_EDITED` |
| Someone submits on-behalf-of | The target player (who receives the chips) | `ON_BEHALF_SUBMITTED` |
| Manager completes player checkout | The checked-out player | `CHECKOUT_COMPLETE` |
| Manager moves game to SETTLING | All players in the game | `GAME_SETTLING` |
| Game is closed | All players in the game | `GAME_CLOSED` |

**Example document:**

```json
{
  "_id": ObjectId("665f1e5f6a7b8c9d0e1f2031"),
  "game_id": "665f1a2b3c4d5e6f7a8b9c0d",
  "player_token": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "notification_type": "REQUEST_APPROVED",
  "message": "Your 100-chip cash buy-in has been approved.",
  "related_id": "665f1c3d4e5f6a7b8c9d0e1f",
  "is_read": false,
  "created_at": ISODate("2026-01-30T20:16:00Z")
}
```

---

## 4. Index Definitions

### 4.1 `games` Indexes

```javascript
// 1. Unique game code among non-closed games.
//    Ensures no two OPEN or SETTLING games share a code.
//    Uses a partial filter so closed/reused codes do not conflict.
db.games.createIndex(
  { "code": 1 },
  {
    unique: true,
    partialFilterExpression: { "status": { "$in": ["OPEN", "SETTLING"] } },
    name: "uq_code_active_games"
  }
)

// 2. Auto-close: find OPEN games past their expiration.
//    Used by the auto-close background task (query-based, not MongoDB TTL).
//    See Section 6 for rationale.
db.games.createIndex(
  { "expires_at": 1 },
  {
    partialFilterExpression: { "status": "OPEN" },
    name: "idx_expires_at_open_games"
  }
)

// 3. Status filter for admin/listing queries.
db.games.createIndex(
  { "status": 1, "created_at": -1 },
  { name: "idx_status_created" }
)
```

**Rationale:**
- Index 1 supports the join-by-code flow. Players enter a code to find the game. Uniqueness prevents ambiguity. Partial filter allows code reuse after a game closes.
- Index 2 supports the auto-close cron/background task that queries for OPEN games past `expires_at`.
- Index 3 supports admin dashboard listing games by status, sorted by creation date.

---

### 4.2 `players` Indexes

```javascript
// 1. Primary lookup: find a specific player in a game.
//    Used on every authenticated request (validate token belongs to game).
db.players.createIndex(
  { "game_id": 1, "player_token": 1 },
  {
    unique: true,
    name: "uq_game_player_token"
  }
)

// 2. Token-only lookup: find which game(s) a token belongs to.
//    Used when a returning player's client sends only their token.
db.players.createIndex(
  { "player_token": 1 },
  { name: "idx_player_token" }
)

// 3. List all players in a game (for manager view, settlement).
//    Covered by index 1's prefix, so this is implicit -- no separate index needed.
//    The query { game_id: X } uses the left prefix of index 1.
```

**Rationale:**
- Index 1 is the workhorse index. Every API call after join includes `game_id` and `player_token`. This compound unique index ensures one player per token per game and provides O(1) lookups.
- Index 2 supports the "reconnect" flow where a player returns and the client only has their stored token.
- No separate `{ game_id: 1 }` index is needed because it is the left prefix of index 1.

---

### 4.3 `chip_requests` Indexes

```javascript
// 1. Manager polls pending requests for a game.
//    This is the most frequent query -- the manager dashboard auto-polls.
db.chip_requests.createIndex(
  { "game_id": 1, "status": 1, "created_at": 1 },
  { name: "idx_game_status_created" }
)

// 2. Player fetches own activity (all their requests in a game).
db.chip_requests.createIndex(
  { "game_id": 1, "player_token": 1, "created_at": -1 },
  { name: "idx_game_player_created" }
)

// 3. Game summary aggregation: sum approved amounts by type for a game.
//    Covered by index 1 (filter on game_id + status=APPROVED, then scan).
//    No separate index needed.
```

**Rationale:**
- Index 1 directly supports the critical path: `{ game_id: X, status: "PENDING" }` sorted by `created_at`. This is polled every few seconds by the manager's client. The index also supports filtering by other statuses (APPROVED for settlement aggregation).
- Index 2 supports the player activity view: "show me all my requests in this game, newest first."
- No additional index for aggregation because index 1 covers `{ game_id, status: "APPROVED" }` and the aggregation pipeline scans a small number of documents per game.

---

### 4.4 `notifications` Indexes

```javascript
// 1. Player polls unread notifications.
//    This is polled by every player client on an interval.
db.notifications.createIndex(
  { "player_token": 1, "game_id": 1, "is_read": 1, "created_at": -1 },
  { name: "idx_player_game_unread" }
)

// 2. TTL: auto-delete old notifications after 48 hours.
//    Notifications are ephemeral. No need to keep them after the game ends.
db.notifications.createIndex(
  { "created_at": 1 },
  {
    expireAfterSeconds: 172800,
    name: "ttl_notifications_48h"
  }
)
```

**Rationale:**
- Index 1 is the primary query path. Players poll `{ player_token: X, game_id: Y, is_read: false }` sorted by `created_at` descending. The compound index makes this an index-only scan.
- Index 2 uses MongoDB's native TTL feature to automatically garbage-collect notifications older than 48 hours. Since notifications are only relevant during and shortly after a game, this prevents unbounded collection growth. 48 hours provides a buffer beyond the 24-hour game TTL.

---

## 5. Example Queries

### 5.1 Get Pending Chip Requests for a Game (Manager View)

The manager dashboard polls this every few seconds to show incoming buy-in requests.

```python
# Motor (async)
async def get_pending_requests(db, game_id: str) -> list[dict]:
    cursor = db.chip_requests.find(
        {"game_id": game_id, "status": "PENDING"}
    ).sort("created_at", 1)  # oldest first (FIFO)
    return await cursor.to_list(length=100)
```

```javascript
// MongoDB shell equivalent
db.chip_requests.find(
  { game_id: "665f1a2b3c4d5e6f7a8b9c0d", status: "PENDING" }
).sort({ created_at: 1 })
```

**Index used:** `idx_game_status_created` -- exact match on `game_id` + `status`, sorted by `created_at`.

---

### 5.2 Get Player Activity (Player's Own Requests)

Shows a player their full request history in the current game.

```python
# Motor (async)
async def get_player_activity(db, game_id: str, player_token: str) -> list[dict]:
    cursor = db.chip_requests.find(
        {"game_id": game_id, "player_token": player_token}
    ).sort("created_at", -1)  # newest first
    return await cursor.to_list(length=100)
```

```javascript
// MongoDB shell equivalent
db.chip_requests.find(
  {
    game_id: "665f1a2b3c4d5e6f7a8b9c0d",
    player_token: "b2c3d4e5-f6a7-8901-bcde-f23456789012"
  }
).sort({ created_at: -1 })
```

**Index used:** `idx_game_player_created` -- exact match on `game_id` + `player_token`, sorted by `created_at` descending.

---

### 5.3 Get Game Summary Stats (Aggregation)

Computes total cash, total credit, and chip counts from approved requests. Used for the game summary dashboard.

```python
# Motor (async)
async def get_game_summary(db, game_id: str) -> dict:
    pipeline = [
        {
            "$match": {
                "game_id": game_id,
                "status": {"$in": ["APPROVED", "EDITED"]}
            }
        },
        {
            "$group": {
                "_id": "$request_type",
                "total_amount": {
                    "$sum": {
                        "$cond": {
                            "if": {"$eq": ["$status", "EDITED"]},
                            "then": "$edited_amount",
                            "else": "$amount"
                        }
                    }
                },
                "request_count": {"$sum": 1}
            }
        }
    ]
    results = await db.chip_requests.aggregate(pipeline).to_list(length=10)

    summary = {"total_cash": 0, "total_credit": 0, "total_requests": 0}
    for r in results:
        if r["_id"] == "CASH":
            summary["total_cash"] = r["total_amount"]
        elif r["_id"] == "CREDIT":
            summary["total_credit"] = r["total_amount"]
        summary["total_requests"] += r["request_count"]

    summary["total_chips"] = summary["total_cash"] + summary["total_credit"]
    return summary
```

```javascript
// MongoDB shell equivalent
db.chip_requests.aggregate([
  {
    $match: {
      game_id: "665f1a2b3c4d5e6f7a8b9c0d",
      status: { $in: ["APPROVED", "EDITED"] }
    }
  },
  {
    $group: {
      _id: "$request_type",
      total_amount: {
        $sum: {
          $cond: {
            if: { $eq: ["$status", "EDITED"] },
            then: "$edited_amount",
            else: "$amount"
          }
        }
      },
      request_count: { $sum: 1 }
    }
  }
])
```

**Index used:** `idx_game_status_created` -- match on `game_id`, filter on `status` in `["APPROVED", "EDITED"]`.

---

### 5.4 Get Unread Notifications for a Player

Player client polls this to show notification badges and toasts.

```python
# Motor (async)
async def get_unread_notifications(
    db, player_token: str, game_id: str
) -> list[dict]:
    cursor = db.notifications.find(
        {
            "player_token": player_token,
            "game_id": game_id,
            "is_read": False
        }
    ).sort("created_at", -1)
    return await cursor.to_list(length=50)
```

```javascript
// MongoDB shell equivalent
db.notifications.find({
  player_token: "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  game_id: "665f1a2b3c4d5e6f7a8b9c0d",
  is_read: false
}).sort({ created_at: -1 })
```

**Index used:** `idx_player_game_unread` -- exact match on `player_token` + `game_id` + `is_read`, sorted by `created_at` descending.

---

### 5.5 Find Games to Auto-Close (Expired OPEN Games)

Background task runs periodically (e.g., every 5 minutes) to find and close stale games.

```python
# Motor (async)
from datetime import datetime, timezone

async def find_and_close_expired_games(db) -> int:
    now = datetime.now(timezone.utc)

    # Find all OPEN games past their expiration
    result = await db.games.update_many(
        {
            "status": "OPEN",
            "expires_at": {"$lte": now}
        },
        {
            "$set": {
                "status": "CLOSED",
                "closed_at": now
            }
        }
    )
    return result.modified_count
```

```javascript
// MongoDB shell equivalent
var now = new Date();
db.games.updateMany(
  { status: "OPEN", expires_at: { $lte: now } },
  { $set: { status: "CLOSED", closed_at: now } }
)
```

**Index used:** `idx_expires_at_open_games` -- partial index on `expires_at` filtered to `status: "OPEN"`.

---

### 5.6 Approve a Chip Request and Update Bank (Multi-Document Pattern)

This demonstrates the write pattern for approving a request and updating the embedded bank atomically.

```python
# Motor (async)
from bson import ObjectId
from datetime import datetime, timezone

async def approve_chip_request(
    db, request_id: str, game_id: str, manager_token: str
) -> bool:
    now = datetime.now(timezone.utc)

    # Step 1: Fetch the request to get amount and type
    request_oid = ObjectId(request_id)
    chip_request = await db.chip_requests.find_one(
        {"_id": request_oid, "status": "PENDING"}
    )
    if not chip_request:
        return False

    amount = chip_request["amount"]
    request_type = chip_request["request_type"]

    # Step 2: Update request status (optimistic lock on status=PENDING)
    update_result = await db.chip_requests.update_one(
        {"_id": request_oid, "status": "PENDING"},
        {
            "$set": {
                "status": "APPROVED",
                "resolved_at": now,
                "resolved_by": manager_token
            }
        }
    )
    if update_result.modified_count == 0:
        return False  # Already resolved by another request

    # Step 3: Update embedded bank in game document
    bank_update = {
        "bank.total_chips_issued": amount,
        "bank.chips_in_play": amount,
    }
    if request_type == "CASH":
        bank_update["bank.cash_balance"] = amount
        bank_update["bank.total_cash_in"] = amount
    elif request_type == "CREDIT":
        bank_update["bank.total_credits_issued"] = amount

    await db.games.update_one(
        {"_id": ObjectId(game_id)},
        {"$inc": bank_update}
    )

    # Step 4: If credit, also update player's credits_owed
    if request_type == "CREDIT":
        await db.players.update_one(
            {
                "game_id": game_id,
                "player_token": chip_request["player_token"]
            },
            {"$inc": {"credits_owed": amount}}
        )

    return True
```

**Note on atomicity:** MongoDB does not support multi-collection transactions without replica sets. For v2, the design accepts eventual consistency between the request status, bank, and player credit updates. Each individual update is atomic. If the process fails mid-way, the system can detect and reconcile because the request status (the source of truth) is updated first via an optimistic lock on `status: "PENDING"`. For stricter guarantees, enable replica set transactions via Motor's `start_session()` / `start_transaction()`.

---

### 5.7 Get Player's Buy-In Totals for Checkout

Used during settlement to compute a player's total buy-ins for P/L calculation.

```python
# Motor (async)
async def get_player_buyin_total(
    db, game_id: str, player_token: str
) -> dict:
    pipeline = [
        {
            "$match": {
                "game_id": game_id,
                "player_token": player_token,
                "status": {"$in": ["APPROVED", "EDITED"]}
            }
        },
        {
            "$group": {
                "_id": None,
                "total_cash": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$request_type", "CASH"]},
                            {
                                "$cond": [
                                    {"$eq": ["$status", "EDITED"]},
                                    "$edited_amount",
                                    "$amount"
                                ]
                            },
                            0
                        ]
                    }
                },
                "total_credit": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$request_type", "CREDIT"]},
                            {
                                "$cond": [
                                    {"$eq": ["$status", "EDITED"]},
                                    "$edited_amount",
                                    "$amount"
                                ]
                            },
                            0
                        ]
                    }
                }
            }
        }
    ]
    results = await db.chip_requests.aggregate(pipeline).to_list(length=1)
    if results:
        r = results[0]
        total = r["total_cash"] + r["total_credit"]
        return {
            "total_cash": r["total_cash"],
            "total_credit": r["total_credit"],
            "total_buy_ins": total
        }
    return {"total_cash": 0, "total_credit": 0, "total_buy_ins": 0}
```

**Index used:** `idx_game_player_created` -- match on `game_id` + `player_token`, then filter by status in the pipeline.

---

## 6. TTL / Auto-Close Strategy

### Decision: Query-Based Auto-Close (NOT MongoDB TTL Index on Games)

**Approach:** Use a background task (asyncio periodic task or cron) that runs every 5 minutes, queries for expired OPEN games, and transitions them to CLOSED.

**Why NOT use MongoDB's native TTL index to delete game documents:**

| Factor | MongoDB TTL Delete | Query-Based Close |
|---|---|---|
| **Data preservation** | Deletes the document entirely | Sets `status = "CLOSED"`, preserves all data |
| **Cascade handling** | Cannot cascade to players/requests/notifications | The close task can also clean up related state |
| **Business logic** | No business logic on delete (just gone) | Can trigger notifications, run settlement, log events |
| **Precision** | TTL monitor runs ~every 60s, not exact | Runs on your schedule (5 min is fine for 24h window) |
| **Visibility** | Silent deletion | Explicit status change, auditable |

**Implementation details:**

1. On game creation, compute `expires_at = created_at + timedelta(hours=24)` and store it in the game document.
2. A background asyncio task runs every 5 minutes:
   ```python
   import asyncio
   from datetime import datetime, timezone

   async def auto_close_loop(db):
       while True:
           now = datetime.now(timezone.utc)
           result = await db.games.update_many(
               {"status": "OPEN", "expires_at": {"$lte": now}},
               {"$set": {"status": "CLOSED", "closed_at": now}}
           )
           if result.modified_count > 0:
               # Optionally: create GAME_CLOSED notifications
               # for all players in each closed game
               pass
           await asyncio.sleep(300)  # 5 minutes
   ```
3. The `idx_expires_at_open_games` partial index ensures this query is efficient even with many historical games.
4. **Defense in depth:** The API layer also checks `expires_at` on any game read and returns CLOSED status if expired, even if the background task has not yet run.

**TTL for notifications (separate concern):** Notifications DO use MongoDB's native TTL index (`ttl_notifications_48h`) because they are truly ephemeral and can be safely deleted after 48 hours with no business impact.

**Trade-offs accepted:**
- The background task introduces up to 5 minutes of lag between actual expiry and status change. For a 24-hour window, this is negligible.
- If the background task is down, games remain OPEN past 24h. The defense-in-depth API check mitigates this.

---

## 7. Pydantic v2 Models

All models use Pydantic v2 conventions: `model_config` dict instead of inner `Config` class, `field_serializer` for custom serialization, `StrEnum` for enum types, and `Field` with `gt=0` for validation.

### 7.1 Enums

```python
# src/models/enums.py

from enum import StrEnum


class GameStatus(StrEnum):
    OPEN = "OPEN"
    SETTLING = "SETTLING"
    CLOSED = "CLOSED"


class ChipRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    EDITED = "EDITED"


class RequestType(StrEnum):
    CASH = "CASH"
    CREDIT = "CREDIT"


class NotificationType(StrEnum):
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_DECLINED = "REQUEST_DECLINED"
    REQUEST_EDITED = "REQUEST_EDITED"
    ON_BEHALF_SUBMITTED = "ON_BEHALF_SUBMITTED"
    CHECKOUT_COMPLETE = "CHECKOUT_COMPLETE"
    GAME_SETTLING = "GAME_SETTLING"
    GAME_CLOSED = "GAME_CLOSED"
```

### 7.2 Bank Model (Embedded Sub-Document)

```python
# src/models/bank.py

from pydantic import BaseModel


class Bank(BaseModel):
    """Embedded bank sub-document within a Game.

    Tracks all cash and credit flows for a poker session.
    All values are integers representing chip counts.
    """
    cash_balance: int = 0
    total_cash_in: int = 0
    total_cash_out: int = 0
    total_credits_issued: int = 0
    total_credits_repaid: int = 0
    total_chips_issued: int = 0
    total_chips_returned: int = 0
    chips_in_play: int = 0
```

### 7.3 Game Model

```python
# src/models/game.py

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from src.models.enums import GameStatus
from src.models.bank import Bank


class Game(BaseModel):
    """Represents a poker session (game).

    The game document includes an embedded Bank sub-document
    that tracks all cash and credit flows.
    """
    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[str] = Field(default=None, alias="_id")
    code: str
    status: GameStatus = GameStatus.OPEN
    manager_player_token: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: Optional[datetime] = None
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    bank: Bank = Field(default_factory=Bank)

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at", "closed_at", "expires_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()
```

### 7.4 Player Model

```python
# src/models/player.py

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer


class Player(BaseModel):
    """Represents a player's participation in a specific game.

    Players are identified by a UUID token (no registration required).
    One document per player per game.
    """
    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[str] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    display_name: str
    is_manager: bool = False
    is_active: bool = True
    credits_owed: int = 0
    checked_out: bool = False
    final_chip_count: Optional[int] = None
    profit_loss: Optional[int] = None
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    checked_out_at: Optional[datetime] = None

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("joined_at", "checked_out_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()
```

### 7.5 ChipRequest Model

```python
# src/models/chip_request.py

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, model_validator

from src.models.enums import ChipRequestStatus, RequestType


class ChipRequest(BaseModel):
    """Represents a buy-in request (cash or credit) from a player.

    Replaces v1's Transaction model. Uses an explicit status enum
    instead of boolean confirmed/rejected fields.
    """
    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[str] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    requested_by: str
    request_type: RequestType
    amount: int = Field(gt=0)
    status: ChipRequestStatus = ChipRequestStatus.PENDING
    edited_amount: Optional[int] = Field(default=None, gt=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    @model_validator(mode="after")
    def validate_edited_amount(self) -> "ChipRequest":
        if (
            self.status == ChipRequestStatus.EDITED
            and self.edited_amount is None
        ):
            raise ValueError(
                "edited_amount is required when status is EDITED"
            )
        return self

    @property
    def effective_amount(self) -> int:
        """The actual chip amount after manager resolution.
        Returns 0 for DECLINED or PENDING requests.
        """
        if self.status == ChipRequestStatus.EDITED:
            return self.edited_amount  # type: ignore[return-value]
        if self.status == ChipRequestStatus.APPROVED:
            return self.amount
        return 0

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at", "resolved_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()
```

### 7.6 Notification Model

```python
# src/models/notification.py

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from src.models.enums import NotificationType


class Notification(BaseModel):
    """Poll-based notification for a player.

    Created by backend events (request approval, checkout, etc.).
    Consumed by player clients polling for unread notifications.
    Auto-deleted after 48 hours via MongoDB TTL index.
    """
    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    id: Optional[str] = Field(default=None, alias="_id")
    game_id: str
    player_token: str
    notification_type: NotificationType
    message: str
    related_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_serializer("id")
    def serialize_id(self, value: Optional[str], _info) -> Optional[str]:
        if value is not None:
            return str(value)
        return value

    @field_serializer("created_at")
    def serialize_datetime(
        self, value: Optional[datetime], _info
    ) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()
```

---

## 8. Migration Notes from V1

This section documents the key structural changes from v1 to v2. This is a **green-field redesign**, not a live migration -- v2 starts with empty collections.

| V1 Concept | V2 Replacement | Change Summary |
|---|---|---|
| `Player.user_id` (integer) | `Player.player_token` (UUID string) | Players identified by UUID token, not integer user ID. No registration required. |
| `Transaction` collection | `chip_requests` collection | Renamed. Explicit `status` enum replaces `confirmed`/`rejected` booleans. New `EDITED` status. |
| `Transaction.type` values `buyin_cash` / `buyin_register` | `ChipRequest.request_type` values `CASH` / `CREDIT` | Clearer naming. Only buy-in requests are modeled here. Cashout is a separate checkout flow in v2. |
| No `requested_by` field | `ChipRequest.requested_by` | New field enables on-behalf-of requests where the manager submits for a player. |
| `banks` collection (separate) | `Game.bank` (embedded sub-document) | Bank is now embedded in the game document. Eliminates extra round-trip on every status poll. |
| `Game.status` values `active` / `ending` / `settled` / `expired` | `Game.status` values `OPEN` / `SETTLING` / `CLOSED` | Simplified to 3 uppercase states. `expired` is absorbed into `CLOSED`. |
| No notifications | `notifications` collection | New collection for poll-based player notifications. |
| 12-hour game expiry (code-level check in DAL) | 24-hour expiry via `expires_at` field + background task | Explicit `expires_at` field with partial index. Background task for clean transitions. |
| `Game.players` (embedded array of user_id ints) | Removed from game document | Player list lives only in the `players` collection. No denormalized array in the game document. |
| `Game.host_id` / `Game.host_user_id` (int) | `Game.manager_player_token` (UUID string) | Manager identified by their player token, consistent with the token-based identity system. |
| `Game.settlement_phase` field | Managed in application layer | Settlement sub-phases (credit settlement, final cashout, completed) are handled by application logic using `Game.status = SETTLING`. Can be added as a field later if needed. |
| `Player.quit` (boolean) | `Player.is_active` (boolean, inverted sense) | Simplified. `is_active = false` covers both quit and checked-out states. |
| `Player.cashed_out` / `Player.cashout_time` | `Player.checked_out` / `Player.checked_out_at` | Renamed for clarity. "Checkout" is the v2 term for the end-of-game settlement process. |
| `Player.final_chips` | `Player.final_chip_count` | Renamed for clarity. |
| No P/L field | `Player.profit_loss` | New computed field stored at checkout time: `final_chip_count - total_buy_ins`. |
| `Transaction.at` (datetime) | `ChipRequest.created_at` + `ChipRequest.resolved_at` | Split into two timestamps: when the request was created and when it was resolved. |

---

## Appendix A: Entity Relationship Diagram (Textual)

```
+---------------------------+          +------------------------+
|         games             |          |       players          |
|---------------------------|          |------------------------|
| _id          (ObjectId)   |<----+    | _id        (ObjectId)  |
| code         (str)        |     |    | game_id    (str) ------+--> games._id
| status       (str)        |     |    | player_token (UUID)    |
| manager_player_token (str)|     |    | display_name (str)     |
| created_at   (datetime)   |     |    | is_manager   (bool)    |
| closed_at    (datetime?)  |     |    | is_active    (bool)    |
| expires_at   (datetime)   |     |    | credits_owed (int)     |
| bank: {                   |     |    | checked_out  (bool)    |
|   cash_balance      (int) |     |    | final_chip_count (int?)|
|   total_cash_in     (int) |     |    | profit_loss  (int?)    |
|   total_cash_out    (int) |     |    | joined_at    (datetime)|
|   total_credits_issued    |     |    | checked_out_at (dt?)   |
|                     (int) |     |    +------------------------+
|   total_credits_repaid    |     |
|                     (int) |     |    +------------------------+
|   total_chips_issued(int) |     |    |    chip_requests       |
|   total_chips_returned    |     |    |------------------------|
|                     (int) |     +----| game_id    (str)       |
|   chips_in_play     (int) |     |    | player_token (UUID)    |
| }                         |     |    | requested_by (UUID)    |
+---------------------------+     |    | request_type (str)     |
                                  |    | amount       (int)     |
                                  |    | status       (str)     |
                                  |    | edited_amount (int?)   |
                                  |    | created_at  (datetime) |
                                  |    | resolved_at (datetime?)|
                                  |    | resolved_by (str?)     |
                                  |    +------------------------+
                                  |
                                  |    +------------------------+
                                  |    |    notifications       |
                                  |    |------------------------|
                                  +----| game_id    (str)       |
                                       | player_token (UUID)    |
                                       | notification_type (str)|
                                       | message      (str)     |
                                       | related_id   (str?)    |
                                       | is_read      (bool)    |
                                       | created_at  (datetime) |
                                       +------------------------+
```

**Relationships:**
- `games` 1:N `players` (via `players.game_id` -> string of `games._id`)
- `games` 1:N `chip_requests` (via `chip_requests.game_id`)
- `games` 1:N `notifications` (via `notifications.game_id`)
- `players.player_token` is referenced by `chip_requests.player_token` and `notifications.player_token`
- `bank` is embedded 1:1 inside `games` (not a separate collection)

---

## Appendix B: Collection and Index Setup Script

Complete script to initialize collections and indexes in MongoDB shell.

```javascript
// ============================================================
// ChipMate v2 -- MongoDB Collection and Index Setup
// Run against: use chipmate_v2
// ============================================================

// --- Create collections ---
db.createCollection("games");
db.createCollection("players");
db.createCollection("chip_requests");
db.createCollection("notifications");

// --- games indexes ---

db.games.createIndex(
  { "code": 1 },
  {
    unique: true,
    partialFilterExpression: { "status": { "$in": ["OPEN", "SETTLING"] } },
    name: "uq_code_active_games"
  }
);

db.games.createIndex(
  { "expires_at": 1 },
  {
    partialFilterExpression: { "status": "OPEN" },
    name: "idx_expires_at_open_games"
  }
);

db.games.createIndex(
  { "status": 1, "created_at": -1 },
  { name: "idx_status_created" }
);

// --- players indexes ---

db.players.createIndex(
  { "game_id": 1, "player_token": 1 },
  {
    unique: true,
    name: "uq_game_player_token"
  }
);

db.players.createIndex(
  { "player_token": 1 },
  { name: "idx_player_token" }
);

// --- chip_requests indexes ---

db.chip_requests.createIndex(
  { "game_id": 1, "status": 1, "created_at": 1 },
  { name: "idx_game_status_created" }
);

db.chip_requests.createIndex(
  { "game_id": 1, "player_token": 1, "created_at": -1 },
  { name: "idx_game_player_created" }
);

// --- notifications indexes ---

db.notifications.createIndex(
  { "player_token": 1, "game_id": 1, "is_read": 1, "created_at": -1 },
  { name: "idx_player_game_unread" }
);

db.notifications.createIndex(
  { "created_at": 1 },
  {
    expireAfterSeconds: 172800,
    name: "ttl_notifications_48h"
  }
);

print("ChipMate v2: All collections and indexes created successfully.");
```
