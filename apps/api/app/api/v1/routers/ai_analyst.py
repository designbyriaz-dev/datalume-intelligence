from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_llm_client_dep, get_object_storage
from app.api.resolvers import get_dataset_or_404, get_table_chain_or_404, get_workspace_or_404
from app.core.industry_packs import get_industry_pack
from app.db.session import get_db
from app.models.ai import AIConversation, AIMessage, MessageRole
from app.models.dataset import Dataset, DatasetTable
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.ai import AIConversationOut, AskRequest, AskResponse
from app.services.ai.llm_client import LLMClient
from app.services.ai.planner import run_conversation_turn
from app.services.authz import require_workspace_access
from app.services.datasets import get_dataset_table_dataframe
from app.services.industry_matching import get_effective_field_mapping
from app.services.storage import ObjectStorage

router = APIRouter(tags=["ai-analyst"])

_ROLE_TO_API = {MessageRole.USER: "user", MessageRole.ASSISTANT: "assistant"}


async def _require_askable_table(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[DatasetTable, Dataset, Workspace]:
    """Resolves the table and checks workspace access. Declared as its
    own dependency — and listed BEFORE get_llm_client_dep in ask()'s
    signature below — so that an unauthorized caller gets 403, not a 503
    that leaks "the server has no LLM key configured" before authorization
    has even been checked. FastAPI resolves Depends() params in signature
    order and stops at the first one that raises."""
    table, _version, dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)
    return table, dataset, workspace


def _history_to_anthropic_messages(messages: list[AIMessage]) -> list[dict]:
    """Replays prior turns with full tool_use/tool_result block fidelity
    when available, via each assistant message's `replay_messages` (the
    exact message sequence that turn produced — see
    app/services/ai/planner.py's PlannerResult.message_delta) — rather
    than flattening every turn down to plain text. A model can see it
    already called a tool and got a specific result earlier in the
    conversation, instead of only seeing the prose answer that followed.

    Falls back to a plain {role, content} pair for any turn persisted
    before `replay_messages` existed (or in the edge case where it's
    unexpectedly absent) — degrading to the old flattened behavior
    rather than breaking.

    Assumes router.ask() always persists exactly one USER row then one
    ASSISTANT row per turn, in that order — true for every conversation
    this function is called on."""
    result: list[dict] = []
    i = 0
    while i < len(messages):
        user_msg = messages[i]
        assistant_msg = messages[i + 1] if i + 1 < len(messages) else None

        if assistant_msg is not None and assistant_msg.replay_messages:
            result.extend(assistant_msg.replay_messages)
        else:
            result.append({"role": _ROLE_TO_API[MessageRole(user_msg.role)], "content": user_msg.content})
            if assistant_msg is not None:
                result.append({"role": _ROLE_TO_API[MessageRole(assistant_msg.role)], "content": assistant_msg.content})
        i += 2
    return result


@router.post("/dataset-tables/{table_id}/ask", response_model=AskResponse)
async def ask(
    table_id: str,
    payload: AskRequest,
    table_dataset_workspace: tuple[DatasetTable, Dataset, Workspace] = Depends(_require_askable_table),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    llm_client: LLMClient = Depends(get_llm_client_dep),
) -> AskResponse:
    table, dataset, workspace = table_dataset_workspace

    if payload.conversation_id is not None:
        conversation = await db.get(AIConversation, payload.conversation_id)
        if conversation is None or conversation.dataset_id != dataset.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        history_result = await db.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id).order_by(AIMessage.created_at)
        )
        history_messages = list(history_result.scalars().all())
    else:
        conversation = AIConversation(
            workspace_id=workspace.id,
            dataset_id=dataset.id,
            created_by_user_id=current_user.id,
            title=payload.question[:100],
        )
        db.add(conversation)
        await db.flush()
        history_messages = []

    db.add(AIMessage(conversation_id=conversation.id, role=MessageRole.USER, content=payload.question))

    df = await get_dataset_table_dataframe(storage, table)

    # Gives the planner access to this workspace's own precise KPI
    # engine (see app/services/ai/planner.py's compute_industry_kpis
    # tool) when one exists — None for a workspace with no industry
    # pack (general/other), same as every other industry-gated feature
    # in this app; the AI analyst still works fine without it, just
    # without that one extra tool.
    industry_pack = get_industry_pack(workspace.industry)
    field_mapping = get_effective_field_mapping(table, industry_pack, df.columns) if industry_pack else None

    result = await run_conversation_turn(
        llm_client,
        df=df,
        table_profile=table.profile,
        history=_history_to_anthropic_messages(history_messages),
        question=payload.question,
        industry_pack=industry_pack,
        field_mapping=field_mapping,
        kpi_window_months=workspace.kpi_window_months,
    )

    tool_calls_json = [
        {"name": tc.name, "input": tc.input, "result": tc.result, "error": tc.error} for tc in result.tool_calls
    ]
    db.add(
        AIMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=result.answer,
            tool_calls=tool_calls_json or None,
            replay_messages=result.message_delta or None,
        )
    )
    await db.commit()

    return AskResponse(
        conversation_id=conversation.id,
        answer=result.answer,
        tool_calls=tool_calls_json,
        hit_iteration_limit=result.hit_iteration_limit,
    )


@router.get("/ai-conversations/{conversation_id}", response_model=AIConversationOut)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIConversation:
    result = await db.execute(
        select(AIConversation)
        .where(AIConversation.id == conversation_id)
        .options(selectinload(AIConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    workspace = await db.get(Workspace, conversation.workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    await require_workspace_access(db, current_user.id, workspace)
    return conversation


@router.get("/datasets/{dataset_id}/conversations", response_model=list[AIConversationOut])
async def list_conversations(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AIConversation]:
    dataset = await get_dataset_or_404(db, dataset_id)
    workspace = await get_workspace_or_404(db, dataset.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(
        select(AIConversation)
        .where(AIConversation.dataset_id == dataset_id)
        .options(selectinload(AIConversation.messages))
        .order_by(AIConversation.created_at.desc())
    )
    return list(result.scalars().all())
