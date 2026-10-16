import datetime as dt
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.api.resolvers import get_table_chain_or_404
from app.core.industry_packs import INDUSTRY_PACKS, get_industry_pack
from app.db.session import get_db
from app.models.analysis import AnalysisRun
from app.models.user import User
from app.schemas.industry import (
    ConfirmFieldMappingRequest,
    FieldMappingOut,
    IndustryKPIResponse,
    IndustryPackOut,
)
from app.schemas.scenario import KPIDeltaOut, ScenarioRequest, ScenarioResponse
from app.services import billing
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.datasets import get_dataset_table_dataframe
from app.services.industry_kpis import compute_kpis
from app.services.industry_matching import get_effective_field_mapping, missing_required_fields
from app.services.scenario import ScenarioAdjustment, ScenarioError, apply_adjustments
from app.services.storage import ObjectStorage

router = APIRouter(tags=["industry"])


@router.get("/industry-packs", response_model=list[IndustryPackOut])
async def list_industry_packs(current_user: User = Depends(get_current_user)) -> list[dict]:
    return [_pack_to_dict(p) for p in INDUSTRY_PACKS.values()]


@router.get("/industry-packs/{industry_id}", response_model=IndustryPackOut)
async def get_industry_pack_detail(
    industry_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    pack = get_industry_pack(industry_id)
    if pack is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No industry pack for '{industry_id}'. Available: {', '.join(INDUSTRY_PACKS)}.",
        )
    return _pack_to_dict(pack)


def _pack_to_dict(pack) -> dict:
    return {
        "industry_id": pack.industry_id,
        "name": pack.name,
        "column_aliases": [
            {"canonical_field": ca.canonical_field, "description": ca.description, "required_for_pack": ca.required_for_pack}
            for ca in pack.column_aliases
        ],
        "kpis": [
            {"kpi_id": k.kpi_id, "name": k.name, "description": k.description, "format": k.format} for k in pack.kpis
        ],
        "suggested_questions": list(pack.suggested_questions),
        "terminology": pack.terminology,
        "report_templates": list(pack.report_templates),
        "compliance_caveat": pack.compliance_caveat,
    }


@router.get("/dataset-tables/{table_id}/field-mapping", response_model=FieldMappingOut)
async def get_field_mapping(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> FieldMappingOut:
    """What /industry-kpis, the specialist reports, /scenario, and KPI
    dashboard widgets will actually use to compute against this table —
    the user-confirmed mapping if one has been saved, otherwise the
    automatic alias/token matching's best guess (same "review before
    trusting" pattern as Phase 2's PATCH .../schema for column types)."""
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This workspace's industry ('{workspace.industry}') has no industry pack yet. "
            f"Supported: {', '.join(INDUSTRY_PACKS)}.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)

    return FieldMappingOut(
        industry_id=pack.industry_id,
        pack_name=pack.name,
        fields=[
            {
                "canonical_field": ca.canonical_field,
                "description": ca.description,
                "required_for_pack": ca.required_for_pack,
                "matched_column": mapping.get(ca.canonical_field),
            }
            for ca in pack.column_aliases
        ],
        available_columns=list(df.columns),
        missing_required_fields=missing_required_fields(pack, mapping),
        is_confirmed=table.confirmed_field_mapping is not None,
    )


@router.patch("/dataset-tables/{table_id}/field-mapping", response_model=FieldMappingOut)
async def confirm_field_mapping(
    table_id: str,
    payload: ConfirmFieldMappingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> FieldMappingOut:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This workspace's industry ('{workspace.industry}') has no industry pack yet. "
            f"Supported: {', '.join(INDUSTRY_PACKS)}.",
        )

    known_fields = {ca.canonical_field for ca in pack.column_aliases}
    unknown_fields = set(payload.mapping) - known_fields
    if unknown_fields:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown field(s) for pack '{pack.industry_id}': {', '.join(sorted(unknown_fields))}. "
            f"Valid: {', '.join(sorted(known_fields))}.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    available = set(df.columns)
    unknown_columns = {col for col in payload.mapping.values() if col is not None and col not in available}
    if unknown_columns:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown column(s): {', '.join(sorted(unknown_columns))}. Available: {', '.join(df.columns)}.",
        )

    # Every canonical field the pack defines ends up with an explicit
    # entry (null if the caller didn't map it) — a confirmed mapping
    # means "this is complete, stop guessing," not "merge these few
    # overrides into the automatic guess."
    full_mapping = {ca.canonical_field: payload.mapping.get(ca.canonical_field) for ca in pack.column_aliases}
    table.confirmed_field_mapping = full_mapping
    await db.commit()

    return FieldMappingOut(
        industry_id=pack.industry_id,
        pack_name=pack.name,
        fields=[
            {
                "canonical_field": ca.canonical_field,
                "description": ca.description,
                "required_for_pack": ca.required_for_pack,
                "matched_column": full_mapping.get(ca.canonical_field),
            }
            for ca in pack.column_aliases
        ],
        available_columns=list(df.columns),
        missing_required_fields=missing_required_fields(pack, full_mapping),
        is_confirmed=True,
    )


@router.post("/dataset-tables/{table_id}/industry-kpis", response_model=IndustryKPIResponse)
async def compute_industry_kpis(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> IndustryKPIResponse:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This workspace's industry ('{workspace.industry}') has no industry pack yet. "
            f"Supported: {', '.join(INDUSTRY_PACKS)}.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)
    missing = missing_required_fields(pack, mapping)

    kpi_results = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    subscription = await billing.get_subscription_for_workspace(db, workspace)
    try:
        await billing.check_and_increment_analysis_quota(db, subscription)
    except billing.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc

    result_payload = {
        "industry_id": pack.industry_id,
        "pack_name": pack.name,
        "field_mapping": mapping,
        "missing_required_fields": missing,
        "kpis": [asdict(r) for r in kpi_results],
        "compliance_caveat": pack.compliance_caveat,
    }

    run = AnalysisRun(
        dataset_table_id=table.id,
        operation_type=f"industry_kpis:{pack.industry_id}",
        parameters={"industry_id": pack.industry_id},
        result=result_payload,
        created_by_user_id=current_user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return IndustryKPIResponse(
        analysis_run_id=run.id,
        industry_id=pack.industry_id,
        pack_name=pack.name,
        field_mapping=mapping,
        missing_required_fields=missing,
        kpis=[asdict(r) for r in kpi_results],
        compliance_caveat=pack.compliance_caveat,
    )


def _kpi_deltas(baseline: list, scenario: list) -> list[dict]:
    baseline_by_id = {r.kpi_id: r for r in baseline}
    deltas = []
    for scenario_result in scenario:
        base = baseline_by_id.get(scenario_result.kpi_id)
        delta = None
        pct_change = None
        if base is not None and base.value is not None and scenario_result.value is not None:
            delta = round(scenario_result.value - base.value, 4)
            if base.value != 0:
                pct_change = round(delta / abs(base.value) * 100, 2)
        deltas.append(
            {
                "kpi_id": scenario_result.kpi_id,
                "name": scenario_result.name,
                "format": scenario_result.format,
                "baseline_value": base.value if base else None,
                "scenario_value": scenario_result.value,
                "delta": delta,
                "pct_change": pct_change,
            }
        )
    return deltas


@router.post("/dataset-tables/{table_id}/scenario", response_model=ScenarioResponse)
async def run_scenario(
    table_id: str,
    payload: ScenarioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> ScenarioResponse:
    """'What if rent increases 5%?' — applies adjustments to a copy of the
    data and recomputes the same KPI engine used by /industry-kpis, so
    baseline and scenario numbers are produced by identical code."""
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)

    pack = get_industry_pack(workspace.industry)
    if pack is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This workspace's industry ('{workspace.industry}') has no industry pack, so there are no "
            "KPIs to model a scenario against.",
        )

    df = await get_dataset_table_dataframe(storage, table)
    mapping = get_effective_field_mapping(table, pack, df.columns)

    baseline_kpis = compute_kpis(df, pack, mapping, as_of=dt.date.today())

    adjustments = [ScenarioAdjustment(a.column, a.adjustment_type, a.value) for a in payload.adjustments]
    try:
        adjusted_df = apply_adjustments(df, adjustments)
    except ScenarioError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    scenario_kpis = compute_kpis(adjusted_df, pack, mapping, as_of=dt.date.today())

    # Quota is only consumed once the scenario actually computed
    # successfully — same "don't charge for a failed request" pattern as
    # /analyze and /industry-kpis. Must commit here: check_and_increment
    # only flushes, it doesn't commit (the caller decides the transaction
    # boundary) — forgetting this commit was a real bug caught by the
    # quota-exhaustion test for this endpoint.
    subscription = await billing.get_subscription_for_workspace(db, workspace)
    try:
        await billing.check_and_increment_analysis_quota(db, subscription)
    except billing.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    await db.commit()

    return ScenarioResponse(
        industry_id=pack.industry_id,
        adjustments_applied=payload.adjustments,
        baseline_kpis=[asdict(r) for r in baseline_kpis],
        scenario_kpis=[asdict(r) for r in scenario_kpis],
        kpi_deltas=[KPIDeltaOut(**d) for d in _kpi_deltas(baseline_kpis, scenario_kpis)],
    )
