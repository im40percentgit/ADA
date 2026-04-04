# Phase 14a — Multi-Tenancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add organization-based multi-tenancy with shared-DB tenant column isolation, org management API, admin UI, and comprehensive tenant isolation tests.

**Architecture:** New organizations and organization_members tables. TenantContext FastAPI dependency resolves current user's org. Patient queries filter by organization_id when in tenant mode, fall back to existing user-scoped behavior in solo mode. Org management in Settings page.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), aiosqlite (persistence), existing UI component library

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase14a-multi-tenancy-design.md`

---

## Task 1: Tenant Data Model + CRUD

**Files:**
- Modify: `ada/core/state.py` — add tables, migration, CRUD
- Create: `tests/unit/test_organizations.py`

- [ ] Add `organizations` and `organization_members` tables to `_SCHEMA` in state.py. Add `organization_id` column to `users` and `patients` tables (nullable FK). Add ALTER TABLE migration for existing DBs.
- [ ] Add CRUD methods: `create_organization(org)`, `get_organization(org_id)`, `update_organization(org_id, updates)`, `list_organization_members(org_id)`, `add_organization_member(org_id, user_id, role)`, `update_member_role(org_id, user_id, role)`, `remove_organization_member(org_id, user_id)`, `get_user_organization(user_id) -> dict | None`.
- [ ] Add tenant-scoped patient query: `get_patients_for_organization(org_id) -> list[dict]`.
- [ ] Write `tests/unit/test_organizations.py`: create org, add member, list members, role update, remove member, get user's org, patient org scoping.
- [ ] Run tests, commit: `feat(phase14a): add tenant data model with organizations and member management`

---

## Task 2: TenantContext + Route Integration

**Files:**
- Create: `ada/api/tenant.py`
- Modify: `ada/api/routes/patients.py`
- Modify: `ada/api/routes/caregiver.py`
- Create: `tests/integration/test_tenant_isolation.py`

- [ ] Create `ada/api/tenant.py`: `TenantContext` dataclass (user_id, organization_id, org_role). `get_tenant_context(user, request)` FastAPI dependency — looks up user's org membership from state, returns context.
- [ ] Modify patient routes: use `TenantContext` to filter `get_patients()`. In tenant mode: filter by org_id. In solo mode: existing behavior (user's connected patients).
- [ ] Modify caregiver overview: scope to tenant's patients when in org mode.
- [ ] Write `tests/integration/test_tenant_isolation.py`: user in org A can't see org B's patients, solo user sees only their connected patients, cross-tenant session/assessment access prevented.
- [ ] Run tests, commit: `feat(phase14a): add TenantContext and tenant-scoped patient queries`

---

## Task 3: Organization Management API

**Files:**
- Create: `ada/api/routes/organizations.py`
- Modify: `ada/api/app.py`

- [ ] Create `ada/api/routes/organizations.py` with all endpoints: POST create, GET detail, PUT update, GET members, POST invite, PUT member role, DELETE member. Follow existing route patterns.
- [ ] Auth: membership required for GET, admin/owner for writes, owner-only for role changes. Prevent removing sole owner.
- [ ] Register router in app.py.
- [ ] Write unit tests for all endpoints.
- [ ] Run tests, commit: `feat(phase14a): add organization management REST API`

---

## Task 4: Frontend Types + API + Settings UI

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/SettingsPage.tsx`
- Modify: `web/test/msw/handlers.ts`
- Modify: `web/test/factories.ts`

- [ ] Add TypeScript types: `Organization`, `OrganizationMember`.
- [ ] Add API functions: `createOrganization`, `getOrganization`, `updateOrganization`, `listOrgMembers`, `inviteOrgMember`, `updateMemberRole`, `removeOrgMember`, `getMyOrganization`.
- [ ] Add MSW handlers + factories.
- [ ] Extend SettingsPage: add "Organization" section below companion settings. Solo mode: "Create Organization" card. Org mode: org name, members list, invite form, role management.
- [ ] Run tests, commit: `feat(phase14a): add organization management UI in settings`

---

## Verification Checklist

- [ ] Backend: all org + tenant isolation tests pass
- [ ] Frontend: all tests pass
- [ ] Create org → appears in settings
- [ ] Invite member → they see org patients
- [ ] Tenant isolation → org A can't see org B data
- [ ] Solo mode → existing behavior preserved
- [ ] Admin controls → proper role enforcement
