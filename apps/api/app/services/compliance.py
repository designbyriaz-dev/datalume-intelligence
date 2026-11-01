"""Evaluates a workspace's ComplianceRule rows against a property's
Document rows. See app/models/compliance.py's module docstring for why
this is a configurable checklist, not a legal-compliance determination —
the status vocabulary below is the brief's own, chosen specifically to
avoid a blunt pass/fail the account holder could mistake for legal
advice:

  passes                 a qualifying document is on file and, if the
                          rule requires it, not expired (and not within
                          its warning window either)
  potential_issue        a qualifying document is on file but its
                          expiry falls within the rule's warning window
                          — not yet expired, worth renewing soon
  missing_information     no document of the required type is on file
                          at all — this app simply doesn't know, it is
                          not asserting the property lacks one in
                          reality
  action_may_be_overdue  a qualifying document is on file but its
                          expiry date has already passed
  requires_human_review  a qualifying document is on file but the rule
                          needs expiry information the document doesn't
                          have — a person needs to look at it, the
                          engine can't
  unable_to_determine    the rule's check_type isn't one this engine
                          knows how to evaluate (defensive fallback —
                          never silently reported as "passes")

Deterministic and computed fresh on every call, no AI involved — same
"pure function over already-loaded rows" shape as
app/services/property_kpis.py and app/services/inventory_compare.py.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass

from app.models.compliance import ComplianceCheckType, ComplianceRule
from app.models.document import Document


class ComplianceStatus(str, enum.Enum):
    PASSES = "passes"
    POTENTIAL_ISSUE = "potential_issue"
    MISSING_INFORMATION = "missing_information"
    ACTION_MAY_BE_OVERDUE = "action_may_be_overdue"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    UNABLE_TO_DETERMINE = "unable_to_determine"


@dataclass
class ComplianceCheckResult:
    rule_id: str
    rule_name: str
    status: ComplianceStatus
    detail: str
    matched_document_id: str | None = None


def _as_str(value: object) -> str:
    """`DocumentType`/`ComplianceCheckType` are `(str, enum.Enum)` mixins
    — real instances of `str` with the right content, but on this
    Python version an f-string still calls Enum's own `__format__`
    (inherited, not overridden by the mixin) and renders
    "DocumentType.GAS_SAFETY_CERTIFICATE" instead of the plain value.
    Confirmed empirically, not assumed — caught via a real live check
    showing that exact text in a compliance-check detail message.
    `.value` sidesteps `__format__` entirely."""
    return value.value if isinstance(value, enum.Enum) else str(value)


def _evaluate_document_required(rule: ComplianceRule, documents: list[Document], today: dt.date) -> ComplianceCheckResult:
    matching = [d for d in documents if d.document_type == rule.document_type]
    doc_type = _as_str(rule.document_type)

    if not matching:
        return ComplianceCheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            status=ComplianceStatus.MISSING_INFORMATION,
            detail=f"No {doc_type} document is on file for this property.",
        )

    if not rule.requires_non_expired:
        return ComplianceCheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            status=ComplianceStatus.PASSES,
            detail=f"A {doc_type} document is on file.",
            matched_document_id=matching[0].id,
        )

    with_expiry = [d for d in matching if d.expiry_date is not None]
    if not with_expiry:
        return ComplianceCheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            status=ComplianceStatus.REQUIRES_HUMAN_REVIEW,
            detail=(
                f"A {doc_type} document is on file but has no expiry date recorded, "
                "so this can't be checked automatically."
            ),
            matched_document_id=matching[0].id,
        )

    # The document with the latest expiry is the most relevant one —
    # an older superseded certificate shouldn't mask a valid new one.
    best = max(with_expiry, key=lambda d: d.expiry_date)

    if best.expiry_date < today:
        return ComplianceCheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            status=ComplianceStatus.ACTION_MAY_BE_OVERDUE,
            detail=f"The {doc_type} on file expired on {best.expiry_date.isoformat()}.",
            matched_document_id=best.id,
        )

    days_to_expiry = (best.expiry_date - today).days
    if days_to_expiry <= rule.warning_window_days:
        return ComplianceCheckResult(
            rule_id=rule.id,
            rule_name=rule.name,
            status=ComplianceStatus.POTENTIAL_ISSUE,
            detail=f"The {doc_type} on file expires on {best.expiry_date.isoformat()} (in {days_to_expiry} days).",
            matched_document_id=best.id,
        )

    return ComplianceCheckResult(
        rule_id=rule.id,
        rule_name=rule.name,
        status=ComplianceStatus.PASSES,
        detail=f"The {doc_type} on file is valid until {best.expiry_date.isoformat()}.",
        matched_document_id=best.id,
    )


def evaluate_compliance(
    rules: list[ComplianceRule], documents: list[Document], *, today: dt.date | None = None
) -> list[ComplianceCheckResult]:
    today = today or dt.date.today()
    results: list[ComplianceCheckResult] = []
    for rule in rules:
        if not rule.is_active:
            continue
        if rule.check_type == ComplianceCheckType.DOCUMENT_REQUIRED.value:
            results.append(_evaluate_document_required(rule, documents, today))
        else:
            results.append(
                ComplianceCheckResult(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    status=ComplianceStatus.UNABLE_TO_DETERMINE,
                    detail=f"This engine doesn't know how to evaluate check type '{_as_str(rule.check_type)}'.",
                )
            )
    return results
