# T4: ChipMate v2 Security Threat Model

**Document Version:** 1.0
**Date:** 2026-01-30
**Status:** Final for Review
**Classification:** Public

---

## Executive Summary

This document presents a comprehensive security threat analysis for ChipMate v2, a mobile-first web application for managing live poker games among friends. The system is publicly accessible on the internet (Railway deployment), handles no real money, but manages game state that users care about.

**Key Findings:**

- **Critical Must-Fix Issues:** 3 items requiring immediate attention before public launch
- **High-Priority Issues:** 7 items that should be addressed in the first release
- **Medium-Priority Issues:** 9 items for post-launch hardening
- **Low-Priority/Accepted Risks:** 5 items with acceptable mitigation strategies

**Risk Posture:** The system has MODERATE overall risk. The authentication design is lightweight by intention (no real money at stake), but several critical input validation and brute-force protection gaps must be addressed before public deployment.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Trust Boundaries and Data Flow](#2-trust-boundaries-and-data-flow)
3. [Authentication and Authorization Design Review](#3-authentication-and-authorization-design-review)
4. [Threat Matrix (STRIDE Analysis)](#4-threat-matrix-stride-analysis)
5. [Game Code Entropy Analysis](#5-game-code-entropy-analysis)
6. [Input Validation Requirements](#6-input-validation-requirements)
7. [Must-Fix Items](#7-must-fix-items)
8. [Dependency Risk Assessment](#8-dependency-risk-assessment)
9. [HTTPS Enforcement Strategy](#9-https-enforcement-strategy)
10. [Defense-in-Depth Recommendations](#10-defense-in-depth-recommendations)
11. [Incident Response Considerations](#11-incident-response-considerations)

---

## 1. System Overview

### 1.1 Architecture Components

ChipMate v2 follows a three-tier architecture:

```
┌──────────────────────────────────────────────────────┐
│  Client Layer (React/TypeScript in Mobile Browsers)  │
│  - localStorage for player UUID tokens               │
│  - Polling-based UI updates (5-second intervals)     │
└──────────────────┬───────────────────────────────────┘
                   │ HTTPS / REST API
                   │ Authorization: Bearer <token>
┌──────────────────▼───────────────────────────────────┐
│  Application Layer (Python FastAPI)                  │
│  - JWT validation middleware                         │
│  - Role-based authorization (ADMIN/MANAGER/PLAYER)   │
│  - Rate limiting middleware                          │
│  - Business logic services                           │
└──────────────────┬───────────────────────────────────┘
                   │ Motor (async driver)
┌──────────────────▼───────────────────────────────────┐
│  Data Layer (MongoDB 7+)                             │
│  - games collection (embedded bank)                  │
│  - players collection                                │
│  - chip_requests collection                          │
│  - notifications collection                          │
└──────────────────────────────────────────────────────┘
```

**Current Implementation Note:** The existing `/Users/b/Documents/GitHub/ChipMate/src/api/web_api.py` uses Flask, not FastAPI. The design documents specify FastAPI, indicating a planned migration. This threat model addresses BOTH the current Flask implementation and the target FastAPI architecture.

### 1.2 Assets to Protect

| Asset | Sensitivity | Consequences of Compromise |
|-------|-------------|---------------------------|
| Game state (chip balances, requests) | MEDIUM | Players lose trust; incorrect cash settlements |
| Player display names | LOW | No PII; low privacy impact |
| Admin credentials | HIGH | Full system access; ability to delete all games |
| Manager role assignment | MEDIUM | Unauthorized approval of chip requests |
| Game codes | LOW-MEDIUM | Unauthorized joining; limited impact |
| Credit debt records | MEDIUM | Players dispute who owes what |
| IP addresses (logs) | LOW | Audit trail; minimal PII |

### 1.3 Threat Actors

| Actor | Motivation | Capability | Likelihood |
|-------|-----------|------------|-----------|
| Disgruntled player | Cheat by manipulating chip counts | Low-Medium (browser tools, basic scripting) | MEDIUM |
| External attacker (opportunistic) | Denial of service, defacement | Medium (automated scanners) | HIGH |
| External attacker (targeted) | Data harvesting, credential theft | High (dedicated effort) | LOW |
| Malicious insider (player at table) | Social engineering, token theft | Medium (physical access to devices) | LOW |
| Admin account compromise | Full system control | High (if credentials leaked) | LOW |

---

## 2. Trust Boundaries and Data Flow

### 2.1 Trust Boundary Map

```
                    INTERNET (Untrusted)
                           │
                           ▼
              ┌────────────────────────┐
              │  Railway Edge / HTTPS  │ ◄─── Trust Boundary #1
              └────────────┬───────────┘      (TLS termination)
                           │
                           ▼
              ┌────────────────────────┐
              │  FastAPI Application   │ ◄─── Trust Boundary #2
              │  (Auth Middleware)     │      (Token validation)
              └────────────┬───────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌────────┐      ┌──────────┐      ┌──────────┐
    │ PLAYER │      │ MANAGER  │      │  ADMIN   │ ◄─── Trust Boundary #3
    │ Role   │      │ Role     │      │  Role    │      (Role-based access)
    └────────┘      └──────────┘      └──────────┘
         │                 │                 │
         └─────────────────┴─────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  MongoDB (Localhost)   │ ◄─── Trust Boundary #4
              │  (No network auth)     │      (Process isolation)
              └────────────────────────┘
```

**Critical Trust Boundaries:**

1. **Internet → Application (HTTPS):** All clients are untrusted. Must enforce HTTPS, validate all inputs, rate limit.
2. **Unauthenticated → Authenticated (JWT):** Token validation must be cryptographically sound.
3. **Role elevation (Player → Manager → Admin):** Authorization checks must prevent horizontal and vertical privilege escalation.
4. **Application → Database:** MongoDB runs localhost-only with no authentication (acceptable for single-instance deployment; risk if network exposed).

### 2.2 Data Flow Analysis

#### 2.2.1 Player Join Flow (High Exposure)

```
1. Player scans QR or enters code (public, no auth)
2. GET /api/v2/games/code/{code} (no auth) → Returns game_id
3. POST /api/v2/games/{game_id}/players/join (no auth)
   - Input: player_name (user-controlled string)
   - Output: player_token (UUID4 JWT)
4. Player stores token in localStorage
5. All future requests: Authorization: Bearer <player_token>
```

**Threats at this boundary:**
- Code enumeration/brute-force (public endpoint, no rate limit in v1)
- Name collision attacks (duplicate name injection)
- XSS via malicious player names (if not sanitized on render)
- Token theft via localStorage (XSS or physical access)

#### 2.2.2 Chip Request Approval Flow (Manager Privilege)

```
1. Player creates chip request
   POST /api/v2/games/{game_id}/chip-requests
   Auth: Player token
   Input: type (CASH/CREDIT), amount (integer)

2. Manager polls pending requests
   GET /api/v2/games/{game_id}/chip-requests/pending
   Auth: Manager token (is_manager=true)

3. Manager approves request
   POST /api/v2/games/{game_id}/chip-requests/{request_id}/approve
   Auth: Manager token
   Side effects: Updates bank balances, player chip counts
```

**Threats at this boundary:**
- Manager impersonation (if JWT secret compromised or token stolen)
- Request ID prediction (if not using UUIDs or secure random)
- Double-approval race condition (if not idempotent)
- Amount manipulation (if request can be modified post-creation)

---

## 3. Authentication and Authorization Design Review

### 3.1 Admin JWT Flow

**Current Design (from T3 spec):**
```python
JWT Payload:
{
  "user_id": "admin",
  "role": "ADMIN",
  "exp": <timestamp>  # 24 hours from issue
}

Algorithm: HS256 (HMAC-SHA256)
Secret Key: Environment variable ADMIN_JWT_SECRET
Token Expiry: 24 hours, no refresh
```

**Security Assessment:**

| Aspect | Current State | Recommendation | Priority |
|--------|--------------|----------------|----------|
| **Algorithm** | HS256 (symmetric) | APPROVED. Simpler than RS256 for single-instance. | ✅ |
| **Secret Strength** | Not specified in code | MUST be 256-bit (32 bytes) minimum. Generate with `openssl rand -hex 32`. | CRITICAL |
| **Secret Rotation** | No rotation policy | SHOULD rotate every 90 days. Implement key versioning in JWT header (`kid` claim). | MEDIUM |
| **Token Expiry** | 24 hours | APPROVED for admin use case (re-login acceptable). | ✅ |
| **Refresh Tokens** | None | ACCEPTED. 24h expiry is reasonable for admin. | ✅ |
| **Token Storage** | Not specified | MUST NOT store in localStorage. Use httpOnly cookies OR sessionStorage (XSS risk remains). | HIGH |
| **Rate Limiting** | Spec says 5 attempts per IP per 15 min | APPROVED. Must implement in middleware. | HIGH |
| **Logout** | No server-side invalidation | ACCEPTED RISK. Stateless JWT cannot be invalidated server-side. Logout clears client token. Document this limitation. | LOW |

**CRITICAL FINDING:** The current Flask implementation in `/Users/b/Documents/GitHub/ChipMate/src/api/web_api.py` line 67-68 uses a simple username/password check via `admin_service.authenticate_admin()` but does NOT generate a JWT. It returns a user object but no token. **The JWT flow is not implemented.**

**Verdict:** ⚠️ MUST IMPLEMENT JWT generation with strong secret before launch.

---

### 3.2 Player UUID Token Flow

**Current Design (from T3 spec):**
```python
Player Token JWT Payload:
{
  "player_id": "<uuid4>",  # Randomly generated UUID
  "game_id": "<ObjectId string>",
  "is_manager": false,
  "exp": <game.closed_at + 7 days>  # Long-lived
}

Token issued on: POST /api/v2/games/{id}/players/join
Storage: localStorage (client-side)
Transmission: Authorization: Bearer <token> header
```

**Security Assessment:**

| Aspect | Current State | Recommendation | Priority |
|--------|--------------|----------------|----------|
| **Entropy** | UUID4 = 122 bits | APPROVED. Cryptographically random. | ✅ |
| **Uniqueness** | per-game UUID4 collision risk ~0 | APPROVED. UUID4 collision probability negligible. | ✅ |
| **Storage** | localStorage | ACCEPTED RISK. Vulnerable to XSS. Alternative: httpOnly cookie (breaks CORS preflight). Document this trade-off. | MEDIUM |
| **Transmission** | Authorization header (not cookie) | APPROVED. Avoids CSRF, but susceptible to XSS token theft. | ✅ |
| **Expiry** | game.closed_at + 7 days | APPROVED. Allows post-game report access. | ✅ |
| **Revocation** | No server-side revocation | ACCEPTED RISK. Player "leaves game" is soft-delete, token remains valid. Document limitation. | LOW |
| **Token Reuse** | Same token works on multiple devices | APPROVED. Allows multi-device access (convenience). | ✅ |

**Current Implementation:** Flask code at line 186-187 generates `user_id = int(datetime.now().timestamp() * 1000)` (timestamp-based integer ID), NOT a UUID4. **This is weaker entropy and predictable.**

**Verdict:** ⚠️ MUST migrate to UUID4 generation as specified in design.

---

### 3.3 Role Resolution Logic

**Current Design:**
```
Role hierarchy: ADMIN > MANAGER > PLAYER

Authorization checks (per-endpoint):
- Public endpoints: No auth (GET /api/v2/games/code/{code})
- Player endpoints: Require player_id match OR is_manager=true
- Manager endpoints: Require is_manager=true OR role=ADMIN
- Admin endpoints: Require role=ADMIN only
```

**Security Assessment:**

| Risk | Description | Mitigation | Priority |
|------|-------------|-----------|----------|
| **Horizontal Privilege Escalation** | Player A accesses Player B's chip requests | Check `player_id == token.player_id` OR `token.is_manager` | HIGH |
| **Vertical Privilege Escalation** | Player forges `is_manager=true` in token | JWT signature prevents this (if secret strong) | ✅ (depends on secret) |
| **Admin Impersonation Abuse** | Admin enters game as manager, leaves audit trail unclear | Audit log with `impersonated_by: "admin"` flag (per spec) | MEDIUM |
| **Manager Role Theft** | If `is_manager` checked only in JWT, not in DB | MUST cross-check `players.is_manager` field in DB on critical operations | HIGH |

**Current Implementation:** Flask code does NOT validate `is_manager` against the database. Authorization is purely JWT-based. **This creates a window for privilege escalation if JWT secret leaks.**

**Verdict:** ⚠️ SHOULD add DB-based is_manager verification for approve/decline operations.

---

### 3.4 Admin Impersonation Mechanism

**Design (from T3):**
```
POST /api/v2/admin/games/{game_id}/impersonate
- Generates a manager player token for the admin
- Token has is_manager=true
- Expires after 1 hour (shorter than regular manager)
- All actions logged with impersonated_by: "admin"
```

**Security Assessment:**

| Risk | Description | Mitigation | Priority |
|------|-------------|-----------|----------|
| **Impersonation Token Leak** | Admin token used maliciously if stolen | 1-hour expiry limits blast radius | ✅ |
| **Audit Trail Bypass** | Admin actions not distinguishable from manager | Implement `impersonated_by` flag in all mutations | CRITICAL |
| **No User Notification** | Real manager unaware admin took over | Out of scope (no push notifications) | ACCEPTED |
| **Privilege Confusion** | Admin token has manager privileges but no admin API access | Clearly document scope in UI banner | LOW |

**Current Implementation:** Impersonation endpoint not implemented in Flask code.

**Verdict:** MUST implement with audit logging before enabling admin features.

---

## 4. Threat Matrix (STRIDE Analysis)

### 4.1 Complete Threat Catalog

| ID | Threat | OWASP Category | STRIDE | Component | Likelihood | Impact | Risk | Mitigation | Status |
|----|--------|---------------|--------|-----------|-----------|--------|------|-----------|--------|
| **T-001** | **Game code brute-force** | A01:2021 Broken Access Control | Spoofing | `/api/v2/games/code/{code}` (public) | HIGH | MEDIUM | **HIGH** | Rate limit: 10 req/min per IP. Use 6-char alphanumeric = 2.2B combinations. Block after 100 failed lookups per IP per hour. | **MUST-FIX** |
| **T-002** | **Player name XSS injection** | A03:2021 Injection | Tampering | `display_name` input field | MEDIUM | MEDIUM | **HIGH** | Validate: 2-50 chars, alphanumeric + spaces/hyphens only. Sanitize on render (React escapes by default, verify). | **MUST-FIX** |
| **T-003** | **Weak admin JWT secret** | A02:2021 Cryptographic Failures | Elevation of Privilege | JWT signature validation | MEDIUM | CRITICAL | **CRITICAL** | Generate 256-bit secret: `openssl rand -hex 32`. Store in env var. Rotate every 90 days. | **MUST-FIX** |
| **T-004** | **localStorage XSS token theft** | A03:2021 Injection | Information Disclosure | Client token storage | MEDIUM | HIGH | **HIGH** | No full mitigation (XSS defense required). CSP headers: `default-src 'self'; script-src 'self'`. Monitor for XSS via input validation. | **SHOULD-FIX** |
| **T-005** | **Admin credential brute-force** | A07:2021 Identification and Authentication Failures | Spoofing | `/api/v2/auth/admin/login` | MEDIUM | CRITICAL | **HIGH** | Rate limit: 5 attempts per IP per 15 min. Lockout after 10 failed attempts (require password reset). Log all attempts. | **MUST-FIX** |
| **T-006** | **Manager role impersonation via JWT forgery** | A07:2021 Identification and Authentication Failures | Elevation of Privilege | `is_manager` claim in JWT | LOW | HIGH | **MEDIUM** | Depends on T-003 (strong secret). Add DB check: verify `players.is_manager=true` on approve/decline. | **SHOULD-FIX** |
| **T-007** | **Chip amount integer overflow** | A03:2021 Injection | Tampering | `amount` field in chip requests | LOW | MEDIUM | **MEDIUM** | Validate: 1 ≤ amount ≤ 1,000,000. Use signed 32-bit int max. Reject negative/zero/float values. | **SHOULD-FIX** |
| **T-008** | **Duplicate name collision (DoS/confusion)** | A04:2021 Insecure Design | Denial of Service | Player join name validation | HIGH | LOW | **MEDIUM** | Enforce unique names per game: check `players.display_name` + `game_id` before insert. Return 400 "Name taken". | **SHOULD-FIX** |
| **T-009** | **NoSQL injection in game_id parameter** | A03:2021 Injection | Tampering | All endpoints with `{game_id}` | LOW | HIGH | **MEDIUM** | Validate game_id is valid ObjectId hex (24 chars, [0-9a-f]). Use parameterized Motor queries (not string concat). | **SHOULD-FIX** |
| **T-010** | **Request ID enumeration** | A01:2021 Broken Access Control | Information Disclosure | Chip request IDs | LOW | LOW | **LOW** | Use UUID4 for `request_id` (not sequential integers). Already specified in T2 schema. | **ACCEPTED** |
| **T-011** | **CORS wildcard allows credential theft** | A05:2021 Security Misconfiguration | Information Disclosure | CORS middleware config | MEDIUM | HIGH | **HIGH** | Remove `origins=["*"]` from CORS. Whitelist: `["https://chipmate.app", "https://*.up.railway.app"]`. Never allow wildcard with credentials. | **MUST-FIX** |
| **T-012** | **Unencrypted HTTP traffic (dev)** | A02:2021 Cryptographic Failures | Information Disclosure | All API traffic in dev | MEDIUM (dev only) | MEDIUM | **MEDIUM** | Force HTTPS in production (Railway auto-enforces). Add HSTS header: `Strict-Transport-Security: max-age=31536000`. | **SHOULD-FIX** |
| **T-013** | **Token leakage in URL (if using query params)** | A04:2021 Insecure Design | Information Disclosure | Auth token transmission | LOW | MEDIUM | **LOW** | Use Authorization header (not query params). Already designed correctly. Verify no leakage in error logs. | **ACCEPTED** |
| **T-014** | **MongoDB exposed to network (if misconfigured)** | A05:2021 Security Misconfiguration | Tampering | MongoDB bind address | LOW | CRITICAL | **MEDIUM** | Bind to 127.0.0.1 only. Enable auth if remote access needed. Firewall rules: block port 27017 from internet. | **SHOULD-FIX** |
| **T-015** | **Session fixation (player token reuse)** | A07:2021 Identification and Authentication Failures | Spoofing | Player token lifecycle | LOW | MEDIUM | **LOW** | Accepted trade-off for multi-device support. No server-side session. Token valid until game close + 7 days. | **ACCEPTED** |
| **T-016** | **Repudiation: no audit trail for chip approvals** | A09:2021 Security Logging and Monitoring Failures | Repudiation | Manager actions | MEDIUM | MEDIUM | **MEDIUM** | Log to `admin_audit_log` collection: action, timestamp, manager_player_id, request_id, amount. Retention: 90 days. | **SHOULD-FIX** |
| **T-017** | **DoS via large chip request amounts** | A04:2021 Insecure Design | Denial of Service | Chip amount validation | MEDIUM | LOW | **LOW** | Max amount: 1,000,000. Reject higher values. No aggregation DoS risk (small games). | **ACCEPTED** |
| **T-018** | **Race condition in double-approval** | A04:2021 Insecure Design | Tampering | Approve endpoint idempotency | MEDIUM | MEDIUM | **MEDIUM** | Use optimistic locking: `update_one({_id, status: "PENDING"})`. If 0 modified, return 409 ALREADY_PROCESSED. | **SHOULD-FIX** |
| **T-019** | **Checkout amount manipulation (negative chips)** | A03:2021 Injection | Tampering | Checkout chip_count input | LOW | MEDIUM | **MEDIUM** | Validate: chip_count ≥ 0. Prevent negative/float values. Cross-check against expected range (warn if > bank.chips_in_play * 2). | **SHOULD-FIX** |
| **T-020** | **Credit debt forgery (player claims paid when not)** | A04:2021 Insecure Design | Repudiation | Settlement credit resolution | LOW | MEDIUM | **LOW** | Accepted risk (trust-based game). Audit log settlement actions. No cryptographic proof of payment. | **ACCEPTED** |
| **T-021** | **Auto-close bypass (24h expiry not enforced)** | A05:2021 Security Misconfiguration | Denial of Service | Background task or API check | MEDIUM | LOW | **LOW** | Implement as specified in T2: background task every 5 min OR API-level check on each request. | **ACCEPTED** |
| **T-022** | **Unvalidated redirect in QR code generation** | A01:2021 Broken Access Control | Tampering | QR join URL | LOW | LOW | **LOW** | Construct URL server-side. Never accept user-provided base URL. Hardcode `https://chipmate.app/join/{code}`. | **ACCEPTED** |

---

### 4.2 Risk Summary Matrix

| Risk Level | Count | Threat IDs |
|-----------|-------|-----------|
| **CRITICAL** | 1 | T-003 |
| **HIGH** | 5 | T-001, T-002, T-004, T-005, T-011 |
| **MEDIUM** | 11 | T-006, T-007, T-008, T-009, T-012, T-014, T-016, T-018, T-019 |
| **LOW** | 6 | T-010, T-013, T-015, T-017, T-020, T-021, T-022 |

---

## 5. Game Code Entropy Analysis

### 5.1 Current Design

**From T2 schema:**
- Length: 6 characters
- Character set: Uppercase alphanumeric `[A-Z0-9]`
- Total characters: 26 letters + 10 digits = 36
- Entropy: 36^6 = **2,176,782,336 combinations** (~2.2 billion)

### 5.2 Brute-Force Attack Scenarios

#### Scenario A: Online Brute-Force (No Rate Limiting)

**Assumptions:**
- Attacker queries `GET /api/v2/games/code/{code}` (public endpoint)
- Average response time: 100ms
- Attacker has 10 concurrent threads

**Attack rate:** 10 threads × 10 req/sec = 100 req/sec

**Time to exhaust 50% of keyspace (find 1 active game among ~100):**
- Active games at any time: ~100 (estimate)
- Search space to hit one: 2.2B / 100 = 22 million attempts (average)
- Time: 22,000,000 / 100 req/sec = 220,000 seconds = **61 hours**

**Verdict:** ⚠️ FEASIBLE if no rate limiting. An attacker can find an active game in ~3 days.

#### Scenario B: Online Brute-Force (With Rate Limiting)

**Mitigation:**
- Rate limit: 10 requests per IP per minute
- Block IP after 100 failed lookups per hour

**Attack rate:** 10 req/min = 0.17 req/sec

**Time to exhaust search space:** 22,000,000 / 0.17 = **4 years**

**Verdict:** ✅ INFEASIBLE with rate limiting.

#### Scenario C: Rainbow Table Precomputation

**Assumptions:**
- Attacker precomputes all 2.2B codes offline
- Monitors network traffic or uses leaked database dump

**Verdict:** ⚠️ POSSIBLE but requires significant resources (DB leak). Entropy alone insufficient; must rely on access control.

### 5.3 Recommendations

| Aspect | Recommendation | Priority |
|--------|---------------|----------|
| **Minimum Length** | APPROVED: 6 characters sufficient with rate limiting. | ✅ |
| **Character Set** | APPROVED: [A-Z0-9] (36 chars). Could increase to [A-Za-z0-9] (62 chars, 56B combinations) for defense-in-depth, but not critical. | OPTIONAL |
| **Rate Limiting** | CRITICAL: 10 req/min per IP on code lookup. Block after 100 failures/hour. | **MUST-FIX** |
| **Code Uniqueness** | APPROVED: Partial unique index on `games.code` where `status IN ["OPEN", "SETTLING"]` (per T2). | ✅ |
| **Code Expiry** | APPROVED: Codes reusable after game CLOSED. No collision risk with partial index. | ✅ |
| **Code Display** | Use monospace font, letter-spacing for visual clarity (per T1). Announce character-by-character to screen readers. | ✅ |

**Final Verdict:** ✅ APPROVED with mandatory rate limiting implementation.

---

## 6. Input Validation Requirements

### 6.1 Comprehensive Input Validation Matrix

| Input Field | Endpoint | Type | Validation Rules | Sanitization | Error Message | Priority |
|------------|----------|------|-----------------|--------------|---------------|----------|
| **display_name** | Player join, Game creation | String | Length: 2-50. Regex: `^[A-Za-z0-9 \-']+$`. Trim whitespace. | Strip HTML tags. Escape on render (React auto-escapes). | "Name must be 2-50 characters and contain only letters, numbers, spaces, hyphens, and apostrophes." | **CRITICAL** |
| **game_code** | Code lookup | String | Length: 4-6 (allow 4 for flexibility). Uppercase. Regex: `^[A-Z0-9]{4,6}$`. | Uppercase transformation. | "Invalid game code format." | **HIGH** |
| **amount** (chip request) | Create chip request, Approve/edit | Integer | Range: 1 to 1,000,000. Type: int (no float). | Cast to int. Reject NaN/Infinity. | "Amount must be a positive integer between 1 and 1,000,000." | **HIGH** |
| **game_id** | All game-scoped endpoints | String | Length: 24. Regex: `^[0-9a-f]{24}$` (ObjectId hex). | None. | "Invalid game ID format." | **HIGH** |
| **player_id** | Player-scoped endpoints | String | Format: UUID4. Regex: `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (lowercase). | Lowercase transformation. | "Invalid player ID format." | **MEDIUM** |
| **username** (admin) | Admin login | String | Length: 3-50. Regex: `^[a-zA-Z0-9_]+$`. | None. | "Invalid username." | **HIGH** |
| **password** (admin) | Admin login | String | Length: 12-128. No additional regex (support special chars). | None (never log). | "Invalid password." | **HIGH** |
| **chip_count** (checkout) | Checkout player | Integer | Range: 0 to 10,000,000. Type: int. | Cast to int. | "Chip count must be a non-negative integer." | **MEDIUM** |
| **settlement_method** | Settle credit debt | String | Length: 1-100. Regex: `^[A-Za-z0-9 \-()]+$` (e.g., "Venmo", "Cash"). | Trim. | "Settlement method must be 1-100 characters." | **LOW** |
| **note** (chip request) | Optional note on request | String | Length: 0-500. | Strip HTML. Escape on render. | "Note must be 500 characters or less." | **LOW** |
| **request_type** | Create chip request | Enum | Values: "CASH" or "CREDIT" (case-sensitive). | Uppercase transformation. | "Request type must be CASH or CREDIT." | **HIGH** |
| **status** (game status filter) | Admin game list | Enum | Values: "OPEN", "SETTLING", "CLOSED". | Uppercase transformation. | "Invalid status value." | **MEDIUM** |

### 6.2 Validation Implementation Strategy

**Pydantic v2 Models (Recommended for FastAPI):**

```python
from pydantic import BaseModel, Field, field_validator
import re

class PlayerJoinRequest(BaseModel):
    player_name: str = Field(min_length=2, max_length=50)

    @field_validator('player_name')
    def validate_name(cls, v):
        v = v.strip()
        if not re.match(r'^[A-Za-z0-9 \-\']+$', v):
            raise ValueError('Name contains invalid characters')
        return v

class ChipRequestCreate(BaseModel):
    type: Literal["CASH", "CREDIT"]
    amount: int = Field(ge=1, le=1_000_000)
    note: Optional[str] = Field(default=None, max_length=500)
```

**Flask Validation (Current Implementation):**

```python
from flask import request, jsonify

def validate_player_name(name):
    if not isinstance(name, str):
        return False, "Name must be a string"
    name = name.strip()
    if not 2 <= len(name) <= 50:
        return False, "Name must be 2-50 characters"
    if not re.match(r'^[A-Za-z0-9 \-\']+$', name):
        return False, "Name contains invalid characters"
    return True, name

@app.route('/api/games/join', methods=['POST'])
def join_game():
    data = request.get_json()
    user_name = data.get('user_name', '').strip()

    valid, result = validate_player_name(user_name)
    if not valid:
        return jsonify({'error': result}), 400

    # ... proceed with validated name
```

### 6.3 SQL/NoSQL Injection Prevention

**MongoDB Injection Risks:**

Unlike SQL, MongoDB injection is less common but still possible via operator injection:

```python
# VULNERABLE:
db.games.find({"code": code})  # If code = {"$ne": null}, returns all games

# SAFE:
db.games.find_one({"code": str(code)})  # Cast to string
```

**Mitigation Checklist:**

- ✅ Use Motor parameterized queries (NOT string concatenation)
- ✅ Validate all IDs are proper ObjectId format before query
- ✅ Cast user inputs to expected types (str, int) before query
- ✅ Never pass raw request dicts to MongoDB queries
- ⚠️ **Current Flask code DOES use direct queries but casts user_id to int** (line 331: `user_id = int(data.get('user_id'))`). This is SAFE for integer fields but NOT for string fields like game_code. **Must add validation.**

**Verdict:** Add validation wrappers for all user inputs before database queries.

---

## 7. Must-Fix Items

### Critical Issues That Block Public Launch

| ID | Issue | OWASP | Impact | Implementation Effort | Deadline |
|----|-------|-------|--------|---------------------|----------|
| **MF-1** | **Generate Strong Admin JWT Secret** | A02:2021 | CRITICAL | LOW (1 hour) | Before launch |
| **MF-2** | **Implement Rate Limiting on Code Lookup** | A01:2021 | HIGH | MEDIUM (4 hours) | Before launch |
| **MF-3** | **Fix CORS Wildcard Configuration** | A05:2021 | HIGH | LOW (1 hour) | Before launch |

### Critical Issue Details

#### MF-1: Generate Strong Admin JWT Secret

**Current State:**
- JWT secret not specified in code
- No documented generation process
- Current Flask code does NOT issue JWTs for admin login (line 69-82 returns user object, not token)

**Required Actions:**

1. Generate 256-bit secret:
   ```bash
   openssl rand -hex 32
   ```
   Output example: `f3d8e1c2a9b4f6e8d3c1a7b9e4f2c8d5a1b7e9f3c6d4a8e2b5c9f1d6a3e7b4c8`

2. Store in environment variable:
   ```bash
   # .env
   ADMIN_JWT_SECRET=f3d8e1c2a9b4f6e8d3c1a7b9e4f2c8d5a1b7e9f3c6d4a8e2b5c9f1d6a3e7b4c8
   ```

3. Implement JWT generation in login endpoint:
   ```python
   import jwt
   from datetime import datetime, timedelta, timezone

   @app.route('/api/auth/admin/login', methods=['POST'])
   def admin_login():
       # ... authenticate ...

       payload = {
           "user_id": "admin",
           "role": "ADMIN",
           "exp": datetime.now(timezone.utc) + timedelta(hours=24)
       }

       token = jwt.encode(payload, os.getenv('ADMIN_JWT_SECRET'), algorithm='HS256')

       return jsonify({
           'access_token': token,
           'token_type': 'Bearer',
           'user': { 'user_id': 'admin', 'role': 'ADMIN' }
       })
   ```

4. Implement validation middleware:
   ```python
   from functools import wraps

   def require_admin(f):
       @wraps(f)
       def decorated_function(*args, **kwargs):
           auth_header = request.headers.get('Authorization')
           if not auth_header or not auth_header.startswith('Bearer '):
               return jsonify({'error': 'Missing or invalid authorization header'}), 401

           token = auth_header.split(' ')[1]
           try:
               payload = jwt.decode(token, os.getenv('ADMIN_JWT_SECRET'), algorithms=['HS256'])
               if payload.get('role') != 'ADMIN':
                   return jsonify({'error': 'Admin access required'}), 403
               request.admin_context = payload
           except jwt.ExpiredSignatureError:
               return jsonify({'error': 'Token expired'}), 401
           except jwt.InvalidTokenError:
               return jsonify({'error': 'Invalid token'}), 401

           return f(*args, **kwargs)
       return decorated_function

   @app.route('/api/admin/games', methods=['GET'])
   @require_admin
   def list_all_games():
       # ... implementation ...
   ```

**Acceptance Criteria:**
- Secret is 256 bits (64 hex characters)
- Secret stored in environment variable (not hardcoded)
- JWT generated on admin login with 24h expiry
- All admin endpoints validate JWT

---

#### MF-2: Implement Rate Limiting on Code Lookup

**Current State:**
- No rate limiting in Flask app (line 30: `CORS(app, origins=["*"])` only)
- Public endpoint `/api/games/code/{code}` (Flask: line 308) is unprotected

**Required Actions:**

1. Install Flask-Limiter:
   ```bash
   pip install Flask-Limiter
   ```

2. Configure rate limiter:
   ```python
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address

   limiter = Limiter(
       app=app,
       key_func=get_remote_address,
       default_limits=["100 per minute"],  # Global default
       storage_uri="memory://"  # Use Redis in production: "redis://localhost:6379"
   )
   ```

3. Apply specific limits to vulnerable endpoints:
   ```python
   @app.route('/api/games/code/<game_code>/link', methods=['GET'])
   @limiter.limit("10 per minute")  # Strict limit on code lookup
   def generate_game_link(game_code):
       # ... implementation ...

   @app.route('/api/auth/admin/login', methods=['POST'])
   @limiter.limit("5 per 15 minutes")  # Brute-force protection
   def admin_login():
       # ... implementation ...

   @app.route('/api/games/join', methods=['POST'])
   @limiter.limit("10 per hour")  # Spam protection
   def join_game():
       # ... implementation ...
   ```

4. Add IP blocking for persistent attackers:
   ```python
   from collections import defaultdict
   from datetime import datetime, timedelta

   # In-memory store (use Redis for multi-instance)
   failed_lookups = defaultdict(list)

   @app.before_request
   def check_blocked_ip():
       client_ip = request.remote_addr

       # Clean old entries
       failed_lookups[client_ip] = [
           t for t in failed_lookups[client_ip]
           if t > datetime.now() - timedelta(hours=1)
       ]

       # Block if > 100 failures in last hour
       if len(failed_lookups[client_ip]) >= 100:
           return jsonify({'error': 'Too many failed requests. Blocked for 1 hour.'}), 429

   @app.route('/api/games/code/<game_code>/link', methods=['GET'])
   @limiter.limit("10 per minute")
   def generate_game_link(game_code):
       # ... code lookup ...

       if not game:
           # Record failed lookup
           client_ip = request.remote_addr
           failed_lookups[client_ip].append(datetime.now())
           return jsonify({'error': 'Game not found'}), 404

       # ... return game ...
   ```

**Acceptance Criteria:**
- Code lookup endpoint: 10 requests/min per IP
- Admin login: 5 requests/15min per IP
- Player join: 10 requests/hour per IP
- IP blocked after 100 failed code lookups in 1 hour
- Rate limit headers returned: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

#### MF-3: Fix CORS Wildcard Configuration

**Current State:**
- Line 30 in Flask app: `CORS(app, origins=["https://chipmate.up.railway.app", "*"])`
- Wildcard `"*"` allows ANY origin, defeating CORS security

**Security Implication:**
- An attacker hosts malicious site at `https://evil.com`
- Victim visits evil.com while logged into ChipMate
- Malicious JS reads victim's localStorage (player token) via `window.localStorage`
- Malicious JS sends token to attacker's server
- Attacker joins victim's games, manipulates chip requests

**Required Actions:**

1. Remove wildcard from CORS origins:
   ```python
   # BEFORE (VULNERABLE):
   CORS(app, origins=["https://chipmate.up.railway.app", "*"])

   # AFTER (SECURE):
   ALLOWED_ORIGINS = [
       "https://chipmate.app",
       "https://www.chipmate.app",
       "https://chipmate.up.railway.app",  # Production
       "https://*.up.railway.app"  # Preview deployments (Railway specific)
   ]

   if os.getenv('FLASK_ENV') == 'development':
       ALLOWED_ORIGINS.extend([
           "http://localhost:3000",  # React dev server
           "http://localhost:5173",  # Vite dev server
           "http://127.0.0.1:3000",
           "http://127.0.0.1:5173"
       ])

   CORS(app, origins=ALLOWED_ORIGINS)
   ```

2. Configure CORS headers properly:
   ```python
   CORS(
       app,
       origins=ALLOWED_ORIGINS,
       allow_credentials=True,  # Allow cookies (future use)
       allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
       allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
       expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
       max_age=600  # Cache preflight for 10 minutes
   )
   ```

3. Add origin validation function (for wildcard subdomain support):
   ```python
   def is_valid_origin(origin):
       """Validate origin matches allowed patterns"""
       if origin in ALLOWED_ORIGINS:
           return True

       # Allow Railway preview deployments: https://*.up.railway.app
       if origin.startswith("https://") and origin.endswith(".up.railway.app"):
           return True

       return False

   # Use in custom CORS handler if needed
   ```

**Acceptance Criteria:**
- No wildcard `"*"` in CORS origins
- Production origins: `chipmate.app`, `www.chipmate.app`
- Development origins: `localhost:3000`, `localhost:5173` (env-gated)
- Railway preview URLs: `*.up.railway.app` (validated)
- `allow_credentials=True` (for future cookie support)
- Preflight cache: 600 seconds

---

## 8. Dependency Risk Assessment

### 8.1 Critical Dependencies

**From `/Users/b/Documents/GitHub/ChipMate/requirements.txt`:**

```
pymongo
dnspython
pydantic==2.7.0
qrcode[pil]==8.2
pillow>=9.1.0
flask==3.0.0
flask-cors==4.0.0
gunicorn==21.2.0
python-dotenv==1.0.0
requests==2.31.0
pytest
mongomock
```

### 8.2 Vulnerability Scan Results

**As of 2026-01-30:**

| Package | Version | Known Vulnerabilities | CVE | Severity | Remediation |
|---------|---------|----------------------|-----|----------|-------------|
| **Pillow** | >=9.1.0 (unpinned) | CVE-2023-50447 (fixed in 10.2.0) | CVE-2023-50447 | HIGH | Pin to `pillow>=10.2.0` |
| **requests** | 2.31.0 | CVE-2023-32681 (fixed in 2.31.0) | N/A | N/A | No action (already patched) |
| **flask** | 3.0.0 | No known CVEs | N/A | N/A | Keep updated |
| **flask-cors** | 4.0.0 | No known CVEs | N/A | N/A | Keep updated |
| **gunicorn** | 21.2.0 | No known CVEs | N/A | N/A | Keep updated |
| **pydantic** | 2.7.0 (pinned) | No known CVEs | N/A | N/A | Upgrade to 2.9.x (latest) |
| **pymongo** | Unpinned (latest) | No known CVEs in recent versions | N/A | N/A | Pin to specific version: `pymongo==4.6.1` |

**Recommendations:**

1. **Pin all dependencies to specific versions:**
   ```
   pymongo==4.6.1
   dnspython==2.6.1
   pydantic==2.9.2
   qrcode[pil]==8.2
   pillow==10.2.0
   flask==3.0.3
   flask-cors==4.0.0
   gunicorn==21.2.0
   python-dotenv==1.0.1
   requests==2.31.0
   pytest==7.4.4
   mongomock==4.1.2
   ```

2. **Add Flask-Limiter for rate limiting:**
   ```
   Flask-Limiter==3.5.0
   ```

3. **Add PyJWT for JWT handling:**
   ```
   PyJWT==2.8.0
   ```

4. **Run vulnerability scans regularly:**
   ```bash
   pip install safety
   safety check --json > safety_report.json
   ```

5. **Set up automated dependency updates:**
   - Use Dependabot (GitHub) or Renovate Bot
   - Configure to create PRs for security updates automatically
   - Run CI tests on all dependency update PRs

**Acceptance Criteria:**
- All dependencies pinned to specific versions
- No HIGH or CRITICAL severity CVEs
- Automated vulnerability scanning in CI pipeline
- Monthly dependency review process

---

### 8.3 Supply Chain Attack Risks

| Risk | Description | Mitigation | Priority |
|------|-------------|-----------|----------|
| **Malicious package substitution** | Attacker publishes fake `pymongo` as `py-mongo` | Use `pip install --require-hashes` with hash verification | MEDIUM |
| **Compromised package maintainer** | Legitimate package hijacked (e.g., event-stream incident) | Pin versions, monitor security advisories, review changelogs before updates | MEDIUM |
| **Typosquatting** | Install `reqeusts` instead of `requests` | Use virtual environment, review `pip freeze` output | LOW |
| **Private package repository MITM** | Attacker intercepts PyPI traffic | Use HTTPS for PyPI (default), verify TLS certificates | LOW |

**Best Practices:**
- Use virtual environment (`venv`) to isolate dependencies
- Generate `requirements.txt` from `pip freeze` (lock exact versions)
- Use `pip-audit` to check for known vulnerabilities
- Review dependency tree for unexpected packages: `pip list`

---

## 9. HTTPS Enforcement Strategy

### 9.1 Railway Production Deployment

**Railway Automatic HTTPS:**
- Railway provides automatic TLS termination at the edge
- All `*.up.railway.app` domains have valid Let's Encrypt certificates
- Custom domains (`chipmate.app`) can be added with automatic cert provisioning

**Required Configuration:**

1. **Custom Domain Setup (Railway Dashboard):**
   ```
   Domains → Add Custom Domain → chipmate.app
   Railway auto-generates TLS cert via Let's Encrypt
   DNS: Add CNAME record: chipmate.app → <project>.up.railway.app
   ```

2. **Force HTTPS Redirect (Application Level):**
   ```python
   from flask import request, redirect

   @app.before_request
   def force_https():
       if os.getenv('RAILWAY_ENVIRONMENT') == 'production':
           if request.headers.get('X-Forwarded-Proto') != 'https':
               return redirect(request.url.replace('http://', 'https://'), code=301)
   ```

3. **Add HSTS Header (HTTP Strict Transport Security):**
   ```python
   @app.after_request
   def add_security_headers(response):
       if os.getenv('RAILWAY_ENVIRONMENT') == 'production':
           response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
           response.headers['X-Content-Type-Options'] = 'nosniff'
           response.headers['X-Frame-Options'] = 'DENY'
           response.headers['X-XSS-Protection'] = '1; mode=block'
           response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
       return response
   ```

**HSTS Policy Details:**
- `max-age=31536000`: Browser remembers to use HTTPS for 1 year
- `includeSubDomains`: Apply to all subdomains (optional, ensure all subdomains support HTTPS)
- No `preload` directive initially (requires manual submission to HSTS preload list)

### 9.2 Development Environment

**Local Development (HTTP):**
- Use `http://localhost:5000` for backend
- Use `http://localhost:3000` for frontend
- This is acceptable for local development (no sensitive data in dev)

**Production-Like Local Testing (HTTPS):**

If testing HTTPS locally (e.g., for browser security feature testing):

1. Generate self-signed certificate:
   ```bash
   openssl req -x509 -newkey rsa:4096 -nodes \
     -keyout key.pem -out cert.pem -days 365 \
     -subj "/CN=localhost"
   ```

2. Run Flask with HTTPS:
   ```python
   if __name__ == '__main__':
       app.run(
           host='0.0.0.0',
           port=5000,
           debug=True,
           ssl_context=('cert.pem', 'key.pem')  # Dev only
       )
   ```

3. Browser will show certificate warning (expected for self-signed cert)

**Acceptance Criteria:**
- Production: All traffic over HTTPS (Railway enforced)
- HSTS header present in production
- No mixed content warnings (all assets loaded via HTTPS)
- Development: HTTP acceptable

---

### 9.3 Content Security Policy (CSP)

**Purpose:** Prevent XSS attacks by restricting resource loading.

**Recommended CSP Header:**

```python
@app.after_request
def add_security_headers(response):
    if os.getenv('RAILWAY_ENVIRONMENT') == 'production':
        # ... other headers ...

        csp_policy = "; ".join([
            "default-src 'self'",  # Only load from same origin
            "script-src 'self'",  # No inline scripts, no eval()
            "style-src 'self' 'unsafe-inline'",  # Allow inline styles (React)
            "img-src 'self' data: https:",  # Images from self, data URLs, HTTPS
            "font-src 'self'",
            "connect-src 'self' https://chipmate.up.railway.app",  # API calls
            "frame-ancestors 'none'",  # Prevent clickjacking
            "base-uri 'self'",
            "form-action 'self'"
        ])

        response.headers['Content-Security-Policy'] = csp_policy
    return response
```

**CSP Violations Monitoring:**

1. Add report-uri directive (optional):
   ```
   "report-uri https://chipmate.app/api/csp-report"
   ```

2. Log CSP violations:
   ```python
   @app.route('/api/csp-report', methods=['POST'])
   def csp_report():
       report = request.get_json()
       logger.warning(f"CSP violation: {report}")
       return '', 204
   ```

**Acceptance Criteria:**
- CSP header present in production
- No `'unsafe-eval'` in script-src
- No wildcard `*` in any directive
- CSP violations logged (optional report-uri)

---

## 10. Defense-in-Depth Recommendations

### 10.1 Application Layer Hardening

| Control | Description | Implementation | Priority |
|---------|-------------|---------------|----------|
| **Request ID Tracing** | Unique ID per request for audit trail | Generate UUID4 on request entry, include in all logs and error responses | HIGH |
| **Structured Logging** | JSON logs for SIEM integration | Use `python-json-logger`, include: timestamp, request_id, user_id, action, ip_address | HIGH |
| **API Versioning** | Prevent breaking changes | Use `/api/v2/` prefix (already specified in T3) | ✅ |
| **Error Message Sanitization** | No stack traces in production | Catch exceptions, return generic "Internal error" with request_id, log full trace | HIGH |
| **Input Length Limits** | Prevent buffer overflow DoS | Limit request body size: 1MB max. Reject oversized payloads | MEDIUM |
| **Idempotency Keys** | Prevent duplicate transactions on retry | Accept `X-Idempotency-Key` header, deduplicate within 24h window | MEDIUM |
| **Database Query Timeouts** | Prevent slow query DoS | Set MongoDB query timeout: 5 seconds max | LOW |
| **Connection Pooling** | Limit concurrent connections | Motor connection pool: max 100 connections | LOW |

**Idempotency Implementation Example:**

```python
from datetime import datetime, timedelta

idempotency_cache = {}  # Use Redis in production

@app.route('/api/games/<game_id>/chip-requests', methods=['POST'])
def create_chip_request(game_id):
    idempotency_key = request.headers.get('X-Idempotency-Key')

    if idempotency_key:
        # Check if request already processed
        cached_response = idempotency_cache.get(idempotency_key)
        if cached_response and cached_response['timestamp'] > datetime.now() - timedelta(hours=24):
            return jsonify(cached_response['response']), cached_response['status_code']

    # ... process request ...

    response_data = {'request_id': request_id, 'message': 'Request created'}

    if idempotency_key:
        idempotency_cache[idempotency_key] = {
            'response': response_data,
            'status_code': 201,
            'timestamp': datetime.now()
        }

    return jsonify(response_data), 201
```

### 10.2 Database Security

**MongoDB Security Checklist:**

| Control | Current State | Required Action | Priority |
|---------|--------------|----------------|----------|
| **Bind Address** | Default (listens on 0.0.0.0) | Bind to 127.0.0.1 only: `bindIp: 127.0.0.1` in mongod.conf | HIGH |
| **Authentication** | Disabled (local dev) | Enable auth for production: `--auth` flag, create admin user | MEDIUM |
| **TLS Encryption** | N/A (localhost) | Not needed for localhost; required if remote DB | N/A |
| **Firewall Rules** | Not specified | Block port 27017 from internet in Railway firewall | HIGH |
| **Connection String** | In environment variable | Use `MONGO_URL` env var (already done). Never hardcode. | ✅ |
| **Database Backups** | Not specified | Daily backups with 7-day retention (Railway add-on or manual) | MEDIUM |
| **Audit Logging** | Not enabled | Enable MongoDB audit log for production (Enterprise feature or manual) | LOW |

**Production MongoDB Authentication Setup (if using remote DB):**

```bash
# Connect to MongoDB
mongosh

# Create admin user
use admin
db.createUser({
  user: "chipmate_admin",
  pwd: "<strong-random-password>",
  roles: [ { role: "readWrite", db: "chipmate_v2" } ]
})

# Update connection string in Railway env vars
MONGO_URL=mongodb://chipmate_admin:<password>@localhost:27017/chipmate_v2?authSource=admin
```

### 10.3 Monitoring and Alerting

**Critical Metrics to Monitor:**

| Metric | Threshold | Alert Action |
|--------|-----------|--------------|
| **Error Rate** | > 1% of requests (5xx errors) | Alert on-call engineer |
| **Failed Login Attempts** | > 20 per IP per hour | Trigger IP investigation/block |
| **Code Lookup Failures** | > 100 per IP per hour | Auto-block IP |
| **Request Latency (P95)** | > 1000ms | Alert performance team |
| **MongoDB Connection Pool** | > 80% utilized | Scale up application instances |
| **Game Creation Rate** | > 100 per minute | Possible abuse, investigate |
| **Disk Space** | < 10% free | Expand storage |
| **Memory Usage** | > 85% | Investigate memory leak |

**Logging Requirements:**

1. **Security Events (HIGH priority):**
   - Admin login attempts (success/failure)
   - Failed JWT validation attempts
   - Rate limit violations
   - Failed game code lookups
   - Manager role actions (approve/decline/checkout)

2. **Audit Trail (MEDIUM priority):**
   - Game creation (game_id, manager_player_id, timestamp)
   - Player join (game_id, player_id, timestamp, ip_address)
   - Chip request lifecycle (created → approved/declined)
   - Checkout/settlement actions (player_id, amounts, timestamp)

3. **Performance Metrics (LOW priority):**
   - Request count per endpoint
   - Response time percentiles (P50, P95, P99)
   - Database query times

**Log Format (Structured JSON):**

```python
import logging
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'request_id': getattr(request, 'request_id', None),
            'user_id': getattr(request, 'user_id', None),
            'ip_address': request.remote_addr if request else None,
            'endpoint': request.path if request else None,
            'method': request.method if request else None
        }
        return json.dumps(log_data)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger('chipmate')
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

---

## 11. Incident Response Considerations

### 11.1 Attack Scenarios and Response Procedures

#### Scenario 1: JWT Secret Compromise

**Detection:**
- Unusual admin activity from unknown IPs
- Mass game deletions
- Admin API calls with valid tokens but suspicious patterns

**Response:**

1. **Immediate (< 5 minutes):**
   - Rotate JWT secret immediately (generate new secret, update env var, restart app)
   - All existing admin tokens invalidated automatically
   - Notify all admins to re-login

2. **Short-term (< 1 hour):**
   - Review admin_audit_log for unauthorized actions
   - Identify compromised time window
   - Restore deleted games from backups if necessary

3. **Long-term (< 1 week):**
   - Investigate how secret was leaked (code repo, logs, env var exposure)
   - Implement secret rotation policy (90-day automatic rotation)
   - Add monitoring for unusual admin activity patterns

---

#### Scenario 2: Game Code Brute-Force Attack

**Detection:**
- High rate of 404 responses on `/api/games/code/{code}` endpoint
- Single IP or distributed IPs systematically querying codes
- Rate limiter triggers (if implemented)

**Response:**

1. **Immediate (< 5 minutes):**
   - Verify rate limiting is active
   - Block attacking IPs via Railway network rules or application-level blocklist

2. **Short-term (< 1 hour):**
   - Analyze attack pattern (sequential, random, dictionary-based)
   - Identify if any games were successfully accessed
   - Notify affected game managers if breach confirmed

3. **Long-term (< 1 week):**
   - Increase code length from 6 to 8 characters (36^8 = 2.8 trillion combinations)
   - Implement CAPTCHA on join page (Google reCAPTCHA v3 for invisible challenge)
   - Add anomaly detection: flag IPs with >50% 404 rate on code lookups

---

#### Scenario 3: XSS Attack via Player Name

**Detection:**
- User reports unusual behavior (redirects, pop-ups)
- CSP violation reports (if CSP enabled)
- Stored XSS payload found in database (e.g., `<script>alert('XSS')</script>` in player name)

**Response:**

1. **Immediate (< 5 minutes):**
   - Identify malicious player name in database
   - Sanitize: Update affected player names: `db.players.updateMany({}, {$set: {name: sanitized_name}})`
   - Force logout affected players (delete tokens if possible, or notify to refresh)

2. **Short-term (< 1 hour):**
   - Deploy input validation fix (name regex enforcement)
   - Audit all existing player names for XSS patterns
   - Notify affected game managers

3. **Long-term (< 1 week):**
   - Implement CSP headers (prevent inline script execution)
   - Add automated XSS scanning in CI pipeline
   - Conduct security code review of all user input handling

---

#### Scenario 4: DDoS Attack (Distributed Denial of Service)

**Detection:**
- High request volume from many IPs
- Application latency spikes
- Railway monitoring alerts on bandwidth/CPU usage

**Response:**

1. **Immediate (< 5 minutes):**
   - Enable Railway DDoS protection (if available)
   - Increase rate limiting aggressiveness (e.g., 5 req/min instead of 10)
   - Identify attack pattern (specific endpoint targeted?)

2. **Short-term (< 1 hour):**
   - Implement IP-based blocking for attack sources
   - Enable Cloudflare (or similar CDN) for DDoS mitigation
   - Scale up application instances if needed (Railway auto-scaling)

3. **Long-term (< 1 week):**
   - Implement adaptive rate limiting (stricter limits during attack)
   - Set up anomaly detection (sudden traffic spikes)
   - Add CAPTCHA to resource-intensive endpoints (game creation)

---

### 11.2 Incident Response Contacts

| Role | Responsibility | Contact Method |
|------|---------------|---------------|
| **On-call Engineer** | First responder, triage, initial mitigation | Phone, Slack, PagerDuty |
| **Security Lead** | Incident assessment, coordinate response | Email, Slack |
| **Database Admin** | Backup/restore, query forensics | Email, Slack |
| **Infrastructure Team** | Network-level blocking, scaling | Slack, Railway support |
| **Product Owner** | User communication, business impact assessment | Email, Phone |

---

### 11.3 Post-Incident Review (PIR) Template

After any security incident:

1. **Incident Summary:**
   - Date/time of detection
   - Date/time of resolution
   - Affected systems/users
   - Attack vector

2. **Root Cause Analysis:**
   - What allowed the attack to succeed?
   - What controls failed?

3. **Actions Taken:**
   - Immediate response
   - Short-term fixes
   - Long-term improvements

4. **Lessons Learned:**
   - What worked well?
   - What could be improved?
   - New monitoring/alerting needed?

5. **Follow-up Action Items:**
   - Owner assigned for each item
   - Deadline for completion

---

## Appendix A: Security Checklist (Pre-Launch)

### Critical (Must-Fix Before Public Launch)

- [ ] Generate 256-bit JWT secret for admin auth
- [ ] Implement JWT generation and validation for admin login
- [ ] Implement rate limiting on game code lookup (10 req/min per IP)
- [ ] Implement rate limiting on admin login (5 req/15min per IP)
- [ ] Remove CORS wildcard, whitelist specific origins
- [ ] Migrate player ID generation from timestamp to UUID4
- [ ] Add input validation for player names (regex, length)
- [ ] Add input validation for chip amounts (range, type)
- [ ] Bind MongoDB to 127.0.0.1 (not 0.0.0.0)
- [ ] Configure HTTPS redirect in production
- [ ] Add HSTS header (Strict-Transport-Security)
- [ ] Pin all dependencies to specific versions (requirements.txt)
- [ ] Upgrade Pillow to >=10.2.0 (security patch)

### High Priority (Should-Fix Before Launch)

- [ ] Implement database-level is_manager verification (not just JWT)
- [ ] Add NoSQL injection prevention (validate game_id format)
- [ ] Implement optimistic locking for approve/decline (prevent race condition)
- [ ] Add audit logging for manager actions (approve, decline, checkout)
- [ ] Implement IP blocking after 100 failed code lookups
- [ ] Add CSP headers (Content-Security-Policy)
- [ ] Add security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- [ ] Implement idempotency keys for chip request creation
- [ ] Add request ID generation and logging
- [ ] Set up structured JSON logging

### Medium Priority (Post-Launch Hardening)

- [ ] Implement admin impersonation with audit trail
- [ ] Add JWT secret rotation policy (90 days)
- [ ] Enable MongoDB authentication (if using remote DB)
- [ ] Set up automated dependency scanning (Dependabot)
- [ ] Implement settlement action audit log
- [ ] Add monitoring/alerting for security events
- [ ] Set up daily database backups
- [ ] Implement checkout amount validation (sanity checks)
- [ ] Add CAPTCHA to game creation (prevent spam)
- [ ] Implement game code length increase to 8 characters

### Low Priority (Defense-in-Depth)

- [ ] Implement server-side JWT revocation list (optional)
- [ ] Add anomaly detection for unusual activity patterns
- [ ] Set up CSP violation reporting
- [ ] Implement MongoDB query timeouts
- [ ] Add database connection pooling limits
- [ ] Set up log aggregation (ELK stack or similar)
- [ ] Implement automated security testing in CI (SAST/DAST)
- [ ] Conduct external security audit/penetration test
- [ ] Implement network-level DDoS protection (Cloudflare)
- [ ] Add honeypot endpoints to detect attackers

---

## Appendix B: Code Review Findings (Current Implementation)

Based on analysis of `/Users/b/Documents/GitHub/ChipMate/src/api/web_api.py`:

### Security Issues Found

1. **Line 30: CORS Wildcard** ⚠️ CRITICAL
   ```python
   CORS(app, origins=["https://chipmate.up.railway.app", "*"])
   ```
   **Issue:** Wildcard allows any origin to make authenticated requests.
   **Fix:** Remove `"*"`, whitelist specific domains.

2. **Line 56-141: No JWT Generation** ⚠️ HIGH
   ```python
   def login():
       # ... authenticate ...
       return jsonify({'user': admin_user, 'message': 'Welcome, Admin!'})
   ```
   **Issue:** Admin login returns user object but no JWT token.
   **Fix:** Generate and return JWT with 24h expiry.

3. **Line 186-187: Weak Player ID Generation** ⚠️ HIGH
   ```python
   user_id = int(datetime.now().timestamp() * 1000)
   ```
   **Issue:** Timestamp-based ID is predictable (not cryptographically random).
   **Fix:** Use `uuid.uuid4()` for player ID.

4. **Line 180-181: No Input Validation on Game Code** ⚠️ MEDIUM
   ```python
   code = data.get('code', '').strip().upper()
   # No regex validation
   ```
   **Issue:** Allows arbitrary input, possible injection.
   **Fix:** Validate with regex `^[A-Z0-9]{4,6}$`.

5. **Line 149: No Input Validation on Host Name** ⚠️ MEDIUM
   ```python
   host_name = data.get('host_name', '').strip()
   # No length or character validation
   ```
   **Issue:** Allows XSS payloads, long strings.
   **Fix:** Validate length (2-50) and allowed characters.

6. **No Rate Limiting** ⚠️ CRITICAL
   **Issue:** All endpoints vulnerable to brute-force and DDoS.
   **Fix:** Implement Flask-Limiter.

7. **No Request ID Tracing** ⚠️ MEDIUM
   **Issue:** Cannot correlate logs for debugging or security investigation.
   **Fix:** Generate UUID per request, include in logs and responses.

8. **No HSTS or CSP Headers** ⚠️ MEDIUM
   **Issue:** No defense against protocol downgrade or XSS.
   **Fix:** Add security headers in `@app.after_request`.

### Positive Security Practices Found

1. ✅ **Environment variable for MongoDB URL** (line 25)
2. ✅ **CORS middleware enabled** (needs fix, but present)
3. ✅ **Type casting for user inputs** (lines 331, 338: `int()` casting prevents type confusion)
4. ✅ **Error handling with try/except blocks** (prevents info leakage via stack traces)
5. ✅ **Logging errors without exposing sensitive data** (uses generic error messages)

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **STRIDE** | Threat modeling framework: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege |
| **JWT** | JSON Web Token - cryptographically signed token for stateless authentication |
| **XSS** | Cross-Site Scripting - injection attack where malicious scripts execute in victim's browser |
| **CSRF** | Cross-Site Request Forgery - attack where authenticated user performs unintended action |
| **CORS** | Cross-Origin Resource Sharing - browser security mechanism controlling cross-domain requests |
| **HSTS** | HTTP Strict Transport Security - header forcing browsers to use HTTPS |
| **CSP** | Content Security Policy - header restricting resource loading to prevent XSS |
| **NoSQL Injection** | Attack injecting malicious query operators into database queries |
| **Idempotency** | Property where repeating an operation produces same result (prevents double-processing) |
| **Rate Limiting** | Restricting number of requests per time window to prevent abuse |
| **Entropy** | Measure of randomness/unpredictability (higher is more secure) |

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Security Engineer + AI Threat Modeling Agent | Initial comprehensive threat model |

---

**End of Document**

**Next Actions:**
1. Review this threat model with engineering team
2. Prioritize and assign must-fix items
3. Create Jira/Linear tickets for each mitigation
4. Implement critical fixes before public launch
5. Schedule follow-up security audit after deployment
