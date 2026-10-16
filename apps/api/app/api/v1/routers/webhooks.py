import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_http_client
from app.api.resolvers import get_workspace_or_404
from app.db.session import get_db
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.schemas.webhook import WebhookCreatedOut, WebhookCreateRequest, WebhookOut
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.webhooks import WEBHOOK_EVENT_TYPES, generate_webhook_secret, send_test_delivery

router = APIRouter(tags=["webhooks"])


@router.post(
    "/workspaces/{workspace_id}/webhooks", response_model=WebhookCreatedOut, status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    workspace_id: str,
    payload: WebhookCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WebhookCreatedOut:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    unknown = set(payload.event_types) - WEBHOOK_EVENT_TYPES
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown event_type(s): {', '.join(sorted(unknown))}. Valid: {', '.join(sorted(WEBHOOK_EVENT_TYPES))}",
        )

    secret = generate_webhook_secret()
    subscription = WebhookSubscription(
        workspace_id=workspace_id,
        url=payload.url,
        secret=secret,
        event_types=payload.event_types,
        created_by_user_id=current_user.id,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    return WebhookCreatedOut(
        id=subscription.id,
        url=subscription.url,
        event_types=subscription.event_types,
        secret=secret,
        created_at=subscription.created_at,
    )


@router.get("/workspaces/{workspace_id}/webhooks", response_model=list[WebhookOut])
async def list_webhooks(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookSubscription]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id))
    return list(result.scalars().all())


async def _get_webhook_or_404(db: AsyncSession, webhook_id: str) -> WebhookSubscription:
    webhook = await db.get(WebhookSubscription, webhook_id)
    if webhook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    return webhook


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    webhook = await _get_webhook_or_404(db, webhook_id)
    workspace = await get_workspace_or_404(db, webhook.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await db.delete(webhook)
    await db.commit()


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookOut)
async def test_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> WebhookSubscription:
    webhook = await _get_webhook_or_404(db, webhook_id)
    workspace = await get_workspace_or_404(db, webhook.workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    await send_test_delivery(db, http_client, webhook)
    await db.refresh(webhook)
    return webhook
