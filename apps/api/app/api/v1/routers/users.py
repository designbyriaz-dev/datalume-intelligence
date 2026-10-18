from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_object_storage
from app.core.security import verify_password
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogOut
from app.schemas.auth import AccountDeletionRequest
from app.schemas.user import UserOut
from app.services.account_deletion import delete_own_account
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/me/audit-log", response_model=list[AuditLogOut])
async def read_my_audit_log(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """A user's own recent account activity (logins, registration, API
    key changes) — personal-account visibility into the same audit trail
    org managers can export for their organization below."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.actor_user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    return list(result.scalars().all())


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    payload: AccountDeletionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> None:
    """Irreversible. Requires re-entering the account password — the
    same re-confirmation MFA disable uses — since this is the single
    most destructive action an account can take on itself. Deletes
    every personally-owned workspace (and its data, same as
    DELETE /workspaces/{id}), best-effort cancels any live Stripe
    subscription, and deletes the account itself. Organizations the
    user belongs to, and anything they created inside a shared
    organization workspace, are left in place — see
    app/services/account_deletion.py."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")

    await delete_own_account(db, storage, current_user)
