import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.api.resolvers import get_property_chain_or_404, get_tenancy_chain_or_404
from app.core.config import get_settings
from app.db.session import get_db
from app.models.document import Document, DocumentType
from app.models.user import User
from app.schemas.document import DocumentOut
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.document_validation import DocumentValidationError, validate_document_upload
from app.services.malware_scanning import MalwareDetectedError, MalwareScanningUnavailableError, get_malware_scanner
from app.services.storage import ObjectStorage, StorageError

router = APIRouter(tags=["documents"])


async def _get_document_or_404(db: AsyncSession, document_id: str) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.post(
    "/properties/{property_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    property_id: str,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: DocumentType = Form(default=DocumentType.OTHER),
    tenancy_id: str | None = Form(default=None),
    expiry_date: date | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Document:
    property_, workspace = await get_property_chain_or_404(db, property_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    if tenancy_id is not None:
        _tenancy, tenancy_property, _workspace = await get_tenancy_chain_or_404(db, tenancy_id)
        if tenancy_property.id != property_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenancy_id does not belong to this property")

    content = await file.read()
    settings = get_settings()
    try:
        validated = validate_document_upload(file.filename or "upload", content, settings.max_upload_size_bytes)
    except DocumentValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    scanner = get_malware_scanner()
    if scanner is not None:
        try:
            scanner.scan(validated.content)
        except MalwareDetectedError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        except MalwareScanningUnavailableError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    document_id = str(uuid.uuid4())
    filename = file.filename or "upload"
    storage_key = f"workspaces/{workspace.id}/properties/{property_id}/documents/{document_id}/{filename}"
    storage.write(storage_key, content)

    document = Document(
        id=document_id,
        property_id=property_id,
        tenancy_id=tenancy_id,
        document_type=document_type,
        title=title,
        filename=filename,
        storage_key=storage_key,
        content_type=validated.content_type,
        file_size_bytes=len(content),
        expiry_date=expiry_date,
        uploaded_by_user_id=current_user.id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


@router.get("/properties/{property_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    property_id: str,
    tenancy_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    property_, workspace = await get_property_chain_or_404(db, property_id)
    await require_workspace_access(db, current_user.id, workspace)

    query = select(Document).where(Document.property_id == property_id)
    if tenancy_id is not None:
        query = query.where(Document.tenancy_id == tenancy_id)
    result = await db.execute(query.order_by(Document.created_at.desc()))
    return list(result.scalars().all())


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await _get_document_or_404(db, document_id)
    _property, workspace = await get_property_chain_or_404(db, document.property_id)
    await require_workspace_access(db, current_user.id, workspace)
    return document


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    document = await _get_document_or_404(db, document_id)
    _property, workspace = await get_property_chain_or_404(db, document.property_id)
    await require_workspace_access(db, current_user.id, workspace)

    try:
        content = storage.read(document.storage_key)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not found in storage") from exc

    return Response(
        content=content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> None:
    document = await _get_document_or_404(db, document_id)
    _property, workspace = await get_property_chain_or_404(db, document.property_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    storage.delete(document.storage_key)
    await db.delete(document)
    await db.commit()
