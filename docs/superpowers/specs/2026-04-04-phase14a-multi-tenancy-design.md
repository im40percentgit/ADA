# Phase 14a — Multi-Tenancy

## Context

Ada currently operates as a single-tenant application — all users share one flat data space. To deploy Ada for multiple clinics, practices, or solo practitioners, the system needs tenant isolation. Phase 14a adds organization accounts with tenant-scoped data access.

## Tenancy Model

**Shared database, tenant column.** Every data table gets an `organization_id` foreign key. Queries filter by the current user's organization. This is the simplest model for Ada's current SQLite architecture while providing logical data isolation.

**Tenant = Organization.** An organization represents a therapy practice, clinic, care facility, or solo practitioner. Solo practitioners are a one-person organization.

---

## 1. Tenant Data Model

### New Tables

**`organizations`**
```sql
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'free' CHECK(plan IN ('free', 'pro', 'enterprise')),
    settings    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`organization_members`**
```sql
CREATE TABLE IF NOT EXISTS organization_members (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    user_id         TEXT NOT NULL REFERENCES users(id),
    role            TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(organization_id, user_id)
);
```

### Modified Tables

**`users`** — add `organization_id TEXT REFERENCES organizations(id)` (nullable). Null = solo/unaffiliated user.

**`patients`** — add `organization_id TEXT REFERENCES organizations(id)` (nullable). Null = belongs to solo user (existing behavior).

### Migration

Existing users and patients get `organization_id = NULL`. They continue to work in "solo mode" — seeing only their own data, exactly as before. No data migration needed beyond the schema change.

---

## 2. Tenant-Scoped Queries

### TenantContext

New dependency for FastAPI routes: `get_tenant_context(user: User) -> TenantContext`.

```python
@dataclass
class TenantContext:
    user_id: str
    organization_id: str | None  # None = solo mode
    org_role: str | None         # owner/admin/member or None
```

Resolved from:
1. Look up `organization_members` for the current user
2. If found: set `organization_id` and `org_role`
3. If not found: solo mode (`organization_id = None`)

### Query Patterns

**With organization (tenant mode):**
```python
SELECT * FROM patients WHERE organization_id = ?
```

**Without organization (solo mode):**
```python
SELECT * FROM patients WHERE caregiver_id = ? OR id IN (
    SELECT patient_id FROM care_circle_members WHERE user_id = ?
)
```
(Existing behavior — users see patients they're connected to.)

### Affected Queries

All patient-scoped queries need tenant filtering:
- `get_patients()` → `get_patients(org_id=None, user_id=None)`
- `get_sessions()`, `get_assessments()`, etc. — filter through patient's org_id
- Care circles — scoped to org when in tenant mode
- Daily summaries, medications, appointments — all through patient → org chain

### Implementation Approach

Rather than modifying every existing query, add a **tenant filter layer**:
- New `get_patients_for_context(tenant: TenantContext)` method that dispatches to the correct query pattern
- Existing methods gain an optional `organization_id` parameter
- Routes use `TenantContext` to pass the right filter

---

## 3. Organization Management API

### Endpoints

**`POST /api/organizations`** — Create organization
- Request: `{ "name": "...", "slug": "..." }`
- Creator becomes owner
- Adds user as organization_member with role=owner
- Updates user's organization_id
- Returns organization record

**`GET /api/organizations/{id}`** — Get organization details
- Requires membership
- Returns org + member count

**`PUT /api/organizations/{id}`** — Update organization
- Requires owner/admin role
- Accepts partial update: `{ "name": "...", "settings": {...} }`

**`GET /api/organizations/{id}/members`** — List members
- Requires membership
- Returns members with roles and user info

**`POST /api/organizations/{id}/invite`** — Invite user
- Requires admin/owner role
- Request: `{ "email": "...", "role": "member" }`
- If user exists: adds to org_members
- If user doesn't exist: creates invite record (deferred — for now, user must exist)

**`PUT /api/organizations/{id}/members/{user_id}`** — Update member role
- Requires owner role
- Request: `{ "role": "admin" }`

**`DELETE /api/organizations/{id}/members/{user_id}`** — Remove member
- Requires admin/owner role (cannot remove self if sole owner)

---

## 4. Organization Admin UI

### Settings Page Extension

Add "Organization" section to SettingsPage (below companion settings):

**No Organization (solo mode):**
- Card: "Create an Organization" — name input, "Create" button
- Description: "Organizations let you manage patients and staff under one account."

**Has Organization:**
- Org name (editable by admin/owner)
- Plan badge (free/pro/enterprise)
- Member list: name, email, role badge, remove button (admin/owner only)
- Invite section: email input + role selector + "Invite" button (admin/owner only)
- "Leave Organization" button (for non-owners)

### Navigation

No new views needed — organization management lives inside the existing Settings page.

---

## 5. Tenant Isolation Tests

### Integration Tests

- User in org A creates patient → user in org B cannot see that patient
- Solo user creates patient → org user cannot see that patient
- User in org A cannot access org B's sessions/assessments/medications
- Admin can invite, owner can change roles
- Non-admin cannot invite or remove members
- Removing sole owner is prevented
- Creating org sets user's organization_id

---

## Verification Plan

1. **Create org:** register → create org → verify org appears in settings
2. **Invite member:** invite another user → they see the org's patients
3. **Tenant isolation:** user in org A → cannot see org B's patients (API returns empty/403)
4. **Solo mode:** user without org → sees only their connected patients (existing behavior)
5. **Admin controls:** owner can change roles, admin can invite, member cannot
6. **Backward compatibility:** existing users/patients with null org_id continue to work

---

## Files Summary

### New Files
- `ada/api/routes/organizations.py`
- `ada/api/tenant.py` — TenantContext dependency
- `tests/unit/test_organizations.py`
- `tests/integration/test_tenant_isolation.py`

### Modified Files
- `ada/core/state.py` — organizations + organization_members tables, CRUD, tenant-scoped queries
- `ada/api/app.py` — register organizations router
- `ada/api/routes/patients.py` — use TenantContext for patient queries
- `ada/api/routes/caregiver.py` — tenant-scoped overview
- `web/src/types/index.ts` — Organization, OrganizationMember types
- `web/src/api/client.ts` — org API functions
- `web/src/components/SettingsPage.tsx` — org management section
- `web/test/msw/handlers.ts` — org endpoint handlers
- `web/test/factories.ts` — org factories
