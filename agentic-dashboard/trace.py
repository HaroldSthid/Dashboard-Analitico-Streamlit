"""Markdown trace writer for agent harness runs (Phase 5).

Phase 5 scope only: `TraceWriter`. Writes one markdown file per
`Harness.ask()` call to `agentic-dashboard/traces/{YYYY-MM-DD}/{run_id}.md`,
wired into `Harness` via the optional `AgentConfig.trace_writer` field
(tasks 5.5-5.7 in `sdd/agentic-dashboard/tasks`). Content is technical /
developer-facing only: tool names, arguments, row counts, and timing — never
raw comment text or other PII, since the harness never fetches per-lead
comment content in the first place (see `guardrail.py`).

`TraceWriter.write()` accepts a `run_record` dict shaped as follows (see
`agent_harness.Harness.ask()` for the producer side):

    {
        "run_id": str | None,        # generated if omitted/None
        "gateway": str,               # e.g. "OllamaGateway"
        "model": str,                 # e.g. "qwen2.5:7b"
        "steps": int,                 # number of tool-call steps taken
        "outcome": str,                # "answered" | "refused" | "failed"
        "duration_ms": int,
        "question": str,
        "final_answer_text": str,     # optional
        "step_records": list[dict],   # see below, optional (default [])
        "retries": list[dict],        # see below, optional (default [])
    }

Each `step_records` entry:
    {"step": int, "skill": str, "args": dict, "result_summary": str, "duration_ms": int}

Each `retries` entry:
    {"kind": str, "attempt": int, "detail": str}
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TRACES_DIR = Path(__file__).resolve().parent / "traces"

_RUN_ID_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits
_RUN_ID_SUFFIX_LENGTH = 6


def _generate_run_id(now: datetime) -> str:
    """`{YYYYMMDDTHHMMSSZ}-{6-char random suffix}`, e.g. `20260913T142233Z-a1b2c3`."""

    suffix = "".join(random.choices(_RUN_ID_SUFFIX_ALPHABET, k=_RUN_ID_SUFFIX_LENGTH))
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{suffix}"


class TraceWriter:
    """Writes one markdown trace file per agent run.

    `traces_dir` defaults to `agentic-dashboard/traces/`; tests should pass
    a `tmp_path` fixture to avoid polluting the real traces directory.
    """

    def __init__(self, traces_dir: Path | str | None = None) -> None:
        self._traces_dir = Path(traces_dir) if traces_dir is not None else DEFAULT_TRACES_DIR

    def write(self, run_record: dict) -> Path:
        """Render `run_record` to markdown and write it to
        `{traces_dir}/{YYYY-MM-DD}/{run_id}.md`, returning the written path."""

        now = datetime.now(timezone.utc)
        run_id = run_record.get("run_id") or _generate_run_id(now)
        day_dir = self._traces_dir / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        path = day_dir / f"{run_id}.md"
        path.write_text(self._render(run_id, run_record), encoding="utf-8")
        return path

    def _render(self, run_id: str, run_record: dict) -> str:
        frontmatter = (
            "---\n"
            "type: agent-run\n"
            f"run_id: {run_id}\n"
            f"gateway: {run_record.get('gateway', 'unknown')}\n"
            f"model: {run_record.get('model', 'unknown')}\n"
            f"steps: {run_record.get('steps', 0)}\n"
            f"outcome: {run_record.get('outcome', 'unknown')}\n"
            f"duration_ms: {run_record.get('duration_ms', 0)}\n"
            "---\n"
        )

        lines = [
            frontmatter,
            "Orchestrator:: [[Orchestrator/agentic-dashboard]]",
            "Agent:: [[Agent/LeadHarness]]",
            "",
            f"**Question:** {run_record.get('question', '')}",
            "",
        ]

        for step in run_record.get("step_records", []):
            skill_name = step.get("skill", "unknown")
            lines.append(f"## Step {step.get('step')} — [[Skill/{skill_name}]]")
            lines.append(f"- Args: `{step.get('args')}`")
            lines.append(f"- Result: {step.get('result_summary')}")
            lines.append(f"- Duration: {step.get('duration_ms')} ms")
            lines.append("")

        lines.append("## Retries")
        retries = run_record.get("retries") or []
        if retries:
            for retry in retries:
                lines.append(
                    f"- {retry.get('kind')} (attempt {retry.get('attempt')}): "
                    f"{retry.get('detail')}"
                )
        else:
            lines.append("- None")
        lines.append("")

        final_text = run_record.get("final_answer_text")
        if final_text:
            lines.append("## Final Answer")
            lines.append(final_text)
            lines.append("")

        return "\n".join(lines)
