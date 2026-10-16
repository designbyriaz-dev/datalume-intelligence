from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import AdminUserOut, PlatformStatsOut
from app.services.admin_stats import compute_platform_stats
from app.services.audit import record_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=PlatformStatsOut)
async def get_platform_stats(
    current_admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate counts only — no per-user PII — so this endpoint isn't
    separately audit-logged the way /admin/users is below."""
    return await compute_platform_stats(db)


@router.get("/users", response_model=list[AdminUserOut])
async def list_all_users(
    current_admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 200,
) -> list[User]:
    """Exposes customer PII (email), so every access is itself an
    audited event — the brief's "customer data access by platform
    administrators must be tightly restricted and audited" is enforced
    structurally here, not just documented."""
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(min(limit, 1000)))
    users = list(result.scalars().all())

    await record_audit_event(
        db,
        event_type="admin.user_data_accessed",
        actor_user_id=current_admin.id,
        metadata={"endpoint": "GET /admin/users", "returned_count": len(users)},
    )
    await db.commit()

    return users
