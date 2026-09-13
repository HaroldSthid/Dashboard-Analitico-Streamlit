"""Model gateways: a provider-agnostic ABC plus OpenAI-compatible implementations.

Phase 3 scope only: `GatewayResponse`, `ModelGateway`, `OpenRouterGateway`,
`OllamaGateway`, and `build_gateway()`. No agent loop, no tracing, no UI —
those are later PRs (PR4-PR6). See tasks 3.1-3.8 in
`sdd/agentic-dashboard/tasks`.

Both `OpenRouterGateway` and `OllamaGateway` talk to an OpenAI-compatible
`chat/completions` endpoint over `httpx`, so they share one response parser
(`_parse_openai_completion`). A gateway's `transport` constructor argument
exists purely for test injection (`httpx.MockTransport`); production callers
leave it `None` and get real network I/O.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import httpx

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openrouter/auto"


@dataclass(frozen=True)
class GatewayResponse:
    """Normalized reply from a model gateway.

    `raw` always carries the untouched provider response body, so callers
    (e.g. the future `trace.py`) can log exactly what the provider returned.
    """

    kind: Literal["text", "tool_call"]
    text: str | None
    tool_name: str | None
    tool_args: dict | None
    raw: dict


class ModelGateway(ABC):
    """Provider-agnostic contract every model gateway must implement."""

    @abstractmethod
    def complete(self, messages: list[dict], tools: list[dict]) -> GatewayResponse:
        """Send `messages` (+ optional `tools`) to the model and return a
        normalized `GatewayResponse`."""
        raise NotImplementedError


def _parse_openai_completion(raw: dict) -> GatewayResponse:
    """Parse an OpenAI-compatible `chat/completions` response body.

    Shared by `OpenRouterGateway` and `OllamaGateway`, since both expose the
    same OpenAI-style function-calling response shape:
    `choices[0].message.tool_calls[0].function.{name,arguments}` for a tool
    call, or `choices[0].message.content` for a plain text reply.
    """

    message = raw["choices"][0]["message"]
    tool_calls = message.get("tool_calls")

    if tool_calls:
        function = tool_calls[0]["function"]
        return GatewayResponse(
            kind="tool_call",
            text=None,
            tool_name=function["name"],
            tool_args=json.loads(function["arguments"]),
            raw=raw,
        )

    return GatewayResponse(
        kind="text",
        text=message.get("content"),
        tool_name=None,
        tool_args=None,
        raw=raw,
    )


def _post_chat_completion(
    *,
    url: str,
    payload: dict,
    headers: dict,
    transport: httpx.BaseTransport | None,
) -> dict:
    """POST a chat-completions request and return the decoded JSON body."""

    with httpx.Client(transport=transport, timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


class OpenRouterGateway(ModelGateway):
    """Calls OpenRouter's OpenAI-compatible `chat/completions` endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_OPENROUTER_MODEL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self.model = model
        self._transport = transport

    def complete(self, messages: list[dict], tools: list[dict]) -> GatewayResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": messages, "tools": tools}
        raw = _post_chat_completion(
            url=OPENROUTER_CHAT_COMPLETIONS_URL,
            payload=payload,
            headers=headers,
            transport=self._transport,
        )
        return _parse_openai_completion(raw)


class OllamaGateway(ModelGateway):
    """Calls a local Ollama server's OpenAI-compatible `chat/completions` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url if base_url is not None else os.environ.get(
            "OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL
        )
        self.model = model if model is not None else os.environ.get(
            "OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL
        )
        self._transport = transport

    def complete(self, messages: list[dict], tools: list[dict]) -> GatewayResponse:
        payload = {"model": self.model, "messages": messages, "tools": tools}
        raw = _post_chat_completion(
            url=f"{self.base_url}/v1/chat/completions",
            payload=payload,
            headers={},
            transport=self._transport,
        )
        return _parse_openai_completion(raw)


def build_gateway() -> ModelGateway:
    """Build the configured `ModelGateway` from `AGENT_LLM_BACKEND`.

    Defaults to `"ollama"` when unset. Raises `ValueError` for any value
    other than `"openrouter"` or `"ollama"`.
    """

    backend = os.environ.get("AGENT_LLM_BACKEND", "ollama")

    if backend == "openrouter":
        return OpenRouterGateway()
    if backend == "ollama":
        return OllamaGateway()

    raise ValueError(
        f"Unknown AGENT_LLM_BACKEND: {backend!r}. Expected 'openrouter' or 'ollama'."
    )
