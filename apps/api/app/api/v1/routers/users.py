from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogOut
from app.schemas.user import UserOut

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
