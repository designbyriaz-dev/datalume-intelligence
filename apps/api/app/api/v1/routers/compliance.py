from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.resolvers import get_property_chain_or_404, get_workspace_or_404
from app.db.session import get_db
from app.models.compliance import ComplianceRule
from app.models.document import Document
from app.models.user import User
from app.schemas.compliance import (
    ComplianceCheckResultOut,
    ComplianceRuleCreate,
    ComplianceRuleOut,
    ComplianceRuleUpdate,
    PropertyComplianceOut,
)
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.compliance import evaluate_compliance

router = APIRouter(tags=["compliance"])


async def _get_rule_or_404(db: AsyncSession, rule_id: str) -> ComplianceRule:
    rule = await db.get(ComplianceRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compliance rule not found")
    return rule


@router.post(
    "/workspaces/{workspace_id}/compliance-rules",
    response_model=ComplianceRuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_compliance_rule(
    workspace_id: str,
    payload: ComplianceRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRule:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    rule = ComplianceRule(
        workspace_id=workspace_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/workspaces/{workspace_id}/compliance-rules", response_model=list[ComplianceRuleOut])
async def list_compliance_rules(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ComplianceRule]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.workspace_id == workspace_id).order_by(ComplianceRule.name)
    )
    return list(result.scalars().all())


@router.patch("/compliance-rules/{rule_id}", response_model=ComplianceRuleOut)
async def update_compliance_rule(
    rule_id: str,
    payload: ComplianceRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRule:
    rule = await _get_rule_or_404(db, rule_id)
    workspace = await get_workspace_or_404(db, rule.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/compliance-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compliance_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await _get_rule_or_404(db, rule_id)
    workspace = await get_workspace_or_404(db, rule.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(rule)
    await db.commit()


@router.get("/properties/{property_id}/compliance", response_model=PropertyComplianceOut)
async def get_property_compliance(
    property_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PropertyComplianceOut:
    property_, workspace = await get_property_chain_or_404(db, property_id)
    await require_workspace_access(db, current_user.id, workspace)

    rules_result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.workspace_id == workspace.id, ComplianceRule.is_active.is_(True))
    )
    rules = list(rules_result.scalars().all())

    documents_result = await db.execute(select(Document).where(Document.property_id == property_id))
    documents = list(documents_result.scalars().all())

    checks = evaluate_compliance(rules, documents)
    return PropertyComplianceOut(
        property_id=property_id,
        checks=[
            ComplianceCheckResultOut(
                rule_id=c.rule_id,
                rule_name=c.rule_name,
                status=c.status,
                detail=c.detail,
                matched_document_id=c.matched_document_id,
            )
            for c in checks
        ],
    )
