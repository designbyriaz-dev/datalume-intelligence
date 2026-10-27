from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentType


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    tenancy_id: str | None
    document_type: str
    title: str
    filename: str
    content_type: str
    file_size_bytes: int
    expiry_date: date | None
    uploaded_by_user_id: str | None


__all__ = ["DocumentOut", "DocumentType"]
