"""The AI query planner: a standard agentic tool-calling loop, restricted
to the deterministic tools in app/services/tools.py, plus one more tool
assembled per-conversation rather than drawn from that static registry:
compute_industry_kpis (see _industry_kpi_tool_definition and its handling
below). The other tools are pure functions of the dataframe alone
(TOOLS' ToolSpec.execute(df, params)); this one needs the workspace's
own IndustryPack and resolved field mapping too, which the generic
registry has no way to carry — so it's built fresh for each turn, by
run_conversation_turn's own caller, and dispatched specially rather than
through TOOLS.get(). Added after a real gap: the AI analyst's own
suggested question about a pack's own named KPI ("is there a Pupil
Premium attendance gap?") gave a *different*, less accurate answer than
the dedicated KPI engine, because the generic group_aggregate tool
grouped raw rows rather than the per-student aggregation the real KPI
calculation does — see docs/CHECKLIST.md's "Post-Phase-7: AI analyst
industry KPI tool" section.

This module has real test coverage (tests/test_ai_planner.py) using a
scripted FakeLLMClient — that verifies the loop itself (tool execution,
message threading, the iteration cap, error handling) is correct. It
does NOT verify that a real Claude model behaves sensibly when driving
this loop — that needs a real LLM_API_KEY, which this environment
doesn't have. See llm_client.py.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from typing import Any

import polars as pl

from app.core.industry_packs import IndustryPack
from app.services.analytics import AnalyticsError
from app.services.ai.llm_client import LLMClient
from app.services.industry_kpis import DEFAULT_KPI_WINDOW_MONTHS, compute_kpis
from app.services.tools import TOOLS, anthropic_tool_definitions

MAX_TOOL_ITERATIONS = 5

INDUSTRY_KPI_TOOL_NAME = "compute_industry_kpis"


def _industry_kpi_tool_definition(pack: IndustryPack) -> dict[str, Any]:
    kpi_names = ", ".join(k.name for k in pack.kpis)
    return {
        "name": INDUSTRY_KPI_TOOL_NAME,
        "description": (
            f"Computes this workspace's own precise, pre-defined {pack.name} KPIs, using the exact "
            f"same official definitions as this app's dedicated KPI engine — not an approximation "
            f"built from generic statistics tools. Prefer this over group_aggregate/descriptive_stats "
            f"whenever the question matches one of these specific metrics: {kpi_names}. Takes no "
            f"parameters — always computes and returns every KPI in the pack."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }


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
{industry_kpi_note}
Dataset: "{sheet_name}" ({row_count} rows, {column_count} columns)
Columns:
{column_summary}

Call tools as needed, then give your final answer as plain text.
"""

_INDUSTRY_KPI_NOTE_TEMPLATE = """6. This workspace has a {pack_name} KPI engine available via the \
{tool_name} tool. When a question matches one of its named KPIs, call that tool instead of \
approximating the same thing with group_aggregate/descriptive_stats — it uses this app's exact, \
tested definitions (e.g. per-entity aggregation done correctly), which a generic group-by over raw \
rows can get subtly wrong.
"""


def _build_system_prompt(table_profile: dict[str, Any], industry_pack: IndustryPack | None) -> str:
    column_lines = []
    for col in table_profile["columns"]:
        type_note = col["inferred_type"]
        if col["suggested_type"] != col["inferred_type"]:
            type_note += f" (looks like {col['suggested_type']} but stored as text)"
        column_lines.append(f"- {col['name']}: {type_note}, {col['null_ratio']:.0%} missing")

    industry_kpi_note = (
        _INDUSTRY_KPI_NOTE_TEMPLATE.format(pack_name=industry_pack.name, tool_name=INDUSTRY_KPI_TOOL_NAME)
        if industry_pack is not None
        else ""
    )

    return _SYSTEM_PROMPT_TEMPLATE.format(
        sheet_name=table_profile["sheet_name"],
        row_count=table_profile["row_count"],
        column_count=table_profile["column_count"],
        column_summary="\n".join(column_lines),
        industry_kpi_note=industry_kpi_note,
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
    industry_pack: IndustryPack | None = None,
    field_mapping: dict[str, str | None] | None = None,
    kpi_window_months: int | None = None,
) -> PlannerResult:
    system = _build_system_prompt(table_profile, industry_pack)
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": question}]
    turn_start = len(history)
    tool_defs = anthropic_tool_definitions()
    if industry_pack is not None:
        tool_defs = [*tool_defs, _industry_kpi_tool_definition(industry_pack)]
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
            result: dict[str, Any] | None = None
            error: str | None = None
            if tu.name == INDUSTRY_KPI_TOOL_NAME:
                if industry_pack is None or field_mapping is None:
                    # The model called this tool despite it not being in
                    # tool_defs for this conversation — shouldn't happen,
                    # but reject cleanly rather than crash the turn.
                    error = f"{INDUSTRY_KPI_TOOL_NAME} is not available for this workspace."
                else:
                    kpi_results = compute_kpis(
                        df,
                        industry_pack,
                        field_mapping,
                        as_of=dt.date.today(),
                        window_months=kpi_window_months or DEFAULT_KPI_WINDOW_MONTHS,
                    )
                    # KPIResult itself carries no description (every
                    # other consumer — the REST endpoint, the dashboard
                    # widget — gets that from GET /industry-packs
                    # instead, which the model never sees). Without it,
                    # a model has only a bare name and number to go on
                    # for a metric whose sign is meaningful but not
                    # self-evident (e.g. "Pupil Premium Attendance Gap"
                    # being positive doesn't obviously mean PP students
                    # attend *more*) — caught live: a real model call
                    # retrieved the exact right number but got the
                    # direction backwards in its prose. Looked up by
                    # kpi_id from the pack definition and merged in here
                    # specifically, so the model has the same context a
                    # human reading the dashboard would.
                    descriptions = {k.kpi_id: k.description for k in industry_pack.kpis}
                    result = {
                        "pack_name": industry_pack.name,
                        "kpis": [
                            {**asdict(r), "description": descriptions.get(r.kpi_id)} for r in kpi_results
                        ],
                        "compliance_caveat": industry_pack.compliance_caveat,
                    }
            else:
                tool = TOOLS.get(tu.name)
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
