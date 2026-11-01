import datetime as dt

from app.models.compliance import ComplianceCheckType, ComplianceRule
from app.models.document import Document, DocumentType
from app.services.compliance import ComplianceStatus, evaluate_compliance

TODAY = dt.date(2026, 11, 1)


def _rule(
    document_type: str = DocumentType.GAS_SAFETY_CERTIFICATE.value,
    requires_non_expired: bool = True,
    warning_window_days: int = 30,
    is_active: bool = True,
) -> ComplianceRule:
    return ComplianceRule(
        id="rule-1",
        workspace_id="ws-1",
        name="Gas Safety Certificate",
        check_type=ComplianceCheckType.DOCUMENT_REQUIRED.value,
        document_type=document_type,
        requires_non_expired=requires_non_expired,
        warning_window_days=warning_window_days,
        is_active=is_active,
    )


def _document(document_type: str, expiry_date: dt.date | None, doc_id: str = "doc-1") -> Document:
    return Document(
        id=doc_id,
        property_id="prop-1",
        document_type=document_type,
        title="Cert",
        filename="cert.pdf",
        storage_key="x",
        content_type="application/pdf",
        file_size_bytes=100,
        expiry_date=expiry_date,
    )


def test_passes_when_valid_non_expiring_soon_document_exists() -> None:
    rule = _rule()
    doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY + dt.timedelta(days=200))

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.PASSES


def test_missing_information_when_no_matching_document() -> None:
    rule = _rule()

    results = evaluate_compliance([rule], [], today=TODAY)

    assert results[0].status == ComplianceStatus.MISSING_INFORMATION


def test_action_may_be_overdue_when_expired() -> None:
    rule = _rule()
    doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY - dt.timedelta(days=1))

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.ACTION_MAY_BE_OVERDUE


def test_potential_issue_when_expiring_within_warning_window() -> None:
    rule = _rule(warning_window_days=30)
    doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY + dt.timedelta(days=10))

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.POTENTIAL_ISSUE


def test_requires_human_review_when_expiry_missing_but_required() -> None:
    rule = _rule(requires_non_expired=True)
    doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, None)

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.REQUIRES_HUMAN_REVIEW


def test_passes_when_rule_does_not_require_expiry_check() -> None:
    rule = _rule(requires_non_expired=False)
    doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY - dt.timedelta(days=400))  # expired, but irrelevant

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.PASSES


def test_most_relevant_document_is_the_one_with_latest_expiry() -> None:
    rule = _rule()
    old_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY - dt.timedelta(days=5), doc_id="old")
    new_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE.value, TODAY + dt.timedelta(days=200), doc_id="new")

    results = evaluate_compliance([rule], [old_doc, new_doc], today=TODAY)

    assert results[0].status == ComplianceStatus.PASSES
    assert results[0].matched_document_id == "new"


def test_inactive_rules_are_skipped() -> None:
    rule = _rule(is_active=False)

    results = evaluate_compliance([rule], [], today=TODAY)

    assert results == []


def test_unable_to_determine_for_unknown_check_type() -> None:
    rule = _rule()
    rule.check_type = "some_future_check_type"

    results = evaluate_compliance([rule], [], today=TODAY)

    assert results[0].status == ComplianceStatus.UNABLE_TO_DETERMINE


def test_unrelated_document_type_does_not_satisfy_rule() -> None:
    rule = _rule(document_type=DocumentType.GAS_SAFETY_CERTIFICATE.value)
    doc = _document(DocumentType.EPC.value, TODAY + dt.timedelta(days=200))

    results = evaluate_compliance([rule], [doc], today=TODAY)

    assert results[0].status == ComplianceStatus.MISSING_INFORMATION


def test_detail_message_is_plain_text_when_document_type_is_an_enum_member() -> None:
    """Regression test: the Pydantic schema validates an incoming
    document_type into a real DocumentType enum member (not a plain
    string) before the model is constructed — every other test in this
    file passes document_type=....value explicitly and so never
    exercised that path. A (str, enum.Enum) mixin's f-string formatting
    renders "DocumentType.GAS_SAFETY_CERTIFICATE" instead of the plain
    value on this Python version — caught via real live verification,
    not assumed — so this asserts the detail text never contains the
    enum's class-qualified repr, across every status branch."""
    rule = _rule(document_type=DocumentType.GAS_SAFETY_CERTIFICATE)  # a real enum member, not .value

    missing = evaluate_compliance([rule], [], today=TODAY)
    assert "DocumentType." not in missing[0].detail

    no_expiry_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE, None)
    review = evaluate_compliance([rule], [no_expiry_doc], today=TODAY)
    assert "DocumentType." not in review[0].detail

    expired_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE, TODAY - dt.timedelta(days=1))
    overdue = evaluate_compliance([rule], [expired_doc], today=TODAY)
    assert "DocumentType." not in overdue[0].detail

    soon_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE, TODAY + dt.timedelta(days=5))
    potential = evaluate_compliance([rule], [soon_doc], today=TODAY)
    assert "DocumentType." not in potential[0].detail

    valid_doc = _document(DocumentType.GAS_SAFETY_CERTIFICATE, TODAY + dt.timedelta(days=200))
    passes = evaluate_compliance([rule], [valid_doc], today=TODAY)
    assert "DocumentType." not in passes[0].detail
