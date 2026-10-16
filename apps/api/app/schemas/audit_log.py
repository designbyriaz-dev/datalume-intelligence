from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    actor_user_id: str | None
    organization_id: str | None
    workspace_id: str | None
    event_metadata: dict[str, Any]
    created_at: datetime
