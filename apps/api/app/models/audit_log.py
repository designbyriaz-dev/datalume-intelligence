from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class AuditLog(UUIDPKMixin, TimestampMixin, Base):
    """A security/governance event trail — the brief's "advanced audit
    exports". This instruments a deliberately chosen, documented subset
    of events (auth, organization membership, API keys, billing plan
    changes — see app/services/audit.py's module docstring for the full
    list and why), not every mutation in the app. Extending coverage
    means adding one `record_audit_event` call at the point of the new
    action, same pattern as the existing ones."""

    __tablename__ = "audit_logs"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
