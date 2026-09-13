"""Agent harness: the REASON -> SELECT -> EXECUTE -> OBSERVE -> ANSWER core
loop, plus a differentiated retry policy per error class.

Phase 4 scope: `AgentConfig`, `AgentAnswer`, `Harness`, and
`TransientGatewayError`. See tasks 4.1-4.12 in `sdd/agentic-dashboard/tasks`.

Phase 5 scope (this file's `enforce_comment_guardrail` wiring and
`trace_writer` wiring): every terminal `AgentAnswer` `Harness.ask()` returns
— happy path AND every Phase-4 failure/refusal path — is passed through
`enforce_comment_guardrail` (`guardrail.py`) before it is returned, with no
bypass path. This supersedes the earlier "no-tool-call forbidden question"
task (4.13/4.14, deferred per the design v2 correction): PR4's
`_is_forbidden_intent` below only catches a *hallucinated tool call*
reaching for `dim_comentario`; it cannot catch the model answering directly
from its own (hallucinated) knowledge with no tool call at all. Closing
that gap is exactly what the Phase-5 guardrail choke point in `ask()` does.
See tasks 5.3/5.4/5.6/5.7 in `sdd/agentic-dashboard/tasks`.

Vocabulary (`catalogo_categorias_comentario`) and the full lead-id
population (`listar_leads_priorizados`) are both loaded once, at `Harness`
construction time, and cached for the lifetime of the instance — see
`_load_vocabulary` / `_load_all_lead_ids` for why the full lead population
(not just ids touched by this specific `ask()` call) is required to close
the no-tool-call gap, and why both loaders fail open (empty result) rather
than raising out of `__init__` on a database error.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import ValidationError

from gateways import GatewayResponse, ModelGateway
from guardrail import enforce_comment_guardrail
from skills import (
    SKILLS,
    TOOLS_SCHEMA,
    SkillContext,
    SkillResult,
    SkillValidationError,
    ThresholdCitation,
    catalogo_categorias_comentario,
    listar_leads_priorizados,
)
from trace import TraceWriter

# `_SKILL_ARGS_MODELS` is a module-private mapping in `skills.py` (skill name
# -> its Pydantic args model). There is no public accessor for it and
# `skills.py` is a closed Phase-1/2 file the harness must not modify, so it
# is imported directly here under its real name for clarity at the call
# site. This is a read, never a mutation, of that module.
from skills import _SKILL_ARGS_MODELS as SKILL_ARGS_MODELS

# Loading the full lead population uses `listar_leads_priorizados`'s
# `limit` truncation as an "effectively unbounded" sentinel; there is no
# dedicated "no limit" option on that skill (see skills.py), and this
# dataset is a single dashboard's lead table, never large enough for this
# to matter in practice.
_ALL_LEADS_LIMIT = 1_000_000

# Case-insensitive keywords that mark a hallucinated tool call as a
# forbidden-intent guardrail violation rather than a benign unknown tool
# (tasks 4.7/4.8). `dim_comentario` is vocabulary-only and is never joined
# to `tbl_leads` in any skill — see skills.py's module docstring.
FORBIDDEN_INTENT_KEYWORDS: tuple[str, ...] = ("comentario", "sql", "query", "join")

MAX_ARGS_VALIDATION_RETRIES = 2
MAX_UNKNOWN_TOOL_RETRIES = 1
MAX_TRANSIENT_RETRIES = 2

_HALLUCINATED_TOOL_MESSAGE = (
    "I can't call {tool_name!r} — that tool does not exist. "
    "dim_comentario is a vocabulary-only reference catalog (comment "
    "categories); it is never joined to individual leads or lead "
    "identifiers, and I can't run SQL, queries, or joins against it on "
    "your behalf. I can only call the closed set of registered skills."
)


class TransientGatewayError(Exception):
    """A transient gateway failure (timeout, HTTP 429, HTTP 5xx) that the
    harness may retry with backoff before giving up (tasks 4.9/4.10)."""


@dataclass
class AgentConfig:
    """Configuration for one `Harness` instance."""

    gateway: ModelGateway
    skill_context: SkillContext
    max_steps: int = 6
    trace_writer: TraceWriter | None = None


@dataclass
class AgentAnswer:
    """The harness's final, terminal answer to one `Harness.ask()` call."""

    text: str
    citation: ThresholdCitation | None = None
    tables: list[dict] = field(default_factory=list)
    chart_spec: dict | None = None
    refused_by: str | None = None


def _default_backoff(attempt: int) -> float:
    """Simple exponential backoff in seconds: 1, 2, 4, ... for attempt 1, 2, 3."""

    return float(2 ** (attempt - 1))


@dataclass
class _TraceState:
    """Accumulates step/retry records for one `Harness.ask()` call, only
    when `AgentConfig.trace_writer` is configured (tasks 5.6/5.7)."""

    steps: list[dict] = field(default_factory=list)
    retries: list[dict] = field(default_factory=list)


# `refused_by` values that represent a deliberate guardrail-style refusal
# (the harness recognized and blocked a forbidden request) rather than an
# operational failure (retries exhausted, invalid input, a downstream
# error). Used only to label the trace's `outcome` field.
_REFUSAL_KINDS = frozenset({"hallucinated_tool", "comment_guardrail"})


class Harness:
    """Runs the REASON -> SELECT -> EXECUTE -> OBSERVE -> ANSWER loop for a
    single `AgentConfig`, applying a differentiated retry policy per error
    class encountered along the way. Every terminal `AgentAnswer` this
    class's `ask()` returns has already passed through
    `enforce_comment_guardrail` (tasks 5.3/5.4) — there is no bypass path."""

    def __init__(
        self,
        config: AgentConfig,
        sleep: Callable[[float], None] | None = None,
        backoff: Callable[[int], float] = _default_backoff,
    ) -> None:
        self.config = config
        self._sleep = sleep if sleep is not None else (lambda _seconds: None)
        self._backoff = backoff
        # Loaded once, at construction time, and cached for the instance's
        # lifetime (tasks 5.3/5.4).
        self._vocabulary: tuple[str, ...] = self._load_vocabulary()
        self._all_lead_ids: frozenset[int] = self._load_all_lead_ids()

    def ask(self, question: str) -> AgentAnswer:
        call_start = time.monotonic()
        trace_state = _TraceState() if self.config.trace_writer is not None else None
        lead_ids_seen_this_call: set[int] = set()

        raw_answer = self._run_conversation(question, lead_ids_seen_this_call, trace_state)

        # Mandatory final step (tasks 5.3/5.4): every terminal answer, on
        # every return path above (happy path AND every Phase-4
        # failure/refusal path), passes through the guardrail here before
        # `ask()` returns. `effective_lead_ids` is the full known lead
        # population unioned with whatever this specific call's skill
        # results touched -- the full population is what lets the guardrail
        # catch a forbidden combination even when the model never called a
        # tool this turn (see module docstring and `_load_all_lead_ids`).
        effective_lead_ids = self._all_lead_ids | frozenset(lead_ids_seen_this_call)
        answer = enforce_comment_guardrail(raw_answer, effective_lead_ids, self._vocabulary)

        if trace_state is not None:
            self._write_trace(question, answer, trace_state, call_start)

        return answer

    def _run_conversation(
        self,
        question: str,
        lead_ids_seen_this_call: set[int],
        trace_state: _TraceState | None,
    ) -> AgentAnswer:
        """The Phase-4 REASON -> SELECT -> EXECUTE -> OBSERVE -> ANSWER loop.

        Returns the pre-guardrail `AgentAnswer`; `ask()` is the single
        choke point that applies `enforce_comment_guardrail` afterwards."""

        messages: list[dict] = [{"role": "user", "content": question}]
        last_citation: ThresholdCitation | None = None
        args_retries = 0
        unknown_tool_retries = 0
        step_number = 0

        for _step in range(self.config.max_steps):
            response = self._reason(messages, trace_state)
            if response is None:
                return AgentAnswer(
                    text=(
                        "The model gateway is temporarily unavailable after "
                        f"{MAX_TRANSIENT_RETRIES} retries. Please try again."
                    ),
                    refused_by="transient_gateway_error",
                )

            if response.kind == "text":
                return self._answer(response.text or "", last_citation)

            # SELECT: resolve the requested tool against the closed registry.
            tool_name = response.tool_name or ""
            skill_fn = SKILLS.get(tool_name)

            if skill_fn is None:
                if self._is_forbidden_intent(tool_name, response.tool_args):
                    return AgentAnswer(
                        text=_HALLUCINATED_TOOL_MESSAGE.format(tool_name=tool_name),
                        refused_by="hallucinated_tool",
                    )

                unknown_tool_retries += 1
                if trace_state is not None:
                    trace_state.retries.append(
                        {
                            "kind": "unknown_tool",
                            "attempt": unknown_tool_retries,
                            "detail": f"tool {tool_name!r} does not exist",
                        }
                    )
                if unknown_tool_retries > MAX_UNKNOWN_TOOL_RETRIES:
                    return AgentAnswer(
                        text=(
                            f"The tool {tool_name!r} does not exist and no valid "
                            "tool call followed the correction."
                        ),
                        refused_by="unknown_tool",
                    )

                call_id = f"call_{uuid.uuid4().hex[:24]}"
                messages.append(self._assistant_tool_call_message(response, call_id))
                messages.append(
                    self._tool_result_message(
                        call_id,
                        tool_name,
                        f"Error: tool {tool_name!r} does not exist. "
                        f"Available tools: {sorted(SKILLS)}.",
                    )
                )
                continue

            # Validate tool_args against the skill's own Pydantic args model.
            args_model = SKILL_ARGS_MODELS[tool_name]
            try:
                validated_args = args_model(**(response.tool_args or {}))
            except ValidationError as exc:
                args_retries += 1
                if trace_state is not None:
                    trace_state.retries.append(
                        {
                            "kind": "invalid_args",
                            "attempt": args_retries,
                            "detail": f"{tool_name}: {exc}",
                        }
                    )
                if args_retries > MAX_ARGS_VALIDATION_RETRIES:
                    return AgentAnswer(
                        text=f"Invalid arguments for tool {tool_name!r}: {exc}",
                        refused_by="invalid_args",
                    )

                call_id = f"call_{uuid.uuid4().hex[:24]}"
                messages.append(self._assistant_tool_call_message(response, call_id))
                messages.append(
                    self._tool_result_message(
                        call_id, tool_name, f"Error: invalid arguments: {exc}"
                    )
                )
                continue

            # EXECUTE
            step_start = time.monotonic()
            try:
                result = skill_fn(self.config.skill_context, **validated_args.model_dump())
            except (SkillValidationError, sqlite3.Error) as exc:
                return AgentAnswer(
                    text=f"Skill {tool_name!r} failed: {exc}",
                    refused_by="skill_execution_error",
                )
            step_duration_ms = int((time.monotonic() - step_start) * 1000)

            # OBSERVE
            lead_ids_seen_this_call.update(
                row["IDPROSPECTO"] for row in result.rows if "IDPROSPECTO" in row
            )
            step_number += 1
            if trace_state is not None:
                trace_state.steps.append(
                    {
                        "step": step_number,
                        "skill": tool_name,
                        "args": validated_args.model_dump(),
                        "result_summary": f"{len(result.rows)} row(s)",
                        "duration_ms": step_duration_ms,
                    }
                )

            last_citation = result.citation
            call_id = f"call_{uuid.uuid4().hex[:24]}"
            messages.append(self._assistant_tool_call_message(response, call_id))
            messages.append(
                self._tool_result_message(
                    call_id, tool_name, self._render_result(result)
                )
            )
            # Loop back to REASON.

        return AgentAnswer(
            text=(
                f"Reached the maximum of {self.config.max_steps} steps "
                "without producing an answer."
            ),
            refused_by="max_steps_exceeded",
        )

    # -- REASON ------------------------------------------------------------

    def _reason(
        self, messages: list[dict], trace_state: _TraceState | None = None
    ) -> GatewayResponse | None:
        """Call the gateway, retrying transient failures with backoff.

        Returns `None` once `MAX_TRANSIENT_RETRIES` retries are exhausted.
        """

        attempt = 0
        while True:
            try:
                return self.config.gateway.complete(messages, TOOLS_SCHEMA)
            except TransientGatewayError as exc:
                attempt += 1
                if trace_state is not None:
                    trace_state.retries.append(
                        {
                            "kind": "transient_gateway_error",
                            "attempt": attempt,
                            "detail": str(exc),
                        }
                    )
                if attempt > MAX_TRANSIENT_RETRIES:
                    return None
                self._sleep(self._backoff(attempt))

    # -- ANSWER --------------------------------------------------------

    def _answer(self, text: str, citation: ThresholdCitation | None) -> AgentAnswer:
        """Build the terminal `AgentAnswer`, embedding the last skill call's
        citation verbatim so it can never be paraphrased or dropped.

        This does NOT apply `enforce_comment_guardrail` -- that is applied
        exactly once, centrally, by `ask()` (tasks 5.3/5.4), so every
        return path (this happy path and every Phase-4 failure/refusal
        path) is guarded uniformly with no bypass."""

        final_text = text
        if citation is not None and citation.render() not in final_text:
            final_text = f"{final_text}\n\n{citation.render()}"

        return AgentAnswer(text=final_text, citation=citation)

    # -- Phase 5: vocabulary / lead-id catalog loading ------------------

    def _load_vocabulary(self) -> tuple[str, ...]:
        """Load the comment-category vocabulary once, at construction time,
        via the `catalogo_categorias_comentario` skill (tasks 5.3/5.4).

        Fails open (empty vocabulary) on a database error rather than
        raising out of `Harness.__init__`: a construction-time catalog load
        is a separate concern from a per-call skill execution error, which
        the harness already surfaces normally through `ask()`'s existing
        `skill_execution_error` path when the model's chosen skill actually
        needs the database. An empty vocabulary makes the guardrail's
        term-matching checks a no-op rather than crashing construction."""

        try:
            result = catalogo_categorias_comentario(self.config.skill_context)
        except sqlite3.Error:
            return ()
        return tuple(row["categoria_comentario"] for row in result.rows)

    def _load_all_lead_ids(self) -> frozenset[int]:
        """Load the full universe of valid lead ids once, at construction
        time, via `listar_leads_priorizados` (tasks 5.3/5.4).

        This is intentionally broader than "ids touched by skill calls
        during a given `ask()` call": the highest-priority gap this PR
        closes is the model answering a forbidden lead+comment question
        purely from its own knowledge, with NO tool call at all -- in that
        scenario no `SkillResult` is ever produced, so a per-call-only id
        set would never contain the id the model fabricated a comment
        combination for. Using the full known lead population instead lets
        `enforce_comment_guardrail` catch that case too. Fails open (empty
        set) on a database error, matching `_load_vocabulary`."""

        try:
            result = listar_leads_priorizados(self.config.skill_context, limit=_ALL_LEADS_LIMIT)
        except sqlite3.Error:
            return frozenset()
        return frozenset(row["IDPROSPECTO"] for row in result.rows)

    # -- Phase 5: trace writing ------------------------------------------

    def _write_trace(
        self,
        question: str,
        answer: AgentAnswer,
        trace_state: _TraceState,
        call_start: float,
    ) -> None:
        """Write the complete run record exactly once, at the end of
        `ask()`, regardless of outcome (tasks 5.6/5.7)."""

        duration_ms = int((time.monotonic() - call_start) * 1000)
        if answer.refused_by is None:
            outcome = "answered"
        elif answer.refused_by in _REFUSAL_KINDS:
            outcome = "refused"
        else:
            outcome = "failed"

        gateway = self.config.gateway
        run_record = {
            "gateway": type(gateway).__name__,
            "model": getattr(gateway, "model", "unknown"),
            "steps": len(trace_state.steps),
            "outcome": outcome,
            "duration_ms": duration_ms,
            "question": question,
            "final_answer_text": answer.text,
            "step_records": trace_state.steps,
            "retries": trace_state.retries,
        }
        self.config.trace_writer.write(run_record)

    # -- helpers -------------------------------------------------------

    def _is_forbidden_intent(self, tool_name: str, tool_args: dict | None) -> bool:
        haystack = tool_name.lower()
        if tool_args:
            haystack += " " + " ".join(str(key).lower() for key in tool_args)
            haystack += " " + " ".join(str(value).lower() for value in tool_args.values())
        return any(keyword in haystack for keyword in FORBIDDEN_INTENT_KEYWORDS)

    def _assistant_tool_call_message(self, response: GatewayResponse, call_id: str) -> dict:
        # OpenAI-compatible shape: tool_calls entries wrap {"type": "function",
        # "function": {...}} with an id, and "arguments" is a JSON *string*
        # (not a dict) -- a real Ollama server rejects the flat, dict-arguments
        # shape with a 400 "invalid tool call arguments" error on the very
        # next turn. Only found via a live smoke test; FakeGateway-based unit
        # tests never round-trip this message back through a real provider.
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": response.tool_name,
                        "arguments": json.dumps(response.tool_args or {}),
                    },
                }
            ],
        }

    def _tool_result_message(self, call_id: str, tool_name: str, content: str) -> dict:
        # tool_call_id must match the id on the preceding assistant
        # tool_calls entry -- required by the OpenAI-compatible spec so the
        # provider can pair a tool result back to its originating call.
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": content,
        }

    def _render_result(self, result: SkillResult) -> str:
        payload: dict = {"skill": result.skill, "rows": result.rows}
        if result.citation is not None:
            payload["citation"] = result.citation.render()
        return json.dumps(payload, default=str)
