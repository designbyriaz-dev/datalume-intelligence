import enum

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class AIConversation(UUIDPKMixin, TimestampMixin, Base):
    """A saved back-and-forth with the AI data analyst, scoped to one
    dataset within a workspace. See app/services/ai/ for the (currently
    unconfigured-by-default) orchestration that populates this."""

    __tablename__ = "ai_conversations"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    # SET NULL (not CASCADE): deleting the user who started a
    # conversation shouldn't delete the conversation itself — see
    # app/services/account_deletion.py.
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at"
    )


class AIMessage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Enum(MessageRole, native_enum=False, length=16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # For assistant messages: which deterministic tools were called to
    # ground this answer, and what they returned. None for user messages.
    # This is the evidence trail behind "evidence-grounded answers" — a
    # client can render exactly which AnalysisRun-equivalent calculations
    # backed a given claim, not just trust the prose.
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # For assistant messages: the exact sequence of raw Anthropic-API-shaped
    # messages this turn produced (the user question, each tool-calling
    # iteration's assistant/tool_result pair, and the final assistant
    # message) — see app/services/ai/planner.py's PlannerResult.message_delta.
    # Used to replay prior turns with full tool_use/tool_result block
    # fidelity in a later turn of the same conversation, instead of
    # flattening history down to plain text (which `content`/`tool_calls`
    # above are for — display and the audit trail, not replay). None for
    # user messages, and for any assistant message persisted before this
    # column existed — _history_to_anthropic_messages falls back to plain
    # text for those.
    replay_messages: Mapped[list | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped["AIConversation"] = relationship(back_populates="messages")
