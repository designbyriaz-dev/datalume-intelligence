from pydantic import BaseModel, ConfigDict, Field

from app.models.compliance import ComplianceCheckType
from app.models.document import DocumentType
from app.services.compliance import ComplianceStatus


class ComplianceRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    check_type: ComplianceCheckType = ComplianceCheckType.DOCUMENT_REQUIRED
    document_type: DocumentType
    requires_non_expired: bool = True
    warning_window_days: int = Field(default=30, ge=0, le=365)
    is_active: bool = True


class ComplianceRuleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    document_type: DocumentType
    requires_non_expired: bool
    warning_window_days: int = Field(ge=0, le=365)
    is_active: bool


class ComplianceRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    check_type: str
    document_type: str | None
    requires_non_expired: bool
    warning_window_days: int
    is_active: bool
    created_by_user_id: str | None


class ComplianceCheckResultOut(BaseModel):
    rule_id: str
    rule_name: str
    status: ComplianceStatus
    detail: str
    matched_document_id: str | None


class PropertyComplianceOut(BaseModel):
    property_id: str
    checks: list[ComplianceCheckResultOut]
