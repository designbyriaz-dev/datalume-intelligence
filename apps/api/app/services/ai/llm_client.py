"""LLM client abstraction for the AI data analyst.

IMPORTANT — read this before trusting anything in this module worked:
`AnthropicLLMClient` is written correctly against the documented Anthropic
Messages API (tool use / agentic loop shape), but has NOT been exercised
against a real API key in this codebase — there is no key configured in
this environment. Only `FakeLLMClient` (in tests) has actually been
exercised, and it tests the orchestration loop in planner.py, not real
model behaviour. Do not report this as "working" until it's been run
against a real key and someone has looked at a real answer.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings


class LLMNotConfiguredError(Exception):
    """Raised when the AI analyst is invoked but no LLM_API_KEY is set.
    Routers should turn this into a 503 — never silently return a fake
    answer."""


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None
    tool_uses: list[ToolUseBlock]
    stop_reason: str


class LLMClient(abc.ABC):
    @abc.abstractmethod
    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse: ...


class AnthropicLLMClient(LLMClient):
    """Real implementation — UNVERIFIED, see module docstring."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=messages,
            tools=tools,
        )

        text_parts: list[str] = []
        tool_uses: list[ToolUseBlock] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(ToolUseBlock(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_uses=tool_uses,
            stop_reason=response.stop_reason or "end_turn",
        )


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMNotConfiguredError(
            "No LLM_API_KEY configured. The AI data analyst is scaffolded but not connected to a "
            "real model — see docs/CHECKLIST.md."
        )
    if settings.llm_provider != "anthropic":
        raise LLMNotConfiguredError(
            f"LLM_PROVIDER={settings.llm_provider!r} is not implemented yet — only 'anthropic' is."
        )
    return AnthropicLLMClient(api_key=settings.llm_api_key)
