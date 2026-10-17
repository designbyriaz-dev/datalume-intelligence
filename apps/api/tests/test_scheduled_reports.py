import datetime as dt

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report
from app.models.scheduled_report import ScheduledReport
from app.services.distributed_lock import release_lock, try_acquire_lock
from app.services.email import EmailMessage
from app.services.scheduled_reports import SCHEDULER_LOCK_ID, run_due_scheduled_reports
from app.services.storage import ObjectStorage


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


SAMPLE_CSV = b"unit,rent\nA1,1000\nA2,2000\n"


async def _setup_table(client: AsyncClient, token: str) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Scheduled Test", "industry": "general"}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", SAMPLE_CSV, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return workspace_id, version["tables"][0]["id"]


async def test_create_and_list_scheduled_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "weekly"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["frequency"] == "weekly"
    assert body["is_active"] is True
    assert body["last_run_at"] is None

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/scheduled-reports", headers=_auth(token))
    assert len(list_resp.json()) == 1


async def test_rejects_invalid_report_type_and_frequency(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner2@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    bad_type = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "nope", "frequency": "weekly"},
        headers=_auth(token),
    )
    assert bad_type.status_code == 400

    bad_freq = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "hourly"},
        headers=_auth(token),
    )
    assert bad_freq.status_code == 400


async def test_commercial_property_report_requires_matching_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3@example.com")
    workspace_id, table_id = await _setup_table(client, token)  # workspace industry is "general"

    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "commercial_property_portfolio", "frequency": "monthly"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_newly_supported_report_types_require_matching_industry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner3b@example.com")
    workspace_id, table_id = await _setup_table(client, token)  # workspace industry is "general"

    for report_type in (
        "residential_property_portfolio",
        "residential_repairs_maintenance",
        "social_housing_asset",
        "social_housing_compliance_exceptions",
        "business_performance",
    ):
        resp = await client.post(
            f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
            json={"dataset_table_id": table_id, "report_type": report_type, "frequency": "monthly"},
            headers=_auth(token),
        )
        assert resp.status_code == 400, f"{report_type} should be rejected for a general workspace"


async def test_run_due_scheduled_reports_generates_and_reschedules(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    """Exercises the real scheduler logic directly — no waiting on
    wall-clock time or the APScheduler background job, same pattern as
    the AI planner's fake-client tests: call the actual function that
    the real background job also calls."""
    token = await _register_and_login(client, "owner4@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]

    # Force it into the past so it's "due" without waiting a real day.
    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    scheduled.next_run_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    await db_session.commit()

    now = dt.datetime.now(dt.timezone.utc)
    generated = await run_due_scheduled_reports(db_session, test_storage, now=now)

    assert len(generated) == 1
    assert generated[0].report_type == "data_quality"
    assert generated[0].file_size_bytes > 0

    await db_session.refresh(scheduled)
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip (naive
    # datetimes returned); Postgres preserves it. Matching tzinfo to
    # whichever the DB actually returned (same idiom as
    # app/services/email_tokens.py and app/services/sso.py) keeps the
    # comparison valid against either backend — the stored instant is
    # UTC regardless of the label.
    assert scheduled.last_run_at == now.replace(tzinfo=scheduled.last_run_at.tzinfo)
    assert scheduled.last_error is None
    assert scheduled.next_run_at == (now + dt.timedelta(days=1)).replace(tzinfo=scheduled.next_run_at.tzinfo)

    reports_result = await db_session.execute(select(Report).where(Report.dataset_table_id == table_id))
    assert len(list(reports_result.scalars().all())) == 1


async def test_run_due_scheduled_reports_is_idempotent_when_not_due(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    token = await _register_and_login(client, "owner5@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "monthly"},
        headers=_auth(token),
    )

    # next_run_at was set to ~1 month out on creation — nothing should
    # fire yet.
    generated = await run_due_scheduled_reports(db_session, test_storage)
    assert generated == []


async def test_delete_scheduled_report(client: AsyncClient) -> None:
    token = await _register_and_login(client, "owner6@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/scheduled-reports/{scheduled_id}", headers=_auth(token))
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/workspaces/{workspace_id}/scheduled-reports", headers=_auth(token))
    assert list_resp.json() == []


async def test_outsider_cannot_create_or_list_scheduled_reports(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner7@example.com")
    outsider_token = await _register_and_login(client, "outsider7@example.com")
    workspace_id, table_id = await _setup_table(client, owner_token)

    denied_create = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(outsider_token),
    )
    assert denied_create.status_code == 403

    denied_list = await client.get(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports", headers=_auth(outsider_token)
    )
    assert denied_list.status_code == 403


class _FakeEmailSender:
    """A fake EmailSender, same role as _ScriptedClient for the AI planner
    tests — records what it was asked to send instead of touching a real
    SMTP server."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise RuntimeError("SMTP connection refused (simulated)")
        self.sent.append(message)


async def _make_due(db_session: AsyncSession, scheduled_id: str) -> None:
    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    scheduled.next_run_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    await db_session.commit()


async def test_run_due_scheduled_reports_emails_the_creator_with_pdf_attached(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    token = await _register_and_login(client, "owner8@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]
    await _make_due(db_session, scheduled_id)

    sender = _FakeEmailSender()
    now = dt.datetime.now(dt.timezone.utc)
    generated = await run_due_scheduled_reports(db_session, test_storage, now=now, email_sender=sender)

    assert len(generated) == 1
    assert len(sender.sent) == 1
    message = sender.sent[0]
    assert message.to == "owner8@example.com"
    assert len(message.attachments) == 1
    assert message.attachments[0].content_type == "application/pdf"
    assert message.attachments[0].content.startswith(b"%PDF-")

    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    assert scheduled.last_email_sent_at == now.replace(tzinfo=scheduled.last_email_sent_at.tzinfo)
    assert scheduled.last_email_error is None


async def test_email_send_failure_does_not_undo_report_generation(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    token = await _register_and_login(client, "owner9@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]
    await _make_due(db_session, scheduled_id)

    sender = _FakeEmailSender(fail=True)
    generated = await run_due_scheduled_reports(db_session, test_storage, email_sender=sender)

    # The report itself must still be generated and stored — delivery
    # failing must not roll back generation.
    assert len(generated) == 1
    assert generated[0].file_size_bytes > 0

    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    assert scheduled.last_error is None  # generation succeeded — this field is reserved for that
    assert scheduled.last_email_error == "SMTP connection refused (simulated)"
    assert scheduled.last_email_sent_at is None
    assert scheduled.last_run_at is not None


async def test_run_due_scheduled_reports_without_email_sender_still_generates(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    """Regression check: omitting email_sender (the default) must behave
    exactly as before this feature existed — no email attempted, no
    last_email_* fields touched."""
    token = await _register_and_login(client, "owner10@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]
    await _make_due(db_session, scheduled_id)

    generated = await run_due_scheduled_reports(db_session, test_storage)
    assert len(generated) == 1

    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    assert scheduled.last_email_sent_at is None
    assert scheduled.last_email_error is None


RESIDENTIAL_CSV = (
    b"Property,Tenant Name,Rent PCM,Occupancy Status,Tenancy End Date,Rent Arrears,Maintenance Cost\n"
    b"Flat 1,Jane Doe,950,Occupied,2027-01-15,0,120\n"
    b"Flat 2,Bob Smith,850,Occupied,2026-03-20,150,0\n"
)

SOCIAL_HOUSING_CSV = (
    b"Property,Stock Type,EPC Rating,Last Inspection Date,Repair Cost,Planned Investment,Void Status\n"
    b"Flat 1,House,C,2023-01-01,500,2000,Occupied\n"
    b"Flat 2,Flat,B,2026-09-01,100,0,Occupied\n"
)

BUSINESS_FINANCE_CSV = (
    b"Date,Revenue,Expenses,Category,Customer\n"
    b"2026-01-15,10000,4000,Consulting,Acme Ltd\n"
    b"2026-02-10,12000,4500,Consulting,Acme Ltd\n"
)


async def _setup_industry_table(client: AsyncClient, token: str, industry: str, csv_bytes: bytes) -> tuple[str, str]:
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": f"{industry} Scheduled Test", "industry": industry}, headers=_auth(token)
    )
    workspace_id = ws_resp.json()["id"]
    files = {"file": ("data.csv", csv_bytes, "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        data={"name": "Data"},
        files=files,
        headers=_auth(token),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    dataset_id = upload_resp.json()["dataset_id"]
    detail = (await client.get(f"/api/v1/datasets/{dataset_id}", headers=_auth(token))).json()
    version = detail["versions"][-1]
    assert version["status"] == "ready", version
    return workspace_id, version["tables"][0]["id"]


async def test_scheduler_generates_each_industry_report_type(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    cases = [
        ("residential_property", RESIDENTIAL_CSV, "residential_property_portfolio", "resched"),
        ("residential_property", RESIDENTIAL_CSV, "residential_repairs_maintenance", "rmsched"),
        ("social_housing", SOCIAL_HOUSING_CSV, "social_housing_asset", "shsched"),
        ("social_housing", SOCIAL_HOUSING_CSV, "social_housing_compliance_exceptions", "shcesched"),
        ("business_finance", BUSINESS_FINANCE_CSV, "business_performance", "bfsched"),
    ]
    for industry, csv_bytes, report_type, email_prefix in cases:
        token = await _register_and_login(client, f"{email_prefix}@example.com")
        workspace_id, table_id = await _setup_industry_table(client, token, industry, csv_bytes)

        create_resp = await client.post(
            f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
            json={"dataset_table_id": table_id, "report_type": report_type, "frequency": "daily"},
            headers=_auth(token),
        )
        assert create_resp.status_code == 201, create_resp.text
        scheduled_id = create_resp.json()["id"]
        await _make_due(db_session, scheduled_id)

        generated = await run_due_scheduled_reports(db_session, test_storage)
        assert len(generated) == 1, f"{report_type} did not generate"
        assert generated[0].report_type == report_type
        assert generated[0].file_size_bytes > 0

        scheduled = await db_session.get(ScheduledReport, scheduled_id)
        assert scheduled.last_error is None, f"{report_type} failed: {scheduled.last_error}"


async def test_run_due_scheduled_reports_skips_when_another_replica_holds_the_lock(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    """Simulates two API replicas' APScheduler ticks firing at the same
    moment: one has already acquired the scheduler lock (standing in for
    the other replica's in-flight tick) when this one calls
    run_due_scheduled_reports. It must skip entirely — generating
    nothing and leaving the due schedule completely untouched — rather
    than double-process the same due report."""
    token = await _register_and_login(client, "lockowner1@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]
    await _make_due(db_session, scheduled_id)

    now = dt.datetime.now(dt.timezone.utc)
    other_replica_holder = await try_acquire_lock(db_session, SCHEDULER_LOCK_ID, now=now)
    assert other_replica_holder is not None

    generated = await run_due_scheduled_reports(db_session, test_storage, now=now)
    assert generated == []

    scheduled = await db_session.get(ScheduledReport, scheduled_id)
    assert scheduled.last_run_at is None  # completely untouched, not just "no reports returned"
    # still due — will be picked up next tick (tzinfo matched to the
    # DB's own round-trip behavior, same idiom as the other assertions
    # in this file — see the comment above the first one)
    assert scheduled.next_run_at <= now.replace(tzinfo=scheduled.next_run_at.tzinfo)

    await release_lock(db_session, SCHEDULER_LOCK_ID, other_replica_holder)


async def test_run_due_scheduled_reports_releases_the_lock_for_the_next_tick(
    client: AsyncClient, db_session: AsyncSession, test_storage: ObjectStorage
) -> None:
    token = await _register_and_login(client, "lockowner2@example.com")
    workspace_id, table_id = await _setup_table(client, token)

    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/scheduled-reports",
        json={"dataset_table_id": table_id, "report_type": "data_quality", "frequency": "daily"},
        headers=_auth(token),
    )
    scheduled_id = create_resp.json()["id"]
    await _make_due(db_session, scheduled_id)

    generated = await run_due_scheduled_reports(db_session, test_storage)
    assert len(generated) == 1

    # If run_due_scheduled_reports hadn't released the lock afterward,
    # this would come back None.
    holder = await try_acquire_lock(db_session, SCHEDULER_LOCK_ID, lease_seconds=60)
    assert holder is not None
    await release_lock(db_session, SCHEDULER_LOCK_ID, holder)
