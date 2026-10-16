"""The AI query planner: a standard agentic tool-calling loop, restricted
to the deterministic tools in app/services/tools.py. This module has real
test coverage (tests/test_ai_planner.py) using a scripted FakeLLMClient —
that verifies the loop itself (tool execution, message threading, the
iteration cap, error handling) is correct. It does NOT verify that a real
Claude model behaves sensibly when driving this loop — that needs a real
LLM_API_KEY, which this environment doesn't have. See llm_client.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from app.services.analytics import AnalyticsError
from app.services.ai.llm_client import LLMClient
from app.services.tools import TOOLS, anthropic_tool_definitions

MAX_TOOL_ITERATIONS = 5

_SYSTEM_PROMPT_TEMPLATE = """You are DataLume Intelligence's AI data analyst, helping a user understand \
one specific dataset. You are talking to a business user, not a data engineer — be clear and direct.

Hard rules, no exceptions:
1. You must NEVER state a number, statistic, trend, correlation, or forecast unless it came from a \
tool call result earlier in this conversation. If you haven't called a tool to get a figure, you \
don't have it — call a tool, or say you can't answer without more information.
2. If a tool call fails or the data doesn't support an analysis (too few rows, wrong column type), \
say so plainly rather than guessing.
3. When you give a forecast, state the caveat the tool returns — never present it as more certain \
than it is.
4. Cite which columns and calculations back each claim you make, briefly.
5. End with 1-2 relevant follow-up questions the user could ask next, when appropriate.

Dataset: "{sheet_name}" ({row_count} rows, {column_count} columns)
Columns:
{column_summary}

Call tools as needed, then give your final answer as plain text.
"""


def _build_system_prompt(table_profile: dict[str, Any]) -> str:
    column_lines = []
    for col in table_profile["columns"]:
        type_note = col["inferred_type"]
        if col["suggested_type"] != col["inferred_type"]:
            type_note += f" (looks like {col['suggested_type']} but stored as text)"
        column_lines.append(f"- {col['name']}: {type_note}, {col['null_ratio']:.0%} missing")

    return _SYSTEM_PROMPT_TEMPLATE.format(
        sheet_name=table_profile["sheet_name"],
        row_count=table_profile["row_count"],
        column_count=table_profile["column_count"],
        column_summary="\n".join(column_lines),
    )


@dataclass
class ToolCallRecord:
    name: str
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None


@dataclass
class PlannerResult:
    answer: str
    tool_calls: list[ToolCallRecord]
    hit_iteration_limit: bool = False
    # The exact sequence of messages this turn added on top of `history`
    # — the user question, then one {assistant, user(tool_result)} pair
    # per tool-calling iteration, ending with a final assistant message.
    # This is what makes multi-turn replay possible (see
    # app/api/v1/routers/ai_analyst.py's _history_to_anthropic_messages):
    # concatenating message_delta across turns reproduces the exact
    # tool_use/tool_result block structure Anthropic's API expects,
    # instead of flattening each turn down to plain text.
    message_delta: list[dict[str, Any]] = field(default_factory=list)


async def run_conversation_turn(
    llm_client: LLMClient,
    *,
    df: pl.DataFrame,
    table_profile: dict[str, Any],
    history: list[dict[str, Any]],
    question: str,
) -> PlannerResult:
    system = _build_system_prompt(table_profile)
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": question}]
    turn_start = len(history)
    tool_defs = anthropic_tool_definitions()
    tool_call_records: list[ToolCallRecord] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await llm_client.complete(system=system, messages=messages, tools=tool_defs)

        if not response.tool_uses:
            # Close out the turn with the final assistant message so the
            # delta is a complete, replayable exchange — without this,
            # a terminal (no-tool-use) turn would leave `messages`
            # ending on the user's question, and the *next* turn's user
            # message would follow it directly: two consecutive
            # user-role messages, which Anthropic's API rejects.
            messages.append({"role": "assistant", "content": response.text or ""})
            return PlannerResult(
                answer=response.text or "",
                tool_calls=tool_call_records,
                message_delta=messages[turn_start:],
            )

        assistant_content: list[dict[str, Any]] = []
        if response.text:
            assistant_content.append({"type": "text", "text": response.text})
        for tu in response.tool_uses:
            assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name, "input": tu.input})
        messages.append({"role": "assistant", "content": assistant_content})

        tool_result_content: list[dict[str, Any]] = []
        for tu in response.tool_uses:
            tool = TOOLS.get(tu.name)
            result: dict[str, Any] | None = None
            error: str | None = None
            if tool is None:
                error = f"Unknown tool: {tu.name}"
            else:
                try:
                    result = tool.execute(df, tu.input)
                except AnalyticsError as exc:
                    error = str(exc)

            tool_call_records.append(ToolCallRecord(name=tu.name, input=tu.input, result=result, error=error))
            tool_result_content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result if error is None else {"error": error}),
                    "is_error": error is not None,
                }
            )
        messages.append({"role": "user", "content": tool_result_content})

    iteration_limit_answer = (
        "I wasn't able to finish this analysis within the allowed number of steps. "
        "Try asking a more specific question."
    )
    # Same reasoning as the terminal case above: `messages` currently ends
    # on a tool_result (user-role) message from the last iteration. Append
    # a closing assistant message so the next turn's user question doesn't
    # follow another user-role message.
    messages.append({"role": "assistant", "content": iteration_limit_answer})
    return PlannerResult(
        answer=iteration_limit_answer,
        tool_calls=tool_call_records,
        hit_iteration_limit=True,
        message_delta=messages[turn_start:],
    )
