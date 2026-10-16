import csv
import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_email_sender_optional_dep
from app.core.config import get_settings
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.email_token import EmailTokenPurpose
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.user import User
from app.schemas.audit_log import AuditLogOut
from app.schemas.organization import (
    InviteMemberRequest,
    InvitePreviewOut,
    MembershipDetailOut,
    MembershipOut,
    OrganizationCreate,
    OrganizationOut,
    PendingInviteOut,
    UpdateMembershipRoleRequest,
)
from app.services import billing
from app.services.audit import record_audit_event
from app.services.authz import require_membership, require_org_manager
from app.services.email import EmailMessage, EmailSender
from app.services.email_tokens import EmailTokenError, create_org_invite_token, peek_token

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:8]}"


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = Organization(name=payload.name, slug=_slugify(payload.name))
    db.add(org)
    await db.flush()

    owner_membership = Membership(
        user_id=current_user.id,
        organization_id=org.id,
        role=MembershipRole.OWNER,
    )
    db.add(owner_membership)
    await record_audit_event(
        db,
        event_type="organization.created",
        actor_user_id=current_user.id,
        organization_id=org.id,
        metadata={"name": org.name},
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationOut])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Organization]:
    result = await db.execute(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.get("/{organization_id}/members", response_model=list[MembershipDetailOut])
async def list_organization_members(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MembershipDetailOut]:
    """Any member can see who else is in the organization — the same
    "any role can read, only owner/admin can govern" split
    require_workspace_access/require_workspace_write_access already use
    for workspaces. Only invite/audit-log/billing-writes are manager-only."""
    await require_membership(db, current_user.id, organization_id)

    result = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at)
    )
    return [
        MembershipDetailOut(
            id=membership.id,
            user_id=membership.user_id,
            organization_id=membership.organization_id,
            role=membership.role,
            user_email=user.email,
            user_full_name=user.full_name,
        )
        for membership, user in result.all()
    ]


@router.post("/{organization_id}/invite", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def invite_member(
    organization_id: str,
    payload: InviteMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender | None = Depends(get_email_sender_optional_dep),
):
    await require_org_manager(db, current_user.id, organization_id)

    try:
        role = MembershipRole(payload.role)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role: {payload.role}")

    # Checked for both branches below (email-invite and direct-add): the
    # email-invite branch doesn't create a Membership until the invitee
    # accepts, so this can only compare against the *current* member
    # count, not pending invites — an org could still stack up accepted
    # invites past capacity if several land at once. Good enough to stop
    # the common case (inviting past capacity) without new infrastructure
    # to track pending-invite "reservations".
    subscription = await billing.get_or_create_subscription_for_organization(db, organization_id)
    try:
        await billing.check_team_member_limit(db, subscription, organization_id)
    except billing.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc

    invitee = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if invitee is None:
        if email_sender is None:
            # No transactional email integration configured — same
            # fallback behavior as before this feature existed.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "No account found for that email, and email invites for new accounts aren't "
                "configured yet (no SMTP_HOST set) — ask them to register first, or set up "
                "SMTP to invite people who don't have an account.",
            )

        org = await db.get(Organization, organization_id)
        raw_token = await create_org_invite_token(
            db, target_email=payload.email, organization_id=organization_id, role=role.value
        )
        invite_url = f"{get_settings().frontend_base_url}/accept-invite?token={raw_token}"
        email_sender.send(
            EmailMessage(
                to=payload.email,
                subject=f"You've been invited to join {org.name} on DataLume Intelligence",
                text_body=(
                    f"{current_user.full_name} invited you to join {org.name} as {role.value}.\n\n"
                    f"Accept the invite and create your account:\n{invite_url}\n\n"
                    "This link expires in 7 days."
                ),
            )
        )
        await record_audit_event(
            db,
            event_type="organization.invite_emailed",
            actor_user_id=current_user.id,
            organization_id=organization_id,
            metadata={"invitee_email": payload.email, "role": role.value},
        )
        await db.commit()
        # A Response returned directly bypasses response_model entirely
        # (FastAPI's documented behavior) — needed here since this branch
        # has no Membership to serialize as one yet.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=PendingInviteOut(email=payload.email, role=role.value).model_dump(),
        )

    existing = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == invitee.id,
                Membership.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this organization")

    membership = Membership(user_id=invitee.id, organization_id=organization_id, role=role)
    db.add(membership)
    await record_audit_event(
        db,
        event_type="organization.member_invited",
        actor_user_id=current_user.id,
        organization_id=organization_id,
        metadata={"invitee_email": payload.email, "role": role.value},
    )
    await db.commit()
    await db.refresh(membership)
    return membership


async def _is_last_owner(db: AsyncSession, membership: Membership) -> bool:
    if MembershipRole(membership.role) != MembershipRole.OWNER:
        return False
    result = await db.execute(
        select(func.count(Membership.id)).where(
            Membership.organization_id == membership.organization_id,
            Membership.role == MembershipRole.OWNER,
        )
    )
    return result.scalar_one() <= 1


@router.delete("/{organization_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_member(
    organization_id: str,
    membership_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await require_org_manager(db, current_user.id, organization_id)

    membership = await db.get(Membership, membership_id)
    if membership is None or membership.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")

    if await _is_last_owner(db, membership):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot remove the last owner of an organization — make someone else an owner first.",
        )

    await record_audit_event(
        db,
        event_type="organization.member_removed",
        actor_user_id=current_user.id,
        organization_id=organization_id,
        metadata={"removed_user_id": membership.user_id, "role": MembershipRole(membership.role).value},
    )
    await db.delete(membership)
    await db.commit()


@router.patch("/{organization_id}/members/{membership_id}", response_model=MembershipOut)
async def update_member_role(
    organization_id: str,
    membership_id: str,
    payload: UpdateMembershipRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Membership:
    await require_org_manager(db, current_user.id, organization_id)

    try:
        new_role = MembershipRole(payload.role)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role: {payload.role}")

    membership = await db.get(Membership, membership_id)
    if membership is None or membership.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")

    if new_role != MembershipRole.OWNER and await _is_last_owner(db, membership):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot change the last owner's role away from owner — make someone else an owner first.",
        )

    old_role = MembershipRole(membership.role).value
    membership.role = new_role
    await record_audit_event(
        db,
        event_type="organization.member_role_changed",
        actor_user_id=current_user.id,
        organization_id=organization_id,
        metadata={"member_user_id": membership.user_id, "old_role": old_role, "new_role": new_role.value},
    )
    await db.commit()
    await db.refresh(membership)
    return membership


@router.get("/invites/{token}", response_model=InvitePreviewOut)
async def preview_invite(token: str, db: AsyncSession = Depends(get_db)) -> InvitePreviewOut:
    """Deliberately unauthenticated — the invitee doesn't have an account
    yet, so there's nothing to authenticate as. Lets the frontend render
    "You've been invited to join <org> as <role>" before the invitee
    fills in the registration form at POST /auth/register with this
    same token as invite_token."""
    try:
        entry = await peek_token(db, token, purpose=EmailTokenPurpose.ORG_INVITE)
    except EmailTokenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    org = await db.get(Organization, entry.organization_id)
    if org is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or invalid token.")

    return InvitePreviewOut(organization_name=org.name, role=entry.role, email=entry.target_email)


@router.get("/{organization_id}/audit-log")
async def get_organization_audit_log(
    organization_id: str,
    format: str = "json",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """"Advanced audit exports" — restricted to org managers (owner/
    admin), same as other organization-governance actions. Covers the
    documented subset of events in app/services/audit.py, not every
    action in the app."""
    await require_org_manager(db, current_user.id, organization_id)

    if format not in ("json", "csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format must be 'json' or 'csv'")

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(5000)
    )
    entries = list(result.scalars().all())

    if format == "json":
        return [AuditLogOut.model_validate(e).model_dump(mode="json") for e in entries]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "event_type", "actor_user_id", "workspace_id", "created_at", "metadata"])
    for e in entries:
        writer.writerow([e.id, e.event_type, e.actor_user_id or "", e.workspace_id or "", e.created_at.isoformat(), e.event_metadata])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-log-{organization_id}.csv"'},
    )
