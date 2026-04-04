"""
Tenant context for multi-tenancy scoping.

Provides a TenantContext dataclass and a FastAPI dependency that resolves the
current user's organization membership. Routes use TenantContext to decide
whether to scope queries to an organization (tenant mode) or fall back to
per-user behavior (solo mode).

@decision DEC-TENANT-001
@title TenantContext as FastAPI dependency — org-scoped vs solo mode
@status accepted
@rationale A single dependency encapsulates the org lookup and exposes a clean
    interface (organization_id / org_role / is_tenant_mode) that routes consume
    without duplicating membership queries. Solo users (no org membership) get
    organization_id=None and existing per-user behavior applies unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request

from ada.api.auth import get_current_user
from ada.models.user import User


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Resolved tenancy context for the current request.

    Attributes:
        user_id: Authenticated user's ID.
        organization_id: Org the user belongs to, or None for solo mode.
        org_role: User's role in the organization (owner/admin/member), or None.
    """

    user_id: str
    organization_id: str | None  # None = solo mode
    org_role: str | None  # owner/admin/member or None

    @property
    def is_tenant_mode(self) -> bool:
        """True when the user is operating within an organization."""
        return self.organization_id is not None


async def get_tenant_context(
    request: Request,
    user: User = Depends(get_current_user),
) -> TenantContext:
    """FastAPI dependency that resolves the caller's tenant context.

    Looks up the user's organization membership. If the user belongs to an
    organization, returns a tenant-mode context with org_id and role.
    Otherwise returns a solo-mode context (organization_id=None).
    """
    state = request.app.state.state_manager

    # get_user_organization returns the org row (id, name, slug, ...)
    org = await state.get_user_organization(user.id)
    if org:
        # Fetch the membership role separately — get_user_organization returns
        # the organization row, not the membership row.
        members = await state.list_organization_members(org["id"])
        role = None
        for m in members:
            if m["user_id"] == user.id:
                role = m["role"]
                break
        return TenantContext(
            user_id=user.id,
            organization_id=org["id"],
            org_role=role,
        )

    return TenantContext(user_id=user.id, organization_id=None, org_role=None)
