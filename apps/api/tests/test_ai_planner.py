"""Tests the AI query planner's orchestration loop (tool execution,
message threading, iteration cap, error handling) using a scripted fake
LLM client. This does NOT test real model behaviour — no LLM_API_KEY is
configured in this environment. It tests that the harness around a model
is correct, so that once a real key is available, only the model's
judgment is new and unverified, not the plumbing around it.
"""

from dataclasses import asdict

import polars as pl

from app.services.ai.llm_client import LLMClient, LLMResponse, ToolUseBlock
from app.services.ai.planner import run_conversation_turn
from app.services.profiling import profile_table


class ScriptedLLMClient(LLMClient):
    """Returns pre-scripted responses in order, one per call to
    complete(). Also records every call it received, so tests can assert
    on what the planner actually sent (system prompt, message history,
    tool results fed back)."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, *, system, messages, tools):
        # A shallow copy of `messages`, not the live list — planner.py
        # keeps appending to the same list object after this call
        # returns (the closing assistant message, further iterations),
        # so storing the reference itself would make a recorded call's
        # "messages" silently change after the fact.
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if not self._responses:
            raise AssertionError("ScriptedLLMClient ran out of scripted responses")
        return self._responses.pop(0)


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "category": ["office", "office", "retail", "retail", "industrial"],
            "rent": [1200, 950, 2000, 2100, 500],
        }
    )


def _sample_profile() -> dict:
    return asdict(profile_table("Sheet1", _sample_df()))


async def test_planner_returns_text_only_response_with_no_tool_calls():
    client = ScriptedLLMClient([LLMResponse(text="Hello, ask me about your data.", tool_uses=[], stop_reason="end_turn")])

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="hi"
    )

    assert result.answer == "Hello, ask me about your data."
    assert result.tool_calls == []
    assert len(client.calls) == 1
    assert "rent" in client.calls[0]["system"]  # column grounding present in system prompt


async def test_planner_executes_tool_call_and_feeds_result_back():
    client = ScriptedLLMClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "rent"})],
                stop_reason="tool_use",
            ),
            LLMResponse(
                text="The average rent is 1350.",
                tool_uses=[],
                stop_reason="end_turn",
            ),
        ]
    )

    result = await run_conversation_turn(
        client,
        df=_sample_df(),
        table_profile=_sample_profile(),
        history=[],
        question="What's the average rent?",
    )

    assert result.answer == "The average rent is 1350."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "descriptive_stats"
    assert result.tool_calls[0].error is None
    assert result.tool_calls[0].result["mean"] == 1350.0

    # Verify the second call actually received the real tool result, not
    # a placeholder — this is the "evidence-grounded" plumbing working.
    second_call_messages = client.calls[1]["messages"]
    tool_result_message = next(m for m in second_call_messages if m["role"] == "user" and isinstance(m["content"], list))
    tool_result_block = tool_result_message["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert '"mean":1350.0' in tool_result_block["content"].replace(" ", "")


async def test_planner_records_tool_error_without_crashing():
    client = ScriptedLLMClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "category"})],
                stop_reason="tool_use",
            ),
            LLMResponse(
                text="I can't compute an average of a text column.",
                tool_uses=[],
                stop_reason="end_turn",
            ),
        ]
    )

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="average of category?"
    )

    assert result.tool_calls[0].error is not None
    assert "not numeric" in result.tool_calls[0].error
    assert result.answer == "I can't compute an average of a text column."


async def test_planner_rejects_unknown_tool_name_gracefully():
    client = ScriptedLLMClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="delete_everything", input={})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="That operation isn't available.", tool_uses=[], stop_reason="end_turn"),
        ]
    )

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="delete it all"
    )

    assert result.tool_calls[0].error == "Unknown tool: delete_everything"
    assert result.tool_calls[0].result is None


async def test_planner_message_delta_for_text_only_response():
    client = ScriptedLLMClient([LLMResponse(text="Hi there.", tool_uses=[], stop_reason="end_turn")])

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="hi"
    )

    assert result.message_delta == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hi there."},
    ]


async def test_planner_message_delta_includes_tool_use_and_tool_result_blocks():
    client = ScriptedLLMClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "rent"})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="The average rent is 1350.", tool_uses=[], stop_reason="end_turn"),
        ]
    )

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="average rent?"
    )

    assert len(result.message_delta) == 4
    assert result.message_delta[0] == {"role": "user", "content": "average rent?"}
    assert result.message_delta[1]["role"] == "assistant"
    assert result.message_delta[1]["content"][0] == {
        "type": "tool_use",
        "id": "tu_1",
        "name": "descriptive_stats",
        "input": {"column": "rent"},
    }
    assert result.message_delta[2]["role"] == "user"
    assert result.message_delta[2]["content"][0]["type"] == "tool_result"
    assert result.message_delta[2]["content"][0]["tool_use_id"] == "tu_1"
    assert result.message_delta[3] == {"role": "assistant", "content": "The average rent is 1350."}


async def test_planner_message_delta_ends_with_assistant_message_on_iteration_limit():
    responses = [
        LLMResponse(
            text=None,
            tool_uses=[ToolUseBlock(id=f"tu_{i}", name="descriptive_stats", input={"column": "rent"})],
            stop_reason="tool_use",
        )
        for i in range(10)
    ]
    client = ScriptedLLMClient(responses)

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="loop forever?"
    )

    # Must end on an assistant-role message — a subsequent turn's user
    # question appended directly after a user-role tool_result would be
    # two consecutive user-role messages, which the Anthropic API rejects.
    assert result.message_delta[-1]["role"] == "assistant"
    assert result.message_delta[-1]["content"] == result.answer


async def test_planner_replays_prior_turn_with_full_tool_use_fidelity_not_flattened_text():
    """The actual bug this fixes: a second turn in the same conversation
    must see the first turn's tool_use/tool_result blocks in its message
    history, not a flattened plain-text summary — otherwise the model
    has no way to know it already has a specific grounded result and may
    redundantly re-call the same tool."""
    first_turn_client = ScriptedLLMClient(
        [
            LLMResponse(
                text=None,
                tool_uses=[ToolUseBlock(id="tu_1", name="descriptive_stats", input={"column": "rent"})],
                stop_reason="tool_use",
            ),
            LLMResponse(text="The average rent is 1350.", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    first_result = await run_conversation_turn(
        first_turn_client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="average rent?"
    )

    second_turn_client = ScriptedLLMClient(
        [LLMResponse(text="That's the same figure as before.", tool_uses=[], stop_reason="end_turn")]
    )
    await run_conversation_turn(
        second_turn_client,
        df=_sample_df(),
        table_profile=_sample_profile(),
        history=first_result.message_delta,
        question="can you confirm that?",
    )

    sent_history = second_turn_client.calls[0]["messages"]
    # The replayed history must contain the original tool_use block
    # (not just its text description) ahead of the new question.
    tool_use_messages = [
        m for m in sent_history if isinstance(m.get("content"), list)
        and any(block.get("type") == "tool_use" for block in m["content"])
    ]
    assert len(tool_use_messages) == 1
    assert tool_use_messages[0]["content"][0]["name"] == "descriptive_stats"
    assert sent_history[-1] == {"role": "user", "content": "can you confirm that?"}


async def test_planner_stops_after_max_iterations_instead_of_looping_forever():
    # Script 6 tool-use responses in a row — more than MAX_TOOL_ITERATIONS (5).
    responses = [
        LLMResponse(
            text=None,
            tool_uses=[ToolUseBlock(id=f"tu_{i}", name="descriptive_stats", input={"column": "rent"})],
            stop_reason="tool_use",
        )
        for i in range(10)
    ]
    client = ScriptedLLMClient(responses)

    result = await run_conversation_turn(
        client, df=_sample_df(), table_profile=_sample_profile(), history=[], question="loop forever?"
    )

    assert result.hit_iteration_limit is True
    assert len(client.calls) == 5  # MAX_TOOL_ITERATIONS, not 10 — the loop actually bounded itself
