"""Agent harness: the REASON -> SELECT -> EXECUTE -> OBSERVE -> ANSWER core
loop, plus a differentiated retry policy per error class.

Phase 4 scope only: `AgentConfig`, `AgentAnswer`, `Harness`, and
`TransientGatewayError`. No tracing and no UI — those are later PRs
(`trace.py` is PR5, `app.py` is PR6). See tasks 4.1-4.12 in
`sdd/agentic-dashboard/tasks`.

`enforce_comment_guardrail` (the post-generation answer validator) is
explicitly PR5 scope, per the design v2 correction: the earlier
"no-tool-call forbidden question -> guarded refusal" task (4.13/4.14) is
superseded by that dedicated validator, which needs vocabulary/lead-id data
the harness calls into skills for. It is intentionally NOT implemented
here — see the `# TODO(PR5)` marker in `Harness._answer`. The only
forbidden-intent handling implemented in this file is the hallucinated
tool-call keyword guard below (still Phase-4 scope, tasks 4.7/4.8).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import ValidationError

from gateways import GatewayResponse, ModelGateway
from skills import (
    SKILLS,
    TOOLS_SCHEMA,
    SkillContext,
    SkillResult,
    SkillValidationError,
    ThresholdCitation,
)

# `_SKILL_ARGS_MODELS` is a module-private mapping in `skills.py` (skill name
# -> its Pydantic args model). There is no public accessor for it and
# `skills.py` is a closed Phase-1/2 file the harness must not modify, so it
# is imported directly here under its real name for clarity at the call
# site. This is a read, never a mutation, of that module.
from skills import _SKILL_ARGS_MODELS as SKILL_ARGS_MODELS

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


class Harness:
    """Runs the REASON -> SELECT -> EXECUTE -> OBSERVE -> ANSWER loop for a
    single `AgentConfig`, applying a differentiated retry policy per error
    class encountered along the way."""

    def __init__(
        self,
        config: AgentConfig,
        sleep: Callable[[float], None] | None = None,
        backoff: Callable[[int], float] = _default_backoff,
    ) -> None:
        self.config = config
        self._sleep = sleep if sleep is not None else (lambda _seconds: None)
        self._backoff = backoff

    def ask(self, question: str) -> AgentAnswer:
        messages: list[dict] = [{"role": "user", "content": question}]
        last_citation: ThresholdCitation | None = None
        args_retries = 0
        unknown_tool_retries = 0

        for _step in range(self.config.max_steps):
            response = self._reason(messages)
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
                if unknown_tool_retries > MAX_UNKNOWN_TOOL_RETRIES:
                    return AgentAnswer(
                        text=(
                            f"The tool {tool_name!r} does not exist and no valid "
                            "tool call followed the correction."
                        ),
                        refused_by="unknown_tool",
                    )

                messages.append(self._assistant_tool_call_message(response))
                messages.append(
                    self._tool_result_message(
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
                if args_retries > MAX_ARGS_VALIDATION_RETRIES:
                    return AgentAnswer(
                        text=f"Invalid arguments for tool {tool_name!r}: {exc}",
                        refused_by="invalid_args",
                    )

                messages.append(self._assistant_tool_call_message(response))
                messages.append(
                    self._tool_result_message(
                        tool_name, f"Error: invalid arguments: {exc}"
                    )
                )
                continue

            # EXECUTE
            try:
                result = skill_fn(self.config.skill_context, **validated_args.model_dump())
            except (SkillValidationError, sqlite3.Error) as exc:
                return AgentAnswer(
                    text=f"Skill {tool_name!r} failed: {exc}",
                    refused_by="skill_execution_error",
                )

            # OBSERVE
            last_citation = result.citation
            messages.append(self._assistant_tool_call_message(response))
            messages.append(
                self._tool_result_message(tool_name, self._render_result(result))
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

    def _reason(self, messages: list[dict]) -> GatewayResponse | None:
        """Call the gateway, retrying transient failures with backoff.

        Returns `None` once `MAX_TRANSIENT_RETRIES` retries are exhausted.
        """

        attempt = 0
        while True:
            try:
                return self.config.gateway.complete(messages, TOOLS_SCHEMA)
            except TransientGatewayError:
                attempt += 1
                if attempt > MAX_TRANSIENT_RETRIES:
                    return None
                self._sleep(self._backoff(attempt))

    # -- ANSWER --------------------------------------------------------

    def _answer(self, text: str, citation: ThresholdCitation | None) -> AgentAnswer:
        """Build the terminal `AgentAnswer`, embedding the last skill call's
        citation verbatim so it can never be paraphrased or dropped."""

        final_text = text
        if citation is not None and citation.render() not in final_text:
            final_text = f"{final_text}\n\n{citation.render()}"

        # TODO(PR5): enforce_comment_guardrail wraps every terminal answer here
        return AgentAnswer(text=final_text, citation=citation)

    # -- helpers -------------------------------------------------------

    def _is_forbidden_intent(self, tool_name: str, tool_args: dict | None) -> bool:
        haystack = tool_name.lower()
        if tool_args:
            haystack += " " + " ".join(str(key).lower() for key in tool_args)
            haystack += " " + " ".join(str(value).lower() for value in tool_args.values())
        return any(keyword in haystack for keyword in FORBIDDEN_INTENT_KEYWORDS)

    def _assistant_tool_call_message(self, response: GatewayResponse) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"name": response.tool_name, "arguments": response.tool_args}
            ],
        }

    def _tool_result_message(self, tool_name: str, content: str) -> dict:
        return {"role": "tool", "name": tool_name, "content": content}

    def _render_result(self, result: SkillResult) -> str:
        payload: dict = {"skill": result.skill, "rows": result.rows}
        if result.citation is not None:
            payload["citation"] = result.citation.render()
        return json.dumps(payload, default=str)
