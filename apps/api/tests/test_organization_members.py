from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing import get_or_create_subscription_for_organization


async def _register_and_login(client: AsyncClient, email: str, full_name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": full_name},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_org(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post("/api/v1/organizations", json={"name": name}, headers=_auth(token))
    return resp.json()["id"]


async def test_list_members_returns_owner_and_invited_member(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner@example.com", "Org Owner")
    org_id = await _create_org(client, owner_token, "Acme Co")

    # Owner alone first.
    owner_only = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))
    assert owner_only.status_code == 200, owner_only.text
    assert len(owner_only.json()) == 1
    assert owner_only.json()[0]["role"] == "owner"
    assert owner_only.json()[0]["user_email"] == "owner@example.com"
    assert owner_only.json()[0]["user_full_name"] == "Org Owner"

    # Invite an existing user directly (immediate Membership, no email needed).
    member_token = await _register_and_login(client, "member@example.com", "Org Member")
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": "member@example.com", "role": "analyst"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201, invite_resp.text

    members_resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))
    assert members_resp.status_code == 200
    members = {m["user_email"]: m for m in members_resp.json()}
    assert set(members) == {"owner@example.com", "member@example.com"}
    assert members["member@example.com"]["role"] == "analyst"

    # Any member — not just the owner — can read the member list.
    as_member = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(member_token))
    assert as_member.status_code == 200
    assert len(as_member.json()) == 2


async def test_non_member_cannot_list_organization_members(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner2@example.com")
    outsider_token = await _register_and_login(client, "outsider2@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(outsider_token))
    assert resp.status_code == 403


async def test_list_members_requires_authentication(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner3@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    resp = await client.get(f"/api/v1/organizations/{org_id}/members")
    assert resp.status_code == 401


async def _invite(client: AsyncClient, owner_token: str, org_id: str, email: str, role: str = "analyst"):
    return await client.post(
        f"/api/v1/organizations/{org_id}/invite",
        json={"email": email, "role": role},
        headers=_auth(owner_token),
    )


async def _membership_id_for(client: AsyncClient, token: str, org_id: str, email: str) -> str:
    members = (await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(token))).json()
    return next(m["id"] for m in members if m["user_email"] == email)


async def test_owner_can_remove_a_member(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner4@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    await _register_and_login(client, "member4@example.com")
    await _invite(client, owner_token, org_id, "member4@example.com")
    membership_id = await _membership_id_for(client, owner_token, org_id, "member4@example.com")

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{membership_id}", headers=_auth(owner_token)
    )
    assert resp.status_code == 204

    members = (await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))).json()
    assert {m["user_email"] for m in members} == {"owner4@example.com"}


async def test_owner_can_change_a_members_role(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner5@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    await _register_and_login(client, "member5@example.com")
    await _invite(client, owner_token, org_id, "member5@example.com", role="analyst")
    membership_id = await _membership_id_for(client, owner_token, org_id, "member5@example.com")

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{membership_id}",
        json={"role": "viewer"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "viewer"

    members = (await client.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(owner_token))).json()
    assert next(m for m in members if m["user_email"] == "member5@example.com")["role"] == "viewer"


async def test_change_role_rejects_unknown_role(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner6@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    await _register_and_login(client, "member6@example.com")
    await _invite(client, owner_token, org_id, "member6@example.com")
    membership_id = await _membership_id_for(client, owner_token, org_id, "member6@example.com")

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{membership_id}",
        json={"role": "superadmin"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400


async def test_non_manager_cannot_remove_or_change_role(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    viewer_token = await _register_and_login(client, "viewer7@example.com")
    await _invite(client, owner_token, org_id, "viewer7@example.com", role="viewer")
    viewer_membership_id = await _membership_id_for(client, owner_token, org_id, "viewer7@example.com")

    denied_delete = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{viewer_membership_id}", headers=_auth(viewer_token)
    )
    assert denied_delete.status_code == 403

    denied_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{viewer_membership_id}",
        json={"role": "analyst"},
        headers=_auth(viewer_token),
    )
    assert denied_patch.status_code == 403


async def test_cannot_remove_the_last_owner(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner8@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    owner_membership_id = await _membership_id_for(client, owner_token, org_id, "owner8@example.com")

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{owner_membership_id}", headers=_auth(owner_token)
    )
    assert resp.status_code == 400


async def test_cannot_demote_the_last_owner(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner9@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    owner_membership_id = await _membership_id_for(client, owner_token, org_id, "owner9@example.com")

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{owner_membership_id}",
        json={"role": "administrator"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400


async def test_removing_a_non_last_owner_succeeds(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner10@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")
    await _register_and_login(client, "secondowner10@example.com")
    await _invite(client, owner_token, org_id, "secondowner10@example.com", role="owner")
    second_owner_id = await _membership_id_for(client, owner_token, org_id, "secondowner10@example.com")

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{second_owner_id}", headers=_auth(owner_token)
    )
    assert resp.status_code == 204


async def test_invite_blocked_once_team_member_limit_reached(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await _register_and_login(client, "owner11@example.com")
    org_id = await _create_org(client, owner_token, "Acme Co")

    # "business" plan caps team members at 5 (app/core/plans.py). A
    # Subscription is created lazily on first access (Phase 4 pattern) —
    # nothing has touched billing for this org yet, so create it via the
    # same service function the app uses, then bump it onto a paid plan
    # directly, same as other tests needing a non-free plan without a
    # real Stripe call.
    subscription = await get_or_create_subscription_for_organization(db_session, org_id)
    subscription.plan_id = "business"
    await db_session.commit()

    # Owner (1) + 4 invited members = 5, exactly at the business plan's cap.
    for i in range(4):
        email = f"teammate11-{i}@example.com"
        await _register_and_login(client, email)
        resp = await _invite(client, owner_token, org_id, email)
        assert resp.status_code == 201, resp.text

    await _register_and_login(client, "teammate11-overflow@example.com")
    blocked = await _invite(client, owner_token, org_id, "teammate11-overflow@example.com")
    assert blocked.status_code == 402
    assert "team members" in blocked.json()["detail"].lower()
