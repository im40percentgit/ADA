# Phase 9a — Care Circles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Ada's 1:1 caregiver model to a many-to-many care circle model with role-based visibility.

**Architecture:** New `care_circles` and `care_circle_members` tables with automatic migration from `caregiver_id`. New `resolve_circle_access()` auth helper replaces `_resolve_caregiver_patient()`. Caregiver dashboard refactored to support multiple patients via circle membership. Frontend adds CircleSelector for multi-patient caregivers.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, Pydantic v2, React + TypeScript

**Design spec:** `docs/superpowers/specs/2026-03-25-phase9-care-circles-shared-boards-design.md`

---

### Task 1: Care Circle Pydantic Models

**Files:**
- Create: `ada/models/circle.py`

- [ ] **Step 1: Create Pydantic models for care circles**

```python
# ada/models/circle.py
"""Pydantic models for care circles."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


CircleRole = Literal["primary_caregiver", "family", "clinician"]


class CareCircle(BaseModel):
    """A care circle links a patient to their care team."""

    id: str
    patient_id: str
    created_at: datetime


class CareCircleMember(BaseModel):
    """A member of a care circle with a specific role."""

    id: str
    circle_id: str
    user_id: str
    role: CircleRole
    added_by: str | None = None
    created_at: datetime


class CareCircleWithPatient(BaseModel):
    """Care circle with patient name for listing."""

    id: str
    patient_id: str
    patient_name: str
    my_role: CircleRole
    created_at: datetime


class CareCircleMemberWithEmail(BaseModel):
    """Circle member with user email for display."""

    id: str
    user_id: str
    email: str
    role: CircleRole
    created_at: datetime


class AddMemberRequest(BaseModel):
    """Request body for adding a circle member."""

    email: str
    role: CircleRole
```

- [ ] **Step 2: Commit**

```
git add ada/models/circle.py
git commit -m "feat(phase9a): add care circle Pydantic models"
```

---

### Task 2: Database Schema + CRUD Methods

**Files:**
- Modify: `ada/core/state.py` (schema at lines 56-353, CRUD methods after daily_summaries section)
- Create: `tests/unit/test_circle_state.py`

- [ ] **Step 1: Write failing tests for care circle CRUD**

Create `tests/unit/test_circle_state.py`:

```python
"""Tests for care circle StateManager operations."""

from __future__ import annotations

import pytest
import pytest_asyncio

from ada.core.state import StateManager


@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with schema initialized."""
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.mark.asyncio
async def test_create_care_circle(state: StateManager):
    """Creating a care circle stores it in the database."""
    await state.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
    })

    await state.create_care_circle("circle-1", "pat-1")
    circle = await state.get_care_circle_by_patient("pat-1")

    assert circle is not None
    assert circle["id"] == "circle-1"
    assert circle["patient_id"] == "pat-1"


@pytest.mark.asyncio
async def test_create_care_circle_duplicate_patient_fails(state: StateManager):
    """UNIQUE constraint on patient_id prevents duplicate circles."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")

    with pytest.raises(Exception):
        await state.create_care_circle("circle-2", "pat-1")


@pytest.mark.asyncio
async def test_add_circle_member(state: StateManager):
    """Adding a member to a circle stores the membership."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")

    await state.add_circle_member(
        member_id="ccm-1",
        circle_id="circle-1",
        user_id="user-caregiver-1",
        role="primary_caregiver",
        added_by=None,
    )

    members = await state.get_circle_members("circle-1")
    assert len(members) == 1
    assert members[0]["user_id"] == "user-caregiver-1"
    assert members[0]["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_add_duplicate_member_fails(state: StateManager):
    """UNIQUE(circle_id, user_id) prevents duplicate membership."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")
    await state.add_circle_member("ccm-1", "circle-1", "user-1", "primary_caregiver")

    with pytest.raises(Exception):
        await state.add_circle_member("ccm-2", "circle-1", "user-1", "family")


@pytest.mark.asyncio
async def test_remove_circle_member(state: StateManager):
    """Removing a member deletes the membership row."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")
    await state.add_circle_member("ccm-1", "circle-1", "user-1", "primary_caregiver")

    await state.remove_circle_member("circle-1", "user-1")

    members = await state.get_circle_members("circle-1")
    assert len(members) == 0


@pytest.mark.asyncio
async def test_get_circles_by_user(state: StateManager):
    """A user can be in multiple circles for different patients."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_patient({"id": "pat-2", "name": "Bob", "dob": "1985-06-15"})
    await state.create_care_circle("circle-1", "pat-1")
    await state.create_care_circle("circle-2", "pat-2")
    await state.add_circle_member("ccm-1", "circle-1", "user-1", "primary_caregiver")
    await state.add_circle_member("ccm-2", "circle-2", "user-1", "family")

    circles = await state.get_circles_by_user("user-1")
    assert len(circles) == 2
    patient_names = {c["patient_name"] for c in circles}
    assert patient_names == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_get_member_role(state: StateManager):
    """get_circle_member returns the membership record for a specific user."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")
    await state.add_circle_member("ccm-1", "circle-1", "user-1", "clinician")

    member = await state.get_circle_member("circle-1", "user-1")
    assert member is not None
    assert member["role"] == "clinician"


@pytest.mark.asyncio
async def test_get_circle_member_not_found(state: StateManager):
    """get_circle_member returns None for non-members."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_care_circle("circle-1", "pat-1")

    member = await state.get_circle_member("circle-1", "non-existent")
    assert member is None


@pytest.mark.asyncio
async def test_get_patients_by_circle_member(state: StateManager):
    """Returns all patients whose circle includes this user."""
    await state.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await state.create_patient({"id": "pat-2", "name": "Bob", "dob": "1985-06-15"})
    await state.create_care_circle("circle-1", "pat-1")
    await state.create_care_circle("circle-2", "pat-2")
    await state.add_circle_member("ccm-1", "circle-1", "user-1", "primary_caregiver")
    await state.add_circle_member("ccm-2", "circle-2", "user-1", "family")

    patients = await state.get_patients_by_circle_member("user-1")
    assert len(patients) == 2
    names = {p["name"] for p in patients}
    assert names == {"Alice", "Bob"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_circle_state.py -v`
Expected: FAIL with AttributeError (methods don't exist yet)

- [ ] **Step 3: Add care_circles and care_circle_members to _SCHEMA**

In `ada/core/state.py`, add after the `daily_summaries` table (around line 338), before the closing indices section:

```sql
CREATE TABLE IF NOT EXISTS care_circles (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL UNIQUE REFERENCES patients(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS care_circle_members (
    id          TEXT PRIMARY KEY,
    circle_id   TEXT NOT NULL REFERENCES care_circles(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    role        TEXT NOT NULL CHECK(role IN ('primary_caregiver', 'family', 'clinician')),
    added_by    TEXT REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(circle_id, user_id)
);
```

Add indices in the indices section (around line 352):

```sql
CREATE INDEX IF NOT EXISTS idx_care_circles_patient ON care_circles(patient_id);
CREATE INDEX IF NOT EXISTS idx_circle_members_circle ON care_circle_members(circle_id);
CREATE INDEX IF NOT EXISTS idx_circle_members_user ON care_circle_members(user_id);
```

- [ ] **Step 4: Add CRUD methods to StateManager**

Add after the daily_summaries methods section:

```python
# -- Care circles --------------------------------------------------------

async def create_care_circle(self, circle_id: str, patient_id: str) -> None:
    """Create a care circle for a patient."""
    await self._exec(
        "INSERT INTO care_circles (id, patient_id, created_at) VALUES (?, ?, ?)",
        (circle_id, patient_id, _now()),
    )

async def get_care_circle_by_patient(self, patient_id: str) -> dict[str, Any] | None:
    """Get the care circle for a patient."""
    row = await self._fetchone(
        "SELECT * FROM care_circles WHERE patient_id = ?", (patient_id,)
    )
    return dict(row) if row else None

async def add_circle_member(
    self,
    member_id: str,
    circle_id: str,
    user_id: str,
    role: str,
    added_by: str | None = None,
) -> None:
    """Add a user to a care circle."""
    await self._exec(
        """INSERT INTO care_circle_members (id, circle_id, user_id, role, added_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (member_id, circle_id, user_id, role, added_by, _now()),
    )

async def remove_circle_member(self, circle_id: str, user_id: str) -> None:
    """Remove a user from a care circle."""
    await self._exec(
        "DELETE FROM care_circle_members WHERE circle_id = ? AND user_id = ?",
        (circle_id, user_id),
    )

async def get_circle_members(self, circle_id: str) -> list[dict[str, Any]]:
    """List all members of a care circle with email."""
    rows = await self._fetchall(
        """SELECT ccm.id, ccm.circle_id, ccm.user_id, ccm.role,
                  ccm.added_by, ccm.created_at, u.email
           FROM care_circle_members ccm
           LEFT JOIN users u ON u.id = ccm.user_id
           WHERE ccm.circle_id = ?
           ORDER BY ccm.created_at""",
        (circle_id,),
    )
    return [dict(r) for r in rows]

async def get_circle_member(
    self, circle_id: str, user_id: str
) -> dict[str, Any] | None:
    """Get a specific member's record in a circle."""
    row = await self._fetchone(
        "SELECT * FROM care_circle_members WHERE circle_id = ? AND user_id = ?",
        (circle_id, user_id),
    )
    return dict(row) if row else None

async def get_circles_by_user(self, user_id: str) -> list[dict[str, Any]]:
    """List all circles a user belongs to, with patient name and user's role."""
    rows = await self._fetchall(
        """SELECT cc.id, cc.patient_id, cc.created_at,
                  p.name as patient_name, ccm.role as my_role
           FROM care_circles cc
           JOIN care_circle_members ccm ON ccm.circle_id = cc.id
           JOIN patients p ON p.id = cc.patient_id
           WHERE ccm.user_id = ?
           ORDER BY cc.created_at""",
        (user_id,),
    )
    return [dict(r) for r in rows]

async def get_patients_by_circle_member(
    self, user_id: str
) -> list[dict[str, Any]]:
    """Return all patients whose care circle includes this user."""
    rows = await self._fetchall(
        """SELECT p.*
           FROM patients p
           JOIN care_circles cc ON cc.patient_id = p.id
           JOIN care_circle_members ccm ON ccm.circle_id = cc.id
           WHERE ccm.user_id = ?
           ORDER BY p.name""",
        (user_id,),
    )
    return [_patient_row(r) for r in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_circle_state.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ tests pass, 0 regressions

- [ ] **Step 7: Commit**

```
git add ada/core/state.py tests/unit/test_circle_state.py
git commit -m "feat(phase9a): add care_circles + care_circle_members schema and CRUD"
```

---

### Task 3: Caregiver-to-Circle Migration

**Files:**
- Modify: `ada/core/state.py` (add migration method, call in `initialize()` at line ~389)
- Create: `tests/unit/test_circle_migration.py`

- [ ] **Step 1: Write failing tests for migration**

Create `tests/unit/test_circle_migration.py`:

```python
"""Tests for caregiver_id to care_circles migration."""

from __future__ import annotations

import pytest
import pytest_asyncio

from ada.core.state import StateManager


@pytest_asyncio.fixture
async def state_with_legacy_caregiver():
    """StateManager with a patient that has caregiver_id set (legacy model)."""
    sm = StateManager(":memory:")
    await sm.initialize()

    # Create a caregiver user
    await sm._exec(
        """INSERT INTO users (id, email, hashed_password, role, created_at, is_active)
           VALUES (?, ?, ?, ?, datetime('now'), 1)""",
        ("user-cg-1", "caregiver@example.com", "hashed", "caregiver"),
    )

    # Create patient with legacy caregiver_id
    await sm.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
        "caregiver_id": "user-cg-1",
    })

    # Create patient WITHOUT caregiver (should be skipped)
    await sm.create_patient({
        "id": "pat-2",
        "name": "Bob",
        "dob": "1985-06-15",
    })

    yield sm
    await sm.close()


@pytest.mark.asyncio
async def test_migration_creates_circle(state_with_legacy_caregiver: StateManager):
    """Migration creates a care circle for patients with caregiver_id."""
    state = state_with_legacy_caregiver
    circle = await state.get_care_circle_by_patient("pat-1")
    assert circle is not None
    assert circle["patient_id"] == "pat-1"


@pytest.mark.asyncio
async def test_migration_adds_caregiver_as_primary(state_with_legacy_caregiver: StateManager):
    """Migration creates a primary_caregiver membership."""
    state = state_with_legacy_caregiver
    circle = await state.get_care_circle_by_patient("pat-1")
    assert circle is not None

    member = await state.get_circle_member(circle["id"], "user-cg-1")
    assert member is not None
    assert member["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_migration_skips_patients_without_caregiver(state_with_legacy_caregiver: StateManager):
    """Patients without caregiver_id do not get a circle from migration."""
    state = state_with_legacy_caregiver
    circle = await state.get_care_circle_by_patient("pat-2")
    assert circle is None


@pytest.mark.asyncio
async def test_migration_is_idempotent(state_with_legacy_caregiver: StateManager):
    """Running migration twice does not create duplicates."""
    state = state_with_legacy_caregiver
    await state._migrate_caregiver_to_circles()

    circle = await state.get_care_circle_by_patient("pat-1")
    assert circle is not None
    member = await state.get_circle_member(circle["id"], "user-cg-1")
    assert member is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_circle_migration.py -v`
Expected: FAIL (method does not exist)

- [ ] **Step 3: Implement migration**

Add to `StateManager` in `ada/core/state.py`:

```python
async def _migrate_caregiver_to_circles(self) -> None:
    """Seed care_circles from existing caregiver_id relationships.

    Idempotent: INSERT OR IGNORE prevents duplicates.
    """
    rows = await self._fetchall(
        "SELECT id, caregiver_id FROM patients WHERE caregiver_id IS NOT NULL"
    )
    for row in rows:
        patient_id = row["id"]
        caregiver_user_id = row["caregiver_id"]
        circle_id = f"circle-{patient_id}"
        member_id = f"ccm-{caregiver_user_id}-{circle_id}"
        await self._exec(
            "INSERT OR IGNORE INTO care_circles (id, patient_id, created_at) VALUES (?, ?, ?)",
            (circle_id, patient_id, _now()),
        )
        await self._exec(
            """INSERT OR IGNORE INTO care_circle_members
               (id, circle_id, user_id, role, created_at)
               VALUES (?, ?, ?, 'primary_caregiver', ?)""",
            (member_id, circle_id, caregiver_user_id, _now()),
        )
```

Call at the end of `initialize()` (around line 389):

```python
await self._migrate_caregiver_to_circles()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_circle_migration.py -v`
Expected: All 4 PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ pass

- [ ] **Step 6: Commit**

```
git add ada/core/state.py tests/unit/test_circle_migration.py
git commit -m "feat(phase9a): add caregiver_id to care_circles migration"
```

---

### Task 4: Event Types

**Files:**
- Modify: `ada/core/events.py` (EventTypes class at lines 28-106, new dataclasses after line 514)

- [ ] **Step 1: Add event type constants**

In `EventTypes` class, add after `DAILY_SUMMARY_GENERATED` (line 105):

```python
# Care circles
CIRCLE_MEMBER_ADDED = "circle.member_added"
CIRCLE_MEMBER_REMOVED = "circle.member_removed"
```

- [ ] **Step 2: Add event dataclasses**

After `DailySummaryGeneratedEvent` (around line 514):

```python
@dataclass
class CircleMemberAddedEvent(AdaEvent):
    """Published when a user is added to a care circle."""

    event_type: str = EventTypes.CIRCLE_MEMBER_ADDED
    circle_id: str = ""
    patient_id: str = ""
    user_id: str = ""
    role: str = ""


@dataclass
class CircleMemberRemovedEvent(AdaEvent):
    """Published when a user is removed from a care circle."""

    event_type: str = EventTypes.CIRCLE_MEMBER_REMOVED
    circle_id: str = ""
    patient_id: str = ""
    user_id: str = ""
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ pass (no regressions, only added new constants)

- [ ] **Step 4: Commit**

```
git add ada/core/events.py
git commit -m "feat(phase9a): add care circle event types"
```

---

### Task 5: Auth Helper — resolve_circle_access

**Files:**
- Modify: `ada/api/auth.py` (add function after `_resolve_caregiver_patient` at line ~230)
- Create: `tests/unit/test_circle_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_circle_auth.py`:

```python
"""Tests for care circle auth helpers."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException

from ada.api.auth import resolve_circle_access
from ada.core.state import StateManager
from ada.models.user import User


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        ("user-cg-1", "cg@test.com", "caregiver"),
        ("user-fam-1", "fam@test.com", "caregiver"),
        ("user-outsider", "outsider@test.com", "caregiver"),
    ]:
        await sm._exec(
            """INSERT INTO users (id, email, hashed_password, role, created_at, is_active)
               VALUES (?, ?, ?, ?, datetime('now'), 1)""",
            (uid, email, "hashed", role),
        )

    await sm.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await sm.create_care_circle("circle-1", "pat-1")
    await sm.add_circle_member("ccm-1", "circle-1", "user-cg-1", "primary_caregiver")
    await sm.add_circle_member("ccm-2", "circle-1", "user-fam-1", "family")

    yield sm
    await sm.close()


def _user(uid: str) -> User:
    return User(id=uid, email=f"{uid}@test.com", role="caregiver", patient_id=None, is_active=True)


@pytest.mark.asyncio
async def test_valid_member(state: StateManager):
    member = await resolve_circle_access(_user("user-cg-1"), "circle-1", state)
    assert member["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_non_member_404(state: StateManager):
    with pytest.raises(HTTPException) as exc_info:
        await resolve_circle_access(_user("user-outsider"), "circle-1", state)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_role_filter_pass(state: StateManager):
    member = await resolve_circle_access(
        _user("user-cg-1"), "circle-1", state,
        require_roles=["primary_caregiver", "clinician"],
    )
    assert member["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_role_filter_fail(state: StateManager):
    with pytest.raises(HTTPException) as exc_info:
        await resolve_circle_access(
            _user("user-fam-1"), "circle-1", state,
            require_roles=["primary_caregiver"],
        )
    assert exc_info.value.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_circle_auth.py -v`
Expected: FAIL (function doesn't exist)

- [ ] **Step 3: Implement resolve_circle_access**

In `ada/api/auth.py`, add after `_resolve_caregiver_patient` (around line 230):

```python
async def resolve_circle_access(
    user: User,
    circle_id: str,
    state_manager: StateManager,
    require_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Verify user is a member of the circle and optionally check role.

    Returns membership record.
    Raises HTTP 404 if not a member (avoids leaking circle existence).
    Raises HTTP 403 if require_roles specified and role doesn't match.
    """
    member = await state_manager.get_circle_member(circle_id, user.id)
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    if require_roles and member["role"] not in require_roles:
        raise HTTPException(status_code=403, detail="Insufficient circle role")
    return member
```

Ensure `StateManager` is imported at the top of auth.py. Also ensure `Any` is imported from typing.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_circle_auth.py -v`
Expected: All 4 PASS

- [ ] **Step 5: Full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ pass

- [ ] **Step 6: Commit**

```
git add ada/api/auth.py tests/unit/test_circle_auth.py
git commit -m "feat(phase9a): add resolve_circle_access auth helper"
```

---

### Task 6: Circle REST Routes

**Files:**
- Create: `ada/api/routes/circles.py`
- Modify: `ada/api/app.py` (register router, around line 113)
- Create: `tests/unit/test_circle_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_circle_routes.py`:

```python
"""Tests for care circle REST endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        ("user-cg-1", "cg@test.com", "caregiver"),
        ("user-fam-1", "fam@test.com", "caregiver"),
        ("user-outsider", "outsider@test.com", "caregiver"),
    ]:
        await sm._exec(
            """INSERT INTO users (id, email, hashed_password, role, created_at, is_active)
               VALUES (?, ?, ?, ?, datetime('now'), 1)""",
            (uid, email, "hashed", role),
        )

    await sm.create_patient({"id": "pat-1", "name": "Alice", "dob": "1990-01-01"})
    await sm.create_care_circle("circle-1", "pat-1")
    await sm.add_circle_member("ccm-1", "circle-1", "user-cg-1", "primary_caregiver")

    yield sm
    await sm.close()


def _make_client(state: StateManager, user: User) -> TestClient:
    app = create_app(state_manager=state)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(uid: str, role: str = "caregiver") -> User:
    return User(id=uid, email=f"{uid}@test.com", role=role, patient_id=None, is_active=True)


@pytest.mark.asyncio
async def test_list_my_circles(state: StateManager):
    client = _make_client(state, _user("user-cg-1"))
    resp = client.get("/api/circles/my")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["patient_name"] == "Alice"


@pytest.mark.asyncio
async def test_list_my_circles_empty(state: StateManager):
    client = _make_client(state, _user("user-outsider"))
    resp = client.get("/api/circles/my")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_circle_members(state: StateManager):
    client = _make_client(state, _user("user-cg-1"))
    resp = client.get("/api/circles/circle-1/members")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_members_non_member_404(state: StateManager):
    client = _make_client(state, _user("user-outsider"))
    resp = client.get("/api/circles/circle-1/members")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_member(state: StateManager):
    client = _make_client(state, _user("user-cg-1"))
    resp = client.post(
        "/api/circles/circle-1/members",
        json={"email": "fam@test.com", "role": "family"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "family"


@pytest.mark.asyncio
async def test_add_member_family_denied(state: StateManager):
    await state.add_circle_member("ccm-fam", "circle-1", "user-fam-1", "family")
    client = _make_client(state, _user("user-fam-1"))
    resp = client.post(
        "/api/circles/circle-1/members",
        json={"email": "outsider@test.com", "role": "family"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_member(state: StateManager):
    await state.add_circle_member("ccm-fam", "circle-1", "user-fam-1", "family")
    client = _make_client(state, _user("user-cg-1"))
    resp = client.delete("/api/circles/circle-1/members/user-fam-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_member_non_primary_denied(state: StateManager):
    await state.add_circle_member("ccm-fam", "circle-1", "user-fam-1", "family")
    client = _make_client(state, _user("user-fam-1"))
    resp = client.delete("/api/circles/circle-1/members/user-cg-1")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_circle_routes.py -v`
Expected: FAIL (routes don't exist)

- [ ] **Step 3: Create circles route module**

Create `ada/api/routes/circles.py`:

```python
"""Care circle management REST endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user, resolve_circle_access
from ada.core.state import StateManager
from ada.models.circle import AddMemberRequest
from ada.models.user import User

router = APIRouter(prefix="/circles", tags=["circles"])


def _state(request: Request) -> StateManager:
    return request.app.state.state_manager


@router.get("/my")
async def list_my_circles(
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """List all care circles the current user belongs to."""
    return await state.get_circles_by_user(user.id)


@router.get("/{circle_id}/members")
async def list_circle_members(
    circle_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """List members of a care circle. Requires membership."""
    await resolve_circle_access(user, circle_id, state)
    return await state.get_circle_members(circle_id)


@router.post("/{circle_id}/members", status_code=201)
async def add_circle_member(
    circle_id: str,
    body: AddMemberRequest,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Add a member. Requires primary_caregiver or clinician role."""
    await resolve_circle_access(
        user, circle_id, state,
        require_roles=["primary_caregiver", "clinician"],
    )

    target_user = await state._fetchone(
        "SELECT id, email FROM users WHERE email = ?", (body.email,)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    member_id = str(uuid.uuid4())
    try:
        await state.add_circle_member(
            member_id=member_id,
            circle_id=circle_id,
            user_id=target_user["id"],
            role=body.role,
            added_by=user.id,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Already a member")

    return {
        "id": member_id,
        "user_id": target_user["id"],
        "email": target_user["email"],
        "role": body.role,
        "created_at": "",
    }


@router.delete("/{circle_id}/members/{member_user_id}", status_code=204)
async def remove_circle_member(
    circle_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> None:
    """Remove a member. Requires primary_caregiver role."""
    await resolve_circle_access(
        user, circle_id, state,
        require_roles=["primary_caregiver"],
    )
    await state.remove_circle_member(circle_id, member_user_id)
```

- [ ] **Step 4: Register router in app.py**

In `ada/api/app.py`, add with the other router imports and include_router calls (around line 113):

```python
from ada.api.routes import circles
# ...
app.include_router(circles.router, prefix="/api")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_circle_routes.py -v`
Expected: All 8 PASS

- [ ] **Step 6: Full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ pass

- [ ] **Step 7: Commit**

```
git add ada/api/routes/circles.py ada/api/app.py tests/unit/test_circle_routes.py
git commit -m "feat(phase9a): add care circle REST endpoints"
```

---

### Task 7: Refactor Caregiver Dashboard to Use Circles

**Files:**
- Modify: `ada/api/auth.py` (refactor `_resolve_caregiver_patient` at lines 220-230)
- Modify: `ada/api/routes/caregiver.py` (add optional `patient_id` param)
- Modify: `tests/integration/test_caregiver_flow.py` (seed circles in fixtures)

- [ ] **Step 1: Refactor _resolve_caregiver_patient**

In `ada/api/auth.py`, replace `_resolve_caregiver_patient` (lines 220-230) with:

```python
async def _resolve_caregiver_patient(
    user: User, state_manager: StateManager, patient_id: str | None = None
) -> str:
    """Return the patient_id for this caregiver via circle membership.

    If patient_id is provided, verify the user is in that patient's circle.
    Otherwise, return the first patient (backward compatibility).
    Raises HTTP 404 to avoid leaking patient existence.
    """
    if patient_id:
        circle = await state_manager.get_care_circle_by_patient(patient_id)
        if not circle:
            raise HTTPException(status_code=404, detail="No patient linked")
        member = await state_manager.get_circle_member(circle["id"], user.id)
        if not member:
            raise HTTPException(status_code=404, detail="No patient linked")
        return patient_id

    patients = await state_manager.get_patients_by_circle_member(user.id)
    if not patients:
        # Legacy fallback during transition
        patient = await state_manager.get_patient_by_caregiver(user.id)
        if not patient:
            raise HTTPException(status_code=404, detail="No patient linked")
        return patient["id"]
    return patients[0]["id"]
```

- [ ] **Step 2: Update caregiver overview endpoint**

In `ada/api/routes/caregiver.py`, update the endpoint signature to accept optional `patient_id`:

```python
@router.get("/overview")
async def caregiver_overview(
    request: Request,
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
```

And update the patient_id resolution call in the function body to pass the new parameter:

```python
    resolved_patient_id = await _resolve_caregiver_patient(user, state, patient_id)
```

Check that `_resolve_caregiver_patient` is imported and called with the correct signature.

- [ ] **Step 3: Update caregiver integration test fixtures**

In `tests/integration/test_caregiver_flow.py`, add circle seeding to the fixture (after patient creation). Look for where the patient and caregiver user are created and add:

```python
# Seed care circle (Phase 9a)
await sm.create_care_circle(f"circle-{patient_id}", patient_id)
await sm.add_circle_member(f"ccm-{caregiver_user_id}", f"circle-{patient_id}", caregiver_user_id, "primary_caregiver")
```

Use the actual variable names from the fixture.

- [ ] **Step 4: Run caregiver tests**

Run: `uv run pytest tests/integration/test_caregiver_flow.py -v`
Expected: All existing tests PASS

- [ ] **Step 5: Full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: 819+ pass

- [ ] **Step 6: Commit**

```
git add ada/api/auth.py ada/api/routes/caregiver.py tests/integration/test_caregiver_flow.py
git commit -m "refactor(phase9a): caregiver dashboard queries via care circles"
```

---

### Task 8: Circle Integration Test

**Files:**
- Create: `tests/integration/test_circle_flow.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_circle_flow.py`:

```python
"""Integration test: full care circle lifecycle."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        ("user-cg", "caregiver@test.com", "caregiver"),
        ("user-fam", "family@test.com", "caregiver"),
    ]:
        await sm._exec(
            """INSERT INTO users (id, email, hashed_password, role, created_at, is_active)
               VALUES (?, ?, ?, ?, datetime('now'), 1)""",
            (uid, email, "hashed", role),
        )

    # Patient with legacy caregiver_id triggers auto-migration
    await sm.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
        "caregiver_id": "user-cg",
    })

    yield sm
    await sm.close()


def _client(state: StateManager, user: User) -> TestClient:
    app = create_app(state_manager=state)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(uid: str, email: str, role: str = "caregiver") -> User:
    return User(id=uid, email=email, role=role, patient_id=None, is_active=True)


@pytest.mark.asyncio
async def test_full_circle_lifecycle(state: StateManager):
    """Migration, list, add member, overview, remove member."""
    cg = _user("user-cg", "caregiver@test.com")
    fam = _user("user-fam", "family@test.com")
    client_cg = _client(state, cg)
    client_fam = _client(state, fam)

    # 1. Migration created a circle
    resp = client_cg.get("/api/circles/my")
    assert resp.status_code == 200
    circles = resp.json()
    assert len(circles) == 1
    assert circles[0]["patient_name"] == "Alice"
    circle_id = circles[0]["id"]

    # 2. Add family member
    resp = client_cg.post(
        f"/api/circles/{circle_id}/members",
        json={"email": "family@test.com", "role": "family"},
    )
    assert resp.status_code == 201

    # 3. Family member sees the circle
    resp = client_fam.get("/api/circles/my")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 4. Both see members
    resp = client_fam.get(f"/api/circles/{circle_id}/members")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # 5. Caregiver overview works
    resp = client_cg.get("/api/caregiver/overview")
    assert resp.status_code == 200
    assert resp.json()["patient"]["name"] == "Alice"

    # 6. Remove family member
    resp = client_cg.delete(f"/api/circles/{circle_id}/members/user-fam")
    assert resp.status_code == 204

    # 7. Family member no longer sees circle
    resp = client_fam.get("/api/circles/my")
    assert resp.status_code == 200
    assert len(resp.json()) == 0
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_circle_flow.py -v`
Expected: PASS

- [ ] **Step 3: Full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```
git add tests/integration/test_circle_flow.py
git commit -m "test(phase9a): add care circle integration test"
```

---

### Task 9: Frontend Types + API Client

**Files:**
- Modify: `web/src/types/index.ts` (add after caregiver types, around line 282)
- Modify: `web/src/api/client.ts` (add after `getCaregiverOverview`, around line 154)

- [ ] **Step 1: Add TypeScript types**

In `web/src/types/index.ts`, add after `CaregiverOverview`:

```typescript
// -- Care Circles -------------------------------------------------------

export interface CareCircle {
  id: string
  patient_id: string
  patient_name: string
  my_role: 'primary_caregiver' | 'family' | 'clinician'
  created_at: string
}

export interface CareCircleMember {
  id: string
  user_id: string
  email: string
  role: 'primary_caregiver' | 'family' | 'clinician'
  created_at: string
}
```

- [ ] **Step 2: Add API client functions**

In `web/src/api/client.ts`, add after `getCaregiverOverview`:

```typescript
// -- Care Circles -------------------------------------------------------

export function getMyCircles(): Promise<CareCircle[]> {
  return request<CareCircle[]>('/circles/my')
}

export function getCircleMembers(circleId: string): Promise<CareCircleMember[]> {
  return request<CareCircleMember[]>(`/circles/${circleId}/members`)
}

export function addCircleMember(
  circleId: string,
  body: { email: string; role: string },
): Promise<CareCircleMember> {
  return request<CareCircleMember>(`/circles/${circleId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function removeCircleMember(circleId: string, userId: string): Promise<void> {
  return request<void>(`/circles/${circleId}/members/${userId}`, {
    method: 'DELETE',
  })
}

export function getCaregiverOverviewForPatient(patientId: string): Promise<CaregiverOverview> {
  return request<CaregiverOverview>(`/caregiver/overview?patient_id=${patientId}`)
}
```

Add the import for new types if needed (check if types are imported in client.ts).

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /home/j/CerebrumCraft/ada/web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```
git add web/src/types/index.ts web/src/api/client.ts
git commit -m "feat(phase9a): add care circle TypeScript types and API client"
```

---

### Task 10: Frontend — useCircles Hook

**Files:**
- Create: `web/src/hooks/useCircles.ts`

- [ ] **Step 1: Create hook**

```typescript
// web/src/hooks/useCircles.ts
import { useCallback, useEffect, useState } from 'react'

import { getMyCircles } from '../api/client'
import type { CareCircle } from '../types'

interface UseCirclesResult {
  circles: CareCircle[]
  selectedCircle: CareCircle | null
  selectCircle: (circle: CareCircle) => void
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useCircles(): UseCirclesResult {
  const [circles, setCircles] = useState<CareCircle[]>([])
  const [selectedCircle, setSelectedCircle] = useState<CareCircle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getMyCircles()
      setCircles(data)
      if (data.length > 0 && !selectedCircle) {
        setSelectedCircle(data[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load circles')
    } finally {
      setLoading(false)
    }
  }, [selectedCircle])

  useEffect(() => {
    refresh()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const selectCircle = useCallback((circle: CareCircle) => {
    setSelectedCircle(circle)
  }, [])

  return { circles, selectedCircle, selectCircle, loading, error, refresh }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd /home/j/CerebrumCraft/ada/web && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```
git add web/src/hooks/useCircles.ts
git commit -m "feat(phase9a): add useCircles hook"
```

---

### Task 11: Frontend — CircleSelector + CircleMembers Components

**Files:**
- Create: `web/src/components/CircleSelector.tsx`
- Create: `web/src/components/CircleMembers.tsx`

- [ ] **Step 1: Create CircleSelector**

```tsx
// web/src/components/CircleSelector.tsx
import type { CareCircle } from '../types'

interface CircleSelectorProps {
  circles: CareCircle[]
  selected: CareCircle | null
  onSelect: (circle: CareCircle) => void
}

export function CircleSelector({ circles, selected, onSelect }: CircleSelectorProps) {
  if (circles.length <= 1) return null

  return (
    <div className="circle-selector">
      <label className="circle-selector__label" htmlFor="circle-select">
        Patient:
      </label>
      <select
        id="circle-select"
        className="circle-selector__select"
        value={selected?.id ?? ''}
        onChange={(e) => {
          const circle = circles.find((c) => c.id === e.target.value)
          if (circle) onSelect(circle)
        }}
      >
        {circles.map((c) => (
          <option key={c.id} value={c.id}>
            {c.patient_name}
          </option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 2: Create CircleMembers**

```tsx
// web/src/components/CircleMembers.tsx
import { useCallback, useEffect, useState } from 'react'

import { addCircleMember, getCircleMembers, removeCircleMember } from '../api/client'
import type { CareCircleMember } from '../types'

interface CircleMembersProps {
  circleId: string
  currentUserRole: string
}

const ROLE_LABELS: Record<string, string> = {
  primary_caregiver: 'Primary Caregiver',
  family: 'Family',
  clinician: 'Clinician',
}

export function CircleMembers({ circleId, currentUserRole }: CircleMembersProps) {
  const [members, setMembers] = useState<CareCircleMember[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<string>('family')
  const [error, setError] = useState<string | null>(null)

  const canManage = currentUserRole === 'primary_caregiver' || currentUserRole === 'clinician'
  const canRemove = currentUserRole === 'primary_caregiver'

  const fetchMembers = useCallback(async () => {
    try {
      const data = await getCircleMembers(circleId)
      setMembers(data)
    } catch {
      setError('Failed to load members')
    }
  }, [circleId])

  useEffect(() => {
    fetchMembers()
  }, [fetchMembers])

  const handleAdd = async () => {
    if (!email.trim()) return
    try {
      setError(null)
      await addCircleMember(circleId, { email: email.trim(), role })
      setEmail('')
      setShowAdd(false)
      await fetchMembers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add member')
    }
  }

  const handleRemove = async (userId: string) => {
    try {
      setError(null)
      await removeCircleMember(circleId, userId)
      await fetchMembers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    }
  }

  return (
    <div className="circle-members">
      <div className="circle-members__header">
        <h3 className="circle-members__title">Care Team</h3>
        {canManage && (
          <button
            className="circle-members__add-btn"
            onClick={() => setShowAdd(!showAdd)}
          >
            {showAdd ? 'Cancel' : '+ Add Member'}
          </button>
        )}
      </div>

      {error && <div className="circle-members__error">{error}</div>}

      {showAdd && (
        <div className="circle-members__add-form">
          <input
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="circle-members__input"
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="circle-members__role-select"
          >
            <option value="family">Family</option>
            <option value="primary_caregiver">Primary Caregiver</option>
            <option value="clinician">Clinician</option>
          </select>
          <button className="circle-members__submit-btn" onClick={handleAdd}>
            Add
          </button>
        </div>
      )}

      <ul className="circle-members__list">
        {members.map((m) => (
          <li key={m.id} className="circle-members__item">
            <span className="circle-members__email">{m.email}</span>
            <span className={`circle-members__role circle-members__role--${m.role}`}>
              {ROLE_LABELS[m.role] ?? m.role}
            </span>
            {canRemove && m.role !== 'primary_caregiver' && (
              <button
                className="circle-members__remove-btn"
                onClick={() => handleRemove(m.user_id)}
                aria-label={`Remove ${m.email}`}
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 3: Verify compiles**

Run: `cd /home/j/CerebrumCraft/ada/web && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```
git add web/src/components/CircleSelector.tsx web/src/components/CircleMembers.tsx
git commit -m "feat(phase9a): add CircleSelector and CircleMembers components"
```

---

### Task 12: Frontend — Integrate into CaregiverDashboard

**Files:**
- Modify: `web/src/components/CaregiverDashboard.tsx`
- Modify: `web/src/App.css` (add circle styles)

- [ ] **Step 1: Update CaregiverDashboard**

In `web/src/components/CaregiverDashboard.tsx`:

1. Add imports at top:
```typescript
import { useCircles } from '../hooks/useCircles'
import { CircleSelector } from './CircleSelector'
import { CircleMembers } from './CircleMembers'
import { getCaregiverOverviewForPatient } from '../api/client'
```

2. Add circle state inside the component:
```typescript
const { circles, selectedCircle, selectCircle, loading: circlesLoading } = useCircles()
```

3. Update `fetchData` to use selected circle's patient_id instead of the old single-patient fetch:
```typescript
const fetchData = useCallback(async () => {
    if (!selectedCircle) return
    try {
        const result = await getCaregiverOverviewForPatient(selectedCircle.patient_id)
        setData(result)
    } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
    }
}, [selectedCircle])
```

4. Update useEffect to depend on fetchData:
```typescript
useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60_000)
    return () => clearInterval(interval)
}, [fetchData])
```

5. Add CircleSelector to header area:
```tsx
<CircleSelector circles={circles} selected={selectedCircle} onSelect={selectCircle} />
```

6. Add CircleMembers card section (after existing cards):
```tsx
{selectedCircle && (
    <CircleMembers circleId={selectedCircle.id} currentUserRole={selectedCircle.my_role} />
)}
```

- [ ] **Step 2: Add CSS styles**

In `web/src/App.css`, add the circle-selector and circle-members styles. Key classes:

```css
.circle-selector { display: flex; align-items: center; gap: 0.5rem; }
.circle-selector__label { font-size: 0.875rem; color: var(--text-secondary); }
.circle-selector__select { padding: 0.375rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-primary); font-size: 0.875rem; }

.circle-members { background: var(--card-bg); border-radius: var(--radius-md); padding: 1.25rem; box-shadow: var(--shadow-sm); }
.circle-members__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.circle-members__title { font-size: 1rem; font-weight: 600; }
.circle-members__add-btn, .circle-members__submit-btn { padding: 0.375rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-primary); cursor: pointer; font-size: 0.8125rem; }
.circle-members__add-form { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.circle-members__input, .circle-members__role-select { padding: 0.375rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-primary); font-size: 0.875rem; }
.circle-members__input { flex: 1; }
.circle-members__list { list-style: none; padding: 0; margin: 0; }
.circle-members__item { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0; border-bottom: 1px solid var(--border); }
.circle-members__item:last-child { border-bottom: none; }
.circle-members__email { flex: 1; font-size: 0.875rem; }
.circle-members__role { font-size: 0.75rem; padding: 0.125rem 0.5rem; border-radius: 9999px; background: var(--bg-tertiary); }
.circle-members__role--primary_caregiver { background: #e8f4fd; color: #1976d2; }
.circle-members__role--clinician { background: #e8f5e9; color: #2e7d32; }
.circle-members__remove-btn { padding: 0.25rem 0.5rem; font-size: 0.75rem; border: none; background: none; color: #d32f2f; cursor: pointer; }
.circle-members__error { color: #d32f2f; font-size: 0.8125rem; margin-bottom: 0.75rem; }
```

- [ ] **Step 3: Verify compiles**

Run: `cd /home/j/CerebrumCraft/ada/web && npx tsc --noEmit`

- [ ] **Step 4: Run backend tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add web/src/components/CaregiverDashboard.tsx web/src/App.css
git commit -m "feat(phase9a): integrate care circles into caregiver dashboard"
```

---

### Task 13: Config — Board Suggestion Placeholder

**Files:**
- Modify: `ada/core/config.py` (add after DailySummaryConfig, around line 75)
- Modify: `config/default.toml` (add after [agents.daily_summary])

- [ ] **Step 1: Add config class**

In `ada/core/config.py`, after `DailySummaryConfig`:

```python
class BoardSuggestionConfig(BaseModel):
    """Configuration for the board suggestion agent (Phase 9b)."""

    enabled: bool = False
    debounce_seconds: float = 5.0
```

Add to `AgentsConfig`:

```python
board_suggestion: BoardSuggestionConfig = BoardSuggestionConfig()
```

- [ ] **Step 2: Add TOML section**

In `config/default.toml`, after `[agents.daily_summary]`:

```toml
[agents.board_suggestion]
enabled = false
debounce_seconds = 5.0
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```
git add ada/core/config.py config/default.toml
git commit -m "feat(phase9a): add board_suggestion config placeholder"
```

---

## Summary

| Task | Component | New Tests |
|------|-----------|-----------|
| 1 | Pydantic models | - |
| 2 | Schema + CRUD | 9 unit |
| 3 | Migration | 4 unit |
| 4 | Event types | - |
| 5 | Auth helper | 4 unit |
| 6 | Circle REST routes | 8 unit |
| 7 | Caregiver refactor | Existing updated |
| 8 | Integration test | 1 integration (7 assertions) |
| 9 | Frontend types + API | TS compilation |
| 10 | useCircles hook | TS compilation |
| 11 | CircleSelector + CircleMembers | TS compilation |
| 12 | Dashboard integration | TS + backend |
| 13 | Config placeholder | Backend |

**Total new tests:** ~26 unit + 1 integration
**Estimated total after Phase 9a:** 845+ tests
