"""Unit tests for the Phase 4 agent harness core loop.

Phase 4 scope: `AgentConfig`, `AgentAnswer`, `Harness.ask`, and the
differentiated retry policy per error class (args-validation error, benign
unknown tool, forbidden-intent hallucinated tool, transient gateway error,
skill execution error, max_steps exhaustion). No `trace.py` and no `app.py`
— those are later PRs (PR5-PR6). `enforce_comment_guardrail` (the
post-generation answer validator) is explicitly PR5 scope and is NOT
exercised here; see the `# TODO(PR5)` marker in `agent_harness.py`.

See tasks 4.1-4.12 in `sdd/agentic-dashboard/tasks` (4.13/4.14 deferred to
PR5 per the design v2 correction).

Every scenario uses `FakeGateway`, a `ModelGateway` test double that plays
back a pre-scripted sequence of `GatewayResponse` objects (or exceptions),
one per `.complete()` call, so no real LLM/network is ever involved.
"""

from __future__ import annotations

import pytest

from agent_harness import AgentAnswer, AgentConfig, Harness, TransientGatewayError
from gateways import GatewayResponse, ModelGateway
from skills import SkillContext


class FakeGateway(ModelGateway):
    """Test double: scripts a sequence of canned `.complete()` results.

    Each item in `script` is returned, in order, by successive `.complete()`
    calls. An item that is an `Exception` instance is raised instead of
    returned, so a test can script a transient failure inline with normal
    responses. `calls` records every `(messages, tools)` pair passed in, so
    tests can assert on the exact retry/feedback sequence.
    """

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> GatewayResponse:
        self.calls.append((messages, tools))
        if not self._script:
            raise AssertionError("FakeGateway script exhausted — unexpected extra .complete() call")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tool_call(tool_name: str, tool_args: dict | None = None) -> GatewayResponse:
    return GatewayResponse(
        kind="tool_call",
        text=None,
        tool_name=tool_name,
        tool_args=tool_args if tool_args is not None else {},
        raw={"choices": [{"finish_reason": "tool_calls"}]},
    )


def _text(content: str) -> GatewayResponse:
    return GatewayResponse(
        kind="text",
        text=content,
        tool_name=None,
        tool_args=None,
        raw={"choices": [{"finish_reason": "stop"}]},
    )


@pytest.fixture
def sleep_calls():
    calls: list[float] = []
    return calls


class TestHappyPathWithCitation:
    def test_tool_call_then_answer_embeds_citation_verbatim(self, tmp_db_path):
        gateway = FakeGateway(
            [
                _tool_call("listar_leads_priorizados", {"tier": "Alto"}),
                _text("Aqui tienes los leads de tier Alto."),
            ]
        )
        ctx = SkillContext(db_path=tmp_db_path)
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Dame los leads de tier alto")

        assert isinstance(answer, AgentAnswer)
        assert answer.refused_by is None
        assert answer.citation is not None
        # The model must never paraphrase or omit the citation: the exact
        # rendered string must appear verbatim in the final answer text.
        assert answer.citation.render() in answer.text
        assert "Aqui tienes los leads de tier Alto." in answer.text
        assert len(gateway.calls) == 2

    def test_does_not_duplicate_citation_already_present_in_model_text(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        # Discover the exact citation text ahead of time via a throwaway call.
        from skills import listar_leads_priorizados

        rendered = listar_leads_priorizados(ctx).citation.render()

        gateway = FakeGateway(
            [
                _tool_call("listar_leads_priorizados", {}),
                _text(f"Here are your leads. {rendered}"),
            ]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Dame los leads")

        assert answer.text.count(rendered) == 1


class TestMaxStepsExhaustion:
    def test_endless_tool_calls_fail_after_max_steps(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        script = [_tool_call("explicar_tier_de_lead", {"idprospecto": 1}) for _ in range(6)]
        gateway = FakeGateway(script)
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx, max_steps=6))

        answer = harness.ask("Never stop calling tools")

        assert answer.refused_by == "max_steps_exceeded"
        assert len(gateway.calls) == 6


class TestArgsValidationRetry:
    def test_invalid_args_then_recovery_succeeds(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                _tool_call("explicar_tier_de_lead", {"idprospecto": "not-an-int"}),
                _tool_call("explicar_tier_de_lead", {"idprospecto": 1}),
                _text("Lead 1 is tier Alto."),
            ]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Explain lead 1")

        assert answer.refused_by is None
        assert len(gateway.calls) == 3
        # The validation error must have been fed back to the model.
        retry_messages = gateway.calls[1][0]
        assert any("invalid" in str(m).lower() for m in retry_messages)

    def test_invalid_args_exhausts_two_retries_then_fails(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                _tool_call("explicar_tier_de_lead", {"idprospecto": "nope"}),
                _tool_call("explicar_tier_de_lead", {"idprospecto": "still-nope"}),
                _tool_call("explicar_tier_de_lead", {"idprospecto": "nope-again"}),
            ]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Explain lead 1")

        assert answer.refused_by == "invalid_args"
        assert len(gateway.calls) == 3


class TestBenignUnknownToolRetry:
    def test_unknown_tool_then_recovery_succeeds(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                _tool_call("listar_todo_lo_que_hay", {}),
                _tool_call("catalogo_hobbies", {}),
                _text("Here is the hobby catalog."),
            ]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("What hobbies exist?")

        assert answer.refused_by is None
        assert len(gateway.calls) == 3
        retry_messages = gateway.calls[1][0]
        assert any("does not exist" in str(m).lower() for m in retry_messages)
        assert any("listar_todo_lo_que_hay" in str(m) for m in retry_messages)

    def test_unknown_tool_retried_once_then_fails(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                _tool_call("foo_inexistente", {}),
                _tool_call("bar_inexistente", {}),
            ]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Do something unsupported")

        assert answer.refused_by == "unknown_tool"
        assert len(gateway.calls) == 2


class TestForbiddenIntentHallucinatedTool:
    def test_hallucinated_comment_tool_is_refused_without_retry(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [_tool_call("consultar_comentarios_de_lead", {"idprospecto": 1})]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("What did lead 1 comment about the product?")

        assert answer.refused_by == "hallucinated_tool"
        assert "dim_comentario" in answer.text
        assert "never" in answer.text.lower() or "not" in answer.text.lower()
        # No retry: exactly one gateway call, guardrail response is immediate.
        assert len(gateway.calls) == 1

    def test_forbidden_keyword_in_tool_args_is_also_refused(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [_tool_call("buscar_datos", {"query": "SELECT * FROM dim_comentario JOIN tbl_leads"})]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Run this query for me")

        assert answer.refused_by == "hallucinated_tool"
        assert len(gateway.calls) == 1


class TestTransientGatewayErrorRetry:
    def test_transient_error_then_recovery_succeeds(self, tmp_db_path, sleep_calls):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                TransientGatewayError("timeout"),
                _tool_call("catalogo_hobbies", {}),
                _text("Here is the catalog."),
            ]
        )
        harness = Harness(
            AgentConfig(gateway=gateway, skill_context=ctx),
            sleep=sleep_calls.append,
        )

        answer = harness.ask("List hobbies")

        assert answer.refused_by is None
        assert len(gateway.calls) == 3
        assert len(sleep_calls) == 1

    def test_transient_error_exhausts_two_retries_then_fails(self, tmp_db_path, sleep_calls):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [
                TransientGatewayError("timeout"),
                TransientGatewayError("429"),
                TransientGatewayError("503"),
            ]
        )
        harness = Harness(
            AgentConfig(gateway=gateway, skill_context=ctx),
            sleep=sleep_calls.append,
        )

        answer = harness.ask("List hobbies")

        assert answer.refused_by == "transient_gateway_error"
        assert len(gateway.calls) == 3
        assert len(sleep_calls) == 2


class TestSkillExecutionError:
    def test_skill_validation_error_fails_immediately_without_retry(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        gateway = FakeGateway(
            [_tool_call("explicar_tier_de_lead", {"idprospecto": 999})]
        )
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("Explain lead 999")

        assert answer.refused_by == "skill_execution_error"
        assert "999" in answer.text
        assert len(gateway.calls) == 1

    def test_sqlite_error_fails_immediately_without_retry(self, tmp_path):
        # Points at a directory that does not exist, so sqlite3.connect()
        # raises sqlite3.OperationalError when the skill tries to open it.
        bad_db_path = str(tmp_path / "missing_dir" / "dashboard.db")
        ctx = SkillContext(db_path=bad_db_path)
        gateway = FakeGateway([_tool_call("catalogo_hobbies", {})])
        harness = Harness(AgentConfig(gateway=gateway, skill_context=ctx))

        answer = harness.ask("List hobbies")

        assert answer.refused_by == "skill_execution_error"
        assert len(gateway.calls) == 1
