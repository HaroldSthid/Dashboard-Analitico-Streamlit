"""Unit tests for the Phase 5 markdown trace writer.

Phase 5 scope: `TraceWriter`. See tasks 5.5 in `sdd/agentic-dashboard/tasks`.
Wiring into `Harness` (tasks 5.6/5.7) is covered separately in
`test_harness.py`.
"""

from __future__ import annotations

import re

from trace import TraceWriter


def _sample_run_record(**overrides) -> dict:
    record = {
        "gateway": "OllamaGateway",
        "model": "qwen2.5:7b",
        "steps": 1,
        "outcome": "answered",
        "duration_ms": 42,
        "question": "Dame los leads de tier alto",
        "final_answer_text": "Aqui tienes los leads.",
        "step_records": [
            {
                "step": 1,
                "skill": "listar_leads_priorizados",
                "args": {"tier": "Alto"},
                "result_summary": "3 row(s)",
                "duration_ms": 12,
            }
        ],
        "retries": [],
    }
    record.update(overrides)
    return record


class TestTraceWriterWrite:
    def test_write_creates_file_and_returns_its_path(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())

        assert path.exists()
        assert path.suffix == ".md"

    def test_write_uses_date_and_run_id_directory_layout(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())

        assert path.parent.parent == tmp_path
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", path.parent.name)

    def test_write_generates_run_id_when_not_provided(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())

        assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{6}\.md$", path.name)

    def test_write_honors_explicit_run_id(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record(run_id="fixed-run-id"))

        assert path.name == "fixed-run-id.md"

    def test_frontmatter_fields_present(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record(run_id="run-1"))
        content = path.read_text(encoding="utf-8")

        assert "type: agent-run" in content
        assert "run_id: run-1" in content
        assert "gateway: OllamaGateway" in content
        assert "model: qwen2.5:7b" in content
        assert "steps: 1" in content
        assert "outcome: answered" in content
        assert "duration_ms: 42" in content

    def test_body_has_orchestrator_and_agent_wikilinks(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())
        content = path.read_text(encoding="utf-8")

        assert "Orchestrator:: [[Orchestrator/agentic-dashboard]]" in content
        assert "Agent:: [[Agent/LeadHarness]]" in content

    def test_body_has_question_text(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())
        content = path.read_text(encoding="utf-8")

        assert "Dame los leads de tier alto" in content

    def test_body_has_one_step_section_per_tool_call_with_skill_wikilink(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record())
        content = path.read_text(encoding="utf-8")

        assert "## Step 1 — [[Skill/listar_leads_priorizados]]" in content
        assert "tier" in content
        assert "3 row(s)" in content
        assert "12 ms" in content

    def test_body_has_retries_section_listing_attempts(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)
        record = _sample_run_record(
            retries=[
                {"kind": "invalid_args", "attempt": 1, "detail": "bad idprospecto"},
                {"kind": "unknown_tool", "attempt": 1, "detail": "tool does not exist"},
            ]
        )

        path = writer.write(record)
        content = path.read_text(encoding="utf-8")

        assert "## Retries" in content
        assert "invalid_args" in content
        assert "bad idprospecto" in content
        assert "unknown_tool" in content

    def test_body_has_empty_retries_section_when_no_retries(self, tmp_path):
        writer = TraceWriter(traces_dir=tmp_path)

        path = writer.write(_sample_run_record(retries=[]))
        content = path.read_text(encoding="utf-8")

        assert "## Retries" in content
        assert "None" in content

    def test_default_traces_dir_matches_package_layout(self):
        from pathlib import Path

        import trace as trace_module

        assert trace_module.DEFAULT_TRACES_DIR == Path(trace_module.__file__).resolve().parent / "traces"
