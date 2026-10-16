from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "analyst"


class UpdateMembershipRoleRequest(BaseModel):
    role: str


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    organization_id: str
    role: str


class MembershipDetailOut(BaseModel):
    """MembershipOut plus the member's own email/name, for a UI that
    lists who's actually in an organization — MembershipOut alone only
    gives a user_id, which isn't useful to render directly."""

    id: str
    user_id: str
    organization_id: str
    role: str
    user_email: str
    user_full_name: str


class PendingInviteOut(BaseModel):
    """Returned instead of a MembershipOut when the invitee doesn't have
    an account yet — there's no Membership to show until they register
    via the emailed link."""

    status: str = "invite_emailed"
    email: str
    role: str


class InvitePreviewOut(BaseModel):
    """What the frontend shows on the "you've been invited" page before
    the invitee registers — deliberately not the full invite token
    record (no need to expose organization_id as a raw id to an
    unauthenticated viewer beyond what they need to decide)."""

    organization_name: str
    role: str
    email: str
