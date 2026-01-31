# T5: Test Strategy and Test Case Matrix

**Ticket:** T5
**Author:** QA Manager
**Date:** 2026-01-30
**Status:** PROPOSED
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Test Strategy](#2-test-strategy)
3. [Test Levels and Tools](#3-test-levels-and-tools)
4. [Coverage Targets](#4-coverage-targets)
5. [Test Data Strategy](#5-test-data-strategy)
6. [CI Integration](#6-ci-integration)
7. [Test Case Matrix](#7-test-case-matrix)
8. [P0 Critical Path Tests](#8-p0-critical-path-tests)
9. [Edge Case Tests](#9-edge-case-tests)
10. [Negative Tests](#10-negative-tests)
11. [Coverage Mapping to Acceptance Criteria](#11-coverage-mapping-to-acceptance-criteria)
12. [Test Environment Configuration](#12-test-environment-configuration)

---

## 1. Executive Summary

This document defines the comprehensive test strategy for ChipMate v2, a mobile-first web application for managing live poker games. The strategy covers all test levels (unit, integration, component, E2E) and provides a complete test case matrix ensuring coverage of all user stories, edge cases, and failure scenarios.

### Risk Assessment

| Risk Area | Severity | Mitigation |
|-----------|----------|------------|
| Credit-debt calculation errors | CRITICAL | P0 unit tests + E2E checkout flow tests |
| Auth token validation bypass | CRITICAL | P0 security tests for all endpoints |
| Race conditions in approvals | HIGH | Concurrent request tests with pessimistic locking validation |
| 24h auto-close failures | HIGH | Scheduled task tests + fallback validation |
| Polling notification delays | MEDIUM | Polling interval tests + timeout scenarios |
| Mobile browser compatibility | MEDIUM | Cross-browser E2E tests on BrowserStack |

### Quality Gates

| Gate | Requirement | Enforcement |
|------|-------------|-------------|
| Code merged to main | Backend unit tests 80% coverage, all P0 tests pass | GitHub Actions check |
| Pull request approval | No failing tests, no regressions | Automated + manual review |
| Deployment to staging | All E2E tests pass | Railway pre-deployment hook |
| Production release | Load tests pass, security scan clean | Manual approval required |

---

## 2. Test Strategy

### 2.1 Test Pyramid Distribution

```
                  /\
                 /  \  E2E (10%)
                /____\
               /      \  Integration (30%)
              /________\
             /          \  Unit (60%)
            /____________\
```

**Rationale:** Mobile-first app with backend business logic requires strong unit test coverage for calculation correctness, integration tests for API contracts, and focused E2E tests for critical user journeys.

### 2.2 Testing Principles

1. **Test behavior, not implementation** - Focus on API contracts and user-observable outcomes
2. **Deterministic tests** - No flaky tests; all tests must be repeatable
3. **Fast feedback** - Unit tests run in <5s, full suite in <2min
4. **Realistic test data** - Use production-like scenarios (typical game: 6 players, 15 chip requests)
5. **Fail fast** - P0 tests run first in CI pipeline
6. **Clear test names** - Format: `test_<scenario>_<expected_outcome>`

### 2.3 What We Test

| Category | Scope | Priority |
|----------|-------|----------|
| Business logic correctness | Credit calculations, P/L, checkout ordering | P0 |
| State transitions | Game states (OPEN → SETTLING → CLOSED), request states | P0 |
| Auth and authorization | Token validation, role-based access control | P0 |
| Input validation | Malformed requests, boundary conditions | P1 |
| Error handling | Network failures, database errors, race conditions | P1 |
| Performance | Response times, concurrent users | P2 |
| Mobile UX | Touch targets, responsive layout, offline handling | P2 |

### 2.4 What We Don't Test

- MongoDB internals (assume driver works correctly)
- Third-party libraries (pytest, FastAPI, React tested by maintainers)
- Browser rendering engine bugs
- Network infrastructure (SSL, DNS, CDN)

---

## 3. Test Levels and Tools

### 3.1 Backend Unit Tests (pytest)

**Scope:** Individual functions, business logic, calculations

**Location:** `src/tests/unit/`

**Tools:**
- pytest 8.0+ (test runner)
- pytest-asyncio (async test support)
- pytest-cov (coverage reporting)
- freezegun (datetime mocking)
- mongomock (lightweight MongoDB mock)

**Example test:**

```python
# src/tests/unit/test_checkout_calculations.py

from src.services.checkout_service import calculate_checkout_breakdown

def test_checkout_with_credit_repayment():
    """Player with credit debt repays from chips first."""
    result = calculate_checkout_breakdown(
        final_chips=250,
        total_cash_in=150,
        total_credit_in=100,
        credits_owed=100
    )

    assert result["credits_repaid"] == 100
    assert result["remaining_credits"] == 0
    assert result["cash_out"] == 200  # 250 chips - 50 repaid = 200
    assert result["net_profit_loss"] == 0  # 250 - (150+100) = 0
```

### 3.2 Backend Integration Tests (pytest + TestClient)

**Scope:** API endpoint contracts, database interactions, multi-component flows

**Location:** `src/tests/integration/`

**Tools:**
- pytest
- FastAPI TestClient (in-process HTTP client)
- Test MongoDB instance (Docker container)
- Factory pattern (factory_boy or custom fixtures)

**Example test:**

```python
# src/tests/integration/test_chip_request_flow.py

async def test_approve_chip_request_updates_bank(test_client, db, game_factory, player_factory):
    """Approving a cash request updates game bank and player balance."""
    game = await game_factory(status="OPEN")
    manager = await player_factory(game_id=game["_id"], is_manager=True)
    player = await player_factory(game_id=game["_id"])

    # Create pending request
    response = await test_client.post(
        f"/api/v2/games/{game['_id']}/chip-requests",
        json={"type": "CASH", "amount": 100},
        headers={"Authorization": f"Bearer {player['token']}"}
    )
    request_id = response.json()["request_id"]

    # Approve as manager
    response = await test_client.post(
        f"/api/v2/games/{game['_id']}/chip-requests/{request_id}/approve",
        headers={"Authorization": f"Bearer {manager['token']}"}
    )

    assert response.status_code == 200

    # Verify bank updated
    game_updated = await db.games.find_one({"_id": game["_id"]})
    assert game_updated["bank"]["cash_balance"] == 100
    assert game_updated["bank"]["total_cash_in"] == 100
    assert game_updated["bank"]["chips_in_play"] == 100
```

### 3.3 Frontend Component Tests (Vitest + React Testing Library)

**Scope:** React component rendering, user interactions, state management

**Location:** `frontend/src/components/__tests__/`

**Tools:**
- Vitest (test runner)
- React Testing Library (DOM testing utilities)
- MSW (Mock Service Worker for API mocking)
- user-event (simulate user interactions)

**Example test:**

```javascript
// frontend/src/components/__tests__/ChipRequestSheet.test.tsx

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChipRequestSheet } from '../ChipRequestSheet';

test('submits cash chip request with valid amount', async () => {
  const onSubmit = vi.fn();
  render(<ChipRequestSheet gameId="abc123" onSubmit={onSubmit} />);

  const user = userEvent.setup();

  // Select cash type
  await user.click(screen.getByRole('button', { name: /cash/i }));

  // Enter amount
  const amountInput = screen.getByLabelText(/chip amount/i);
  await user.type(amountInput, '100');

  // Submit
  await user.click(screen.getByRole('button', { name: /send request/i }));

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith({
      type: 'CASH',
      amount: 100
    });
  });
});
```

### 3.4 End-to-End Tests (Playwright)

**Scope:** Complete user journeys across frontend and backend

**Location:** `e2e/tests/`

**Tools:**
- Playwright (browser automation)
- playwright-test (test runner with fixtures)
- Docker Compose (test environment orchestration)

**Example test:**

```javascript
// e2e/tests/critical-path.spec.ts

import { test, expect } from '@playwright/test';

test('complete game lifecycle: create → join → request → approve → checkout', async ({ page, context }) => {
  // Manager creates game
  await page.goto('/');
  await page.click('text=New Game');
  await page.fill('input[name="managerName"]', 'Alice');
  await page.click('button:has-text("Create Game")');

  await expect(page.locator('text=Game Code:')).toBeVisible();
  const gameCode = await page.locator('[data-testid="game-code"]').textContent();

  // Player joins in new tab
  const playerPage = await context.newPage();
  await playerPage.goto(`/join?code=${gameCode}`);
  await playerPage.fill('input[name="playerName"]', 'Bob');
  await playerPage.click('button:has-text("Join Game")');

  // Player requests chips
  await playerPage.click('button:has-text("Request Chips")');
  await playerPage.fill('input[inputmode="numeric"]', '100');
  await playerPage.click('button:has-text("Send Request")');

  await expect(playerPage.locator('text=Request sent')).toBeVisible();

  // Manager sees and approves
  await page.waitForSelector('text=1 Pending Request');
  await page.click('text=Pending Requests');
  await page.click('[data-testid="approve-btn"]');

  await expect(page.locator('text=Approved 100')).toBeVisible();

  // Player sees approval notification
  await expect(playerPage.locator('text=approved')).toBeVisible();
});
```

---

## 4. Coverage Targets

### 4.1 Code Coverage

| Component | Metric | Target | Enforcement |
|-----------|--------|--------|-------------|
| Backend services | Line coverage | 80% | Codecov PR check |
| Backend API routes | Line coverage | 70% | Codecov PR check |
| Backend DAL | Line coverage | 75% | Codecov PR check |
| Frontend components | Line coverage | 70% | Codecov PR check |
| Frontend utilities | Line coverage | 80% | Codecov PR check |

**Rationale:** Services contain critical business logic (credit calculations, state machines) and require highest coverage. API routes are thinner and allow slightly lower target.

### 4.2 Functional Coverage

**All acceptance criteria from T1-T21 must have at least one mapped test case.**

Coverage mapping documented in Section 11.

### 4.3 Edge Case Coverage

**All documented edge cases from T1 User Flows must have explicit tests:**

- Duplicate join attempt
- Request after SETTLING
- 24h auto-close
- Checkout with zero chips
- On-behalf-of for non-existent player
- Manager impersonation

### 4.4 Error Scenario Coverage

**All error codes from T3 API Contract must have at least one test:**

- 400 errors (10 codes): INVALID_INPUT, INVALID_AMOUNT, DUPLICATE_NAME, etc.
- 401 errors (5 codes): UNAUTHORIZED, INVALID_TOKEN, EXPIRED_TOKEN, etc.
- 403 errors (3 codes): FORBIDDEN, ADMIN_REQUIRED, MANAGER_CANNOT_LEAVE
- 404 errors (4 codes): GAME_NOT_FOUND, PLAYER_NOT_FOUND, etc.
- 409 errors (8 codes): GAME_NOT_JOINABLE, ALREADY_PROCESSED, etc.

Total: 30 error scenarios to test.

---

## 5. Test Data Strategy

### 5.1 Factory Pattern (Backend)

Use factory pattern to create realistic test data with sensible defaults and easy customization.

```python
# src/tests/fixtures/factories.py

from datetime import datetime, timezone, timedelta
import uuid
from bson import ObjectId

class GameFactory:
    @staticmethod
    async def create(db, **overrides):
        game = {
            "_id": ObjectId(),
            "code": overrides.get("code", "TEST01"),
            "status": overrides.get("status", "OPEN"),
            "manager_player_token": overrides.get("manager_player_token", str(uuid.uuid4())),
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            "bank": {
                "cash_balance": 0,
                "total_cash_in": 0,
                "total_cash_out": 0,
                "total_credits_issued": 0,
                "total_credits_repaid": 0,
                "total_chips_issued": 0,
                "total_chips_returned": 0,
                "chips_in_play": 0
            }
        }
        game.update(overrides)
        await db.games.insert_one(game)
        return game

class PlayerFactory:
    @staticmethod
    async def create(db, game_id, **overrides):
        player = {
            "_id": ObjectId(),
            "game_id": str(game_id),
            "player_token": str(uuid.uuid4()),
            "display_name": overrides.get("display_name", "Test Player"),
            "is_manager": overrides.get("is_manager", False),
            "is_active": True,
            "credits_owed": 0,
            "checked_out": False,
            "final_chip_count": None,
            "profit_loss": None,
            "joined_at": datetime.now(timezone.utc),
            "checked_out_at": None
        }
        player.update(overrides)
        await db.players.insert_one(player)
        return player
```

### 5.2 Test Data Scenarios

**Typical game scenario (used for most tests):**
- 1 manager + 5 players
- 15 chip requests (mix of cash/credit, all approved)
- Total chips in play: 1000
- Game status: OPEN
- Created 2 hours ago

**Settlement scenario:**
- All players checked out
- 2 players with outstanding credit debt
- Game status: SETTLING

**Edge case scenario:**
- Game created 23h 59m ago (near expiration)
- 10 pending requests
- Status: OPEN

### 5.3 Fixture Sharing (pytest)

Use pytest fixtures for common setup patterns:

```python
# src/tests/conftest.py

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

@pytest.fixture
async def db():
    """Clean test database for each test."""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.chipmate_test
    yield db
    await client.drop_database("chipmate_test")
    client.close()

@pytest.fixture
async def typical_game(db):
    """Game with 1 manager + 5 players."""
    game = await GameFactory.create(db)
    manager = await PlayerFactory.create(db, game["_id"], is_manager=True)
    players = [
        await PlayerFactory.create(db, game["_id"], display_name=f"Player{i}")
        for i in range(1, 6)
    ]
    return {
        "game": game,
        "manager": manager,
        "players": players
    }
```

---

## 6. CI Integration

### 6.1 GitHub Actions Workflow

```yaml
# .github/workflows/test.yml

name: Test Suite

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  backend-tests:
    runs-on: ubuntu-latest

    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: pytest src/tests/unit --cov=src --cov-report=xml

      - name: Run integration tests
        run: pytest src/tests/integration --cov=src --cov-append --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: true

  frontend-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Run Vitest
        run: npm run test -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/coverage-final.json

  e2e-tests:
    runs-on: ubuntu-latest

    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Playwright
        run: |
          npm ci
          npx playwright install --with-deps

      - name: Start backend
        run: |
          pip install -r requirements.txt
          uvicorn src.main:app --host 0.0.0.0 --port 8000 &
          sleep 5

      - name: Start frontend
        run: |
          npm run build
          npm run preview &
          sleep 5

      - name: Run E2E tests
        run: npx playwright test

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
```

### 6.2 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml

repos:
  - repo: local
    hooks:
      - id: pytest-unit
        name: Backend unit tests
        entry: pytest src/tests/unit -x
        language: system
        pass_filenames: false
        always_run: true

      - id: vitest
        name: Frontend component tests
        entry: npm run test -- --run --reporter=verbose
        language: system
        pass_filenames: false
        files: \.(tsx?|jsx?)$
```

### 6.3 Test Execution Order

**CI pipeline stages:**

1. Lint and format checks (10s)
2. Backend unit tests (30s)
3. Frontend component tests (20s)
4. Backend integration tests (60s)
5. E2E P0 tests (90s)
6. E2E P1 tests (optional, post-merge)

**Total time budget:** <3 minutes for PR checks

---

## 7. Test Case Matrix

### 7.1 Matrix Columns

- **Test ID**: Unique identifier (format: `TC-<component>-<number>`)
- **Ticket Ref**: User story ticket (T1-T21)
- **Description**: What is being tested
- **Type**: Unit / Integration / Component / E2E
- **Priority**: P0 (must have) / P1 (should have) / P2 (nice to have)
- **Preconditions**: Setup required before test
- **Steps**: Test procedure
- **Expected Result**: Pass criteria

### 7.2 Complete Test Case Matrix

(See sections 8-10 for detailed test cases organized by priority and category)

---

## 8. P0 Critical Path Tests

### 8.1 Game Creation

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-GAME-001 | Manager creates new game successfully | E2E | None | 1. Navigate to home<br>2. Click "New Game"<br>3. Enter name "Alice"<br>4. Click "Create Game" | - Game created<br>- Game code displayed<br>- QR code shown<br>- Manager is first player |
| TC-GAME-002 | Game code is unique among active games | Integration | 1 OPEN game exists | 1. Create game via POST /api/v2/games<br>2. Extract game code<br>3. Attempt to create another game | Second game receives different code |
| TC-GAME-003 | Game has 24h expiry set correctly | Unit | None | 1. Call game creation service<br>2. Check expires_at field | expires_at = created_at + 24h |
| TC-GAME-004 | Manager receives player token with is_manager=true | Integration | None | 1. POST /api/v2/games<br>2. Decode returned player_token JWT | Token payload contains is_manager: true |

### 8.2 Player Join

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-JOIN-001 | Player joins via QR code link | E2E | Game created | 1. Scan QR code<br>2. Enter name "Bob"<br>3. Click "Join Game" | - Player redirected to game view<br>- Name appears in player list |
| TC-JOIN-002 | Player joins via manual code entry | E2E | Game created | 1. Click "Join Game"<br>2. Enter code manually<br>3. Enter name<br>4. Submit | Player joins successfully |
| TC-JOIN-003 | Duplicate name rejected | Integration | Player "Bob" already in game | 1. POST /api/v2/games/{id}/players/join<br>2. Use name "Bob" | 400 DUPLICATE_NAME error |
| TC-JOIN-004 | Cannot join CLOSED game | Integration | Game in CLOSED status | 1. POST /api/v2/games/{id}/players/join | 409 GAME_NOT_JOINABLE error |
| TC-JOIN-005 | Cannot join SETTLING game | Integration | Game in SETTLING status | 1. POST /api/v2/games/{id}/players/join | 409 GAME_NOT_JOINABLE error |

### 8.3 Chip Request (Player)

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-REQ-001 | Player requests cash buy-in | E2E | Player joined game | 1. Click "Request Chips"<br>2. Select "Cash"<br>3. Enter amount 100<br>4. Click "Send Request" | - Toast: "Request sent"<br>- Request appears in activity feed as PENDING |
| TC-REQ-002 | Player requests credit buy-in | E2E | Player joined game | 1. Click "Request Chips"<br>2. Select "Credit"<br>3. Enter amount 100<br>4. Submit | Request created with type=CREDIT |
| TC-REQ-003 | Zero amount rejected | Component | Chip request sheet open | 1. Enter amount "0"<br>2. Click send | Validation error: "Amount must be > 0" |
| TC-REQ-004 | Negative amount rejected | Integration | None | POST /api/v2/games/{id}/chip-requests with amount=-50 | 400 INVALID_AMOUNT error |
| TC-REQ-005 | Non-numeric input prevented | Component | Chip request sheet open | 1. Try to enter "abc" in amount field | Input rejected (inputmode=numeric) |

### 8.4 Manager Approve/Decline

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-APPR-001 | Manager approves cash request | E2E | 1 pending cash request for 100 | 1. View pending requests<br>2. Click "Approve" | - Request status: APPROVED<br>- Bank cash_balance +100<br>- Player receives notification |
| TC-APPR-002 | Manager approves credit request | Integration | 1 pending credit request for 100 | POST /api/v2/.../approve | - Request APPROVED<br>- Bank credits_issued +100<br>- Player credits_owed +100 |
| TC-APPR-003 | Manager declines request | E2E | 1 pending request | Click "Decline" → Confirm | - Request status: DECLINED<br>- Bank unchanged<br>- Player notified |
| TC-APPR-004 | Manager edits request amount | E2E | Pending request for 200 | 1. Click "Edit"<br>2. Change to 150<br>3. Approve | - Request status: EDITED<br>- Bank updated with 150<br>- Player receives edited notification |
| TC-APPR-005 | Approve is idempotent | Integration | 1 PENDING request | 1. Approve request<br>2. Approve again with same request_id | Both calls return 200, second is no-op |
| TC-APPR-006 | Cannot approve already declined request | Integration | 1 DECLINED request | POST /api/.../approve | 409 ALREADY_PROCESSED error |

### 8.5 Single Player Checkout

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-CHKOUT-001 | Checkout player with profit | E2E | Player: 200 cash in, 0 credit, final chips 250 | 1. Click player row<br>2. Click "Check Out"<br>3. Enter 250<br>4. Confirm | - Breakdown shows +50 profit<br>- Cash out: 250<br>- Credits: 0 |
| TC-CHKOUT-002 | Checkout player with loss | Unit | Player: 200 cash, final 150 | calculate_checkout_breakdown(150, 200, 0, 0) | - P/L: -50<br>- Cash out: 150 |
| TC-CHKOUT-003 | Checkout player with credit repayment | Unit | Player: 150 cash, 100 credit, 100 owed, final 250 | calculate_checkout_breakdown(...) | - Credits repaid: 100<br>- Remaining credits: 0<br>- Cash out: 200 |
| TC-CHKOUT-004 | Checkout player with partial credit repayment | Unit | Player: 100 cash, 200 credit, 200 owed, final 150 | calculate_checkout_breakdown(...) | - Credits repaid: 150<br>- Remaining credits: 50<br>- Cash out: 50 |
| TC-CHKOUT-005 | Checkout with zero chips | Integration | Player with chips | POST /api/.../checkout with chip_count=0 | - Checkout succeeds<br>- Cash out: 0<br>- P/L calculated |

### 8.6 Whole-Table Checkout

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-WTBL-001 | Credit-debt players listed first | Integration | 3 players: Alice (50 credit owed), Bob (0), Carol (100 credit owed) | GET /api/.../checkout/order | Order: [Carol, Alice, Bob] |
| TC-WTBL-002 | Whole-table checkout transitions to SETTLING | Integration | Game OPEN, 3 unchecked players | POST /api/.../checkout/whole-table | - Game status: SETTLING<br>- Checkout order returned |
| TC-WTBL-003 | Cannot start with pending requests | Integration | Game has 2 pending requests | POST /api/.../checkout/whole-table with force=false | 400 PENDING_REQUESTS_EXIST error |
| TC-WTBL-004 | Force flag bypasses pending check | Integration | Game has pending requests | POST /.../whole-table with force=true | SETTLING started despite pending |
| TC-WTBL-005 | Process next player in queue | E2E | Whole-table started, 3 in queue | 1. Click "Next Player"<br>2. Enter chips<br>3. Confirm | - Player 1 checked out<br>- Next player shown<br>- Progress updated |

### 8.7 Settlement and Close

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-SETTL-001 | View settlement summary | Integration | All players checked out, 2 with credit debt | GET /api/.../settlement/summary | - Outstanding credits total shown<br>- Debtors listed |
| TC-SETTL-002 | Mark player debt settled | Integration | Player owes 100 credit | POST /api/.../settlement/players/{id}/settle with amount=100 | - Player debt: 0<br>- Settlement logged |
| TC-SETTL-003 | Finalize settlement closes game | Integration | All debts settled | POST /api/.../settlement/finalize | - Game status: CLOSED<br>- closed_at timestamp set |
| TC-SETTL-004 | Cannot finalize with outstanding credits | Integration | 1 player still owes credit | POST /.../finalize with force=false | 400 OUTSTANDING_CREDITS error |
| TC-SETTL-005 | Force finalize ignores debts | Integration | Outstanding credits exist | POST /.../finalize with force=true | Game closed despite debts |

### 8.8 Admin Login

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-ADMIN-001 | Admin login with valid credentials | Integration | Admin user exists | POST /api/v2/auth/admin/login with correct username/password | - JWT returned<br>- Token contains role=ADMIN |
| TC-ADMIN-002 | Login rejected with wrong password | Integration | None | POST /api/.../login with invalid password | 401 INVALID_CREDENTIALS error |
| TC-ADMIN-003 | JWT expires after 24 hours | Unit | None | 1. Create JWT with exp=now+24h<br>2. Validate after 24h | Token validation fails with EXPIRED_TOKEN |
| TC-ADMIN-004 | Admin can view all games | Integration | JWT token, 5 games exist | GET /api/v2/admin/games with JWT | All 5 games returned |

---

## 9. Edge Case Tests

### 9.1 24-Hour Auto-Close

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-001 | Game auto-closes after 24h | Integration | Game with expires_at in past | 1. Run auto-close background task<br>2. Query game | - Game status: CLOSED<br>- closed_at set |
| TC-EDGE-002 | SETTLING games not auto-closed | Integration | SETTLING game past 24h | Run auto-close task | Game remains SETTLING |
| TC-EDGE-003 | Game expires_at set on creation | Unit | None | Create game, check expires_at | expires_at = created_at + 24h |
| TC-EDGE-004 | API returns CLOSED for expired OPEN games | Integration | OPEN game past expires_at | GET /api/v2/games/{id}/status | status field shows CLOSED despite DB |
| TC-EDGE-005 | Players notified on auto-close | Integration | Game with 3 players, auto-closed | Check notifications collection | All 3 players have GAME_CLOSED notification |

### 9.2 Duplicate Join Attempt

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-006 | Same player rejoin attempt | Integration | Player already in game | POST /api/.../join with same token | 200 OK, returns existing session |
| TC-EDGE-007 | Different player same name | Integration | Player "Bob" exists | POST /.../join with name "Bob" | 400 DUPLICATE_NAME |
| TC-EDGE-008 | Same player different browser | E2E | Player in game on tab 1 | Open tab 2, rejoin with stored token | Both tabs show same game state |

### 9.3 Request After SETTLING

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-009 | Request button hidden in SETTLING | Component | Game status SETTLING | Render Player Game View | "Request Chips" button not visible |
| TC-EDGE-010 | API rejects request in SETTLING | Integration | Game status SETTLING | POST /api/.../chip-requests | 409 GAME_NOT_OPEN error |
| TC-EDGE-011 | Stale client request rejected | Integration | Client created request before SETTLING, submitted after | POST chip request | 409 GAME_NOT_OPEN |

### 9.4 Checkout with Zero Chips

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-012 | Player cashes out with 0 chips | Integration | Player has 100 total buy-in | POST /.../checkout with chip_count=0 | - P/L: -100<br>- Cash out: 0<br>- Checkout succeeds |
| TC-EDGE-013 | Zero chips with credit owed | Unit | 100 credit owed, 0 final chips | calculate_checkout_breakdown(0, 0, 100, 100) | - Credits repaid: 0<br>- Remaining credits: 100<br>- Cash out: 0 |

### 9.5 On-Behalf-Of Edge Cases

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-014 | On-behalf-of for non-existent player | Integration | Manager, target player not in game | POST /.../chip-requests with on_behalf_of_player_id | 404 PLAYER_NOT_FOUND |
| TC-EDGE-015 | Target player receives notification | Integration | Manager creates on-behalf-of request | 1. Submit request<br>2. Query target player notifications | Target has ON_BEHALF_SUBMITTED notification |
| TC-EDGE-016 | On-behalf-of for checked-out player | Integration | Target player checked_out=true | POST on-behalf request | 409 PLAYER_NOT_ACTIVE or similar |

### 9.6 Admin Impersonation

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-EDGE-017 | Admin generates manager token | Integration | Admin JWT, game exists | POST /api/.../impersonate | Player token with is_manager=true returned |
| TC-EDGE-018 | Impersonation logged to audit log | Integration | Admin impersonates | 1. Impersonate<br>2. Check admin_audit_log | Entry with action=IMPERSONATE |
| TC-EDGE-019 | Admin can approve requests | E2E | Admin impersonated, pending request | Approve request as admin | Request approved, audit log shows admin_override |

---

## 10. Negative Tests

### 10.1 Invalid Game Code

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-001 | Join with non-existent code | Integration | None | POST /api/.../join with code "FAKE99" | 404 GAME_NOT_FOUND |
| TC-NEG-002 | Get game by invalid code format | Integration | None | GET /api/v2/games/code/123 (invalid format) | 404 or 400 error |

### 10.2 Expired/Invalid Token

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-003 | Request with expired player token | Integration | Token with exp in past | GET /api/.../players/me with expired token | 401 EXPIRED_TOKEN |
| TC-NEG-004 | Request with malformed token | Integration | None | GET /api endpoint with token "invalid-jwt" | 401 INVALID_TOKEN |
| TC-NEG-005 | Request with missing Authorization header | Integration | None | GET /api/.../players/me without header | 401 UNAUTHORIZED |
| TC-NEG-006 | Admin JWT on player endpoint | Integration | Admin JWT | POST /api/.../chip-requests with admin JWT | 403 FORBIDDEN (not a player token) |

### 10.3 Unauthorized Role Access

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-007 | Player accesses manager-only endpoint | Integration | Player token | GET /api/.../checkout/order | 403 FORBIDDEN |
| TC-NEG-008 | Player views another player's details | Integration | Player A token | GET /api/.../players/{player_B_id} | 403 FORBIDDEN |
| TC-NEG-009 | Non-admin accesses admin endpoint | Integration | Player token | GET /api/v2/admin/games | 403 ADMIN_REQUIRED |
| TC-NEG-010 | Manager from different game | Integration | Manager of game A | GET /api/.../games/B/status | 403 FORBIDDEN |

### 10.4 Malformed Input

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-011 | Chip request with missing type | Integration | None | POST /.../chip-requests without request_type field | 400 INVALID_INPUT with field error |
| TC-NEG-012 | Join with name > 50 chars | Integration | None | POST /.../join with 51-char name | 400 INVALID_INPUT |
| TC-NEG-013 | Join with empty name | Integration | None | POST /.../join with name="" | 400 INVALID_INPUT |
| TC-NEG-014 | Checkout with negative chip count | Integration | None | POST /.../checkout with chip_count=-10 | 400 INVALID_CHIP_COUNT |
| TC-NEG-015 | Create game with invalid JSON | Integration | None | POST /api/v2/games with body "not json" | 400 error from FastAPI |

### 10.5 Concurrent Conflicting Requests

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-016 | Concurrent approval of same request | Integration | 1 PENDING request | 1. Start approve call A<br>2. Start approve call B concurrently | One succeeds, one gets 409 ALREADY_PROCESSED |
| TC-NEG-017 | Approve and decline same request | Integration | 1 PENDING request | 1. Approve in thread A<br>2. Decline in thread B | One succeeds, one fails |
| TC-NEG-018 | Concurrent checkout of same player | Integration | Player not checked out | 2 concurrent checkout POSTs | One succeeds, one gets 409 ALREADY_CHECKED_OUT |

### 10.6 State Transition Violations

| Test ID | Description | Type | Preconditions | Steps | Expected Result |
|---------|-------------|------|---------------|-------|-----------------|
| TC-NEG-019 | Close OPEN game directly | Integration | Game status OPEN | POST /api/.../close | 409 INVALID_STATE_TRANSITION (must be SETTLING) |
| TC-NEG-020 | Start whole-table from CLOSED | Integration | Game CLOSED | POST /.../whole-table | 409 error |
| TC-NEG-021 | Approve request in CLOSED game | Integration | Game CLOSED, old PENDING request | POST /.../approve | 409 GAME_NOT_OPEN |

---

## 11. Coverage Mapping to Acceptance Criteria

This section maps every acceptance criterion from user stories T1-T21 to test cases.

### T1: User Flows (covered in sections 8-10)

| Acceptance Criterion | Mapped Test Cases |
|----------------------|-------------------|
| Manager can create game with unique code | TC-GAME-001, TC-GAME-002 |
| Players can join via QR or manual code | TC-JOIN-001, TC-JOIN-002 |
| Duplicate names rejected | TC-JOIN-003 |
| Cannot join CLOSED/SETTLING games | TC-JOIN-004, TC-JOIN-005 |
| Player can request cash/credit | TC-REQ-001, TC-REQ-002 |
| Negative/zero amounts rejected | TC-REQ-003, TC-REQ-004 |
| Manager sees pending requests | TC-APPR-001 |
| Manager can approve/decline/edit | TC-APPR-001, TC-APPR-003, TC-APPR-004 |
| Approvals are idempotent | TC-APPR-005 |
| On-behalf-of requests supported | TC-EDGE-014, TC-EDGE-015 |
| Player receives notifications | TC-APPR-001 (implicit), TC-EDGE-015 |
| Single checkout calculates P/L | TC-CHKOUT-001, TC-CHKOUT-002 |
| Credit repayment calculated | TC-CHKOUT-003, TC-CHKOUT-004 |
| Whole-table checkout orders by credit-debt | TC-WTBL-001 |
| Whole-table transitions to SETTLING | TC-WTBL-002 |
| Settlement lists outstanding credits | TC-SETTL-001 |
| Mark debts settled | TC-SETTL-002 |
| Finalize closes game | TC-SETTL-003 |
| 24h auto-close enforced | TC-EDGE-001, TC-EDGE-002 |
| Admin can login | TC-ADMIN-001 |
| Admin can impersonate manager | TC-EDGE-017 |

### T2: MongoDB Schema (covered by integration tests)

| Schema Requirement | Mapped Test Cases |
|--------------------|-------------------|
| Game code unique among OPEN/SETTLING | TC-GAME-002 |
| Bank embedded in game | TC-APPR-001 (verifies bank update) |
| Player identified by UUID token | TC-JOIN-001 |
| Chip request status enum | TC-APPR-001, TC-APPR-003 |
| Notifications TTL 48h | (Infrastructure test, not in matrix) |
| expires_at triggers auto-close | TC-EDGE-001 |

### T3: API Contract (covered comprehensively)

| API Requirement | Mapped Test Cases |
|-----------------|-------------------|
| All endpoints require auth (except public) | TC-NEG-005 |
| Role-based access control | TC-NEG-007 to TC-NEG-010 |
| Error codes standardized | All TC-NEG-* tests |
| Idempotent operations | TC-APPR-005 |
| Input validation via Pydantic | TC-NEG-011 to TC-NEG-015 |

---

## 12. Test Environment Configuration

### 12.1 Local Development Environment

**Backend:**
```bash
# .env.test
MONGODB_URI=mongodb://localhost:27017/chipmate_test
JWT_SECRET=test-secret-key-do-not-use-in-prod
ENVIRONMENT=test
LOG_LEVEL=DEBUG
```

**Frontend:**
```bash
# .env.test
VITE_API_URL=http://localhost:8000/api/v2
VITE_ENVIRONMENT=test
```

### 12.2 CI Environment (GitHub Actions)

**Services:**
- MongoDB 7 (Docker container on port 27017)
- No external dependencies (mocked via MSW)

**Environment variables:**
- Same as .env.test
- Secrets managed via GitHub Secrets

### 12.3 Staging Environment

**Infrastructure:**
- Railway staging deployment
- Separate MongoDB Atlas cluster (shared-tier)
- Real backend + frontend

**Use case:** Manual QA, E2E smoke tests, cross-browser testing

### 12.4 Cross-Browser Testing (BrowserStack)

**Browsers:**
- Chrome (latest, latest-1)
- Safari iOS (latest 2 versions)
- Chrome Android (latest)
- Firefox (latest)

**Test subset:** P0 E2E tests only (TC-GAME-001, TC-JOIN-001, TC-REQ-001, TC-APPR-001, TC-CHKOUT-001)

**Frequency:** Nightly, not blocking PRs

---

## Appendix A: Test Execution Checklist

### Pre-Release Testing

- [ ] All P0 tests pass (unit + integration + E2E)
- [ ] Code coverage meets targets (80% backend, 70% frontend)
- [ ] No regressions in P1 tests
- [ ] Cross-browser smoke tests pass
- [ ] Load test: 50 concurrent users, <500ms P95 latency
- [ ] Security scan: no critical vulnerabilities
- [ ] Manual exploratory testing: 2 hours
- [ ] Staging deployment validated

### Post-Release Monitoring

- [ ] Error rate <0.1% in first 24h
- [ ] No new error codes in logs
- [ ] User feedback reviewed
- [ ] Hotfix plan ready if needed

---

## Appendix B: Test Metrics Dashboard

Track these metrics in CI/CD pipeline:

| Metric | Target | Current | Trend |
|--------|--------|---------|-------|
| Backend unit test coverage | 80% | - | - |
| Frontend component coverage | 70% | - | - |
| Total test count | 150+ | - | - |
| P0 test pass rate | 100% | - | - |
| Flaky test rate | <1% | - | - |
| Average test suite runtime | <3 min | - | - |
| E2E test pass rate (CI) | >95% | - | - |

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | QA Manager | Initial test strategy and matrix |

---

**End of Document**

This test strategy provides comprehensive coverage of all ChipMate v2 functionality. Review and approval required from:
- Backend Engineer (pytest strategy)
- Frontend Engineer (Vitest + Playwright)
- DevOps (CI configuration)
- Product Owner (acceptance criteria mapping)
