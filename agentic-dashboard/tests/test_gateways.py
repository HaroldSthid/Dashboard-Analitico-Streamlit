"""Unit tests for Phase 3 model gateways.

Phase 3 scope: `GatewayResponse`, the `ModelGateway` ABC, `OpenRouterGateway`,
`OllamaGateway`, and `build_gateway()`. No live network calls — every HTTP
interaction is stubbed via `httpx.MockTransport`.

See tasks 3.1-3.8 in `sdd/agentic-dashboard/tasks`.
"""

from __future__ import annotations

import json

import httpx
import pytest

from gateways import (
    GatewayResponse,
    ModelGateway,
    OllamaGateway,
    OpenRouterGateway,
    build_gateway,
)


class TestGatewayResponse:
    def test_constructs_text_response(self):
        response = GatewayResponse(
            kind="text",
            text="Hello there",
            tool_name=None,
            tool_args=None,
            raw={"choices": []},
        )

        assert response.kind == "text"
        assert response.text == "Hello there"
        assert response.tool_name is None
        assert response.tool_args is None
        assert response.raw == {"choices": []}

    def test_constructs_tool_call_response(self):
        response = GatewayResponse(
            kind="tool_call",
            text=None,
            tool_name="listar_leads_priorizados",
            tool_args={"limit": 5},
            raw={"choices": [{"finish_reason": "tool_calls"}]},
        )

        assert response.kind == "tool_call"
        assert response.tool_name == "listar_leads_priorizados"
        assert response.tool_args == {"limit": 5}


class TestModelGatewayIsAbstract:
    def test_cannot_instantiate_model_gateway_directly(self):
        with pytest.raises(TypeError):
            ModelGateway()

    def test_concrete_subclass_without_complete_cannot_instantiate(self):
        class IncompleteGateway(ModelGateway):
            pass

        with pytest.raises(TypeError):
            IncompleteGateway()


# ---------------------------------------------------------------------------
# Shared OpenAI-compatible response fixtures
# ---------------------------------------------------------------------------


def _text_completion_payload(content: str = "The answer is 42.") -> dict:
    return {
        "id": "chatcmpl-fake",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, "tool_calls": None},
            }
        ],
    }


def _tool_call_completion_payload(
    tool_name: str = "listar_leads_priorizados",
    tool_args: dict | None = None,
) -> dict:
    tool_args = tool_args if tool_args is not None else {"tier": "Alto", "limit": 5}
    return {
        "id": "chatcmpl-fake-tool",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            },
                        }
                    ],
                },
            }
        ],
    }


def _mock_transport(payload: dict, expected_url: str | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if expected_url is not None:
            assert str(request.url) == expected_url
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


class TestOpenRouterGatewayTextResponse:
    def test_parses_text_reply_into_gateway_response(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        transport = _mock_transport(
            _text_completion_payload("The answer is 42."),
            expected_url="https://openrouter.ai/api/v1/chat/completions",
        )
        gateway = OpenRouterGateway(transport=transport)

        result = gateway.complete(
            messages=[{"role": "user", "content": "What is the answer?"}],
            tools=[],
        )

        assert isinstance(result, GatewayResponse)
        assert result.kind == "text"
        assert result.text == "The answer is 42."
        assert result.tool_name is None
        assert result.tool_args is None
        assert result.raw["id"] == "chatcmpl-fake"


class TestOpenRouterGatewayToolCallResponse:
    def test_parses_tool_call_reply_into_gateway_response(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        transport = _mock_transport(
            _tool_call_completion_payload("explicar_tier_de_lead", {"idprospecto": 7})
        )
        gateway = OpenRouterGateway(transport=transport)

        result = gateway.complete(
            messages=[{"role": "user", "content": "Explain lead 7"}],
            tools=[{"name": "explicar_tier_de_lead"}],
        )

        assert result.kind == "tool_call"
        assert result.text is None
        assert result.tool_name == "explicar_tier_de_lead"
        assert result.tool_args == {"idprospecto": 7}


class TestOllamaGatewayTextResponse:
    def test_parses_text_reply_into_gateway_response(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        transport = _mock_transport(
            _text_completion_payload("Ollama says hi."),
            expected_url="http://localhost:11434/v1/chat/completions",
        )
        gateway = OllamaGateway(transport=transport)

        result = gateway.complete(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )

        assert result.kind == "text"
        assert result.text == "Ollama says hi."


class TestOllamaGatewayToolCallResponse:
    def test_parses_tool_call_reply_into_gateway_response(self, monkeypatch):
        transport = _mock_transport(
            _tool_call_completion_payload("resumen_por_cluster", {"hobby_estandar": "Lectura"})
        )
        gateway = OllamaGateway(transport=transport)

        result = gateway.complete(
            messages=[{"role": "user", "content": "summarize"}],
            tools=[{"name": "resumen_por_cluster"}],
        )

        assert result.kind == "tool_call"
        assert result.tool_name == "resumen_por_cluster"
        assert result.tool_args == {"hobby_estandar": "Lectura"}

    def test_uses_configurable_base_url_and_model(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-host:9999")
        monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
        transport = _mock_transport(
            _text_completion_payload("custom host reply"),
            expected_url="http://custom-host:9999/v1/chat/completions",
        )
        gateway = OllamaGateway(transport=transport)

        assert gateway.model == "llama3:8b"
        result = gateway.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert result.text == "custom host reply"


class TestBuildGateway:
    def test_openrouter_backend_returns_openrouter_gateway(self, monkeypatch):
        monkeypatch.setenv("AGENT_LLM_BACKEND", "openrouter")
        gateway = build_gateway()
        assert isinstance(gateway, OpenRouterGateway)

    def test_ollama_backend_returns_ollama_gateway(self, monkeypatch):
        monkeypatch.setenv("AGENT_LLM_BACKEND", "ollama")
        gateway = build_gateway()
        assert isinstance(gateway, OllamaGateway)

    def test_unset_backend_defaults_to_ollama_gateway(self, monkeypatch):
        monkeypatch.delenv("AGENT_LLM_BACKEND", raising=False)
        gateway = build_gateway()
        assert isinstance(gateway, OllamaGateway)

    def test_unknown_backend_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("AGENT_LLM_BACKEND", "bogus")
        with pytest.raises(ValueError):
            build_gateway()
