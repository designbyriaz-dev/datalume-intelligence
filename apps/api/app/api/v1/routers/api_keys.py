from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ApiKeyCreateRequest, ApiKeyCreatedOut, ApiKeyOut
from app.services.api_keys import generate_api_key
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedOut:
    generated = generate_api_key()
    api_key = ApiKey(
        user_id=current_user.id,
        name=payload.name,
        key_prefix=generated.key_prefix,
        key_hash=generated.key_hash,
    )
    db.add(api_key)
    await db.flush()
    await record_audit_event(
        db,
        event_type="api_key.created",
        actor_user_id=current_user.id,
        metadata={"api_key_id": api_key.id, "name": api_key.name},
    )
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreatedOut(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        raw_key=generated.raw_key,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    api_key = await db.get(ApiKey, api_key_id)
    if api_key is None or api_key.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")

    api_key.is_active = False
    await record_audit_event(
        db,
        event_type="api_key.revoked",
        actor_user_id=current_user.id,
        metadata={"api_key_id": api_key.id, "name": api_key.name},
    )
    await db.commit()
