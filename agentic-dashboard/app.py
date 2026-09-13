"""Streamlit UI entry point for the agentic dashboard (Phase 6).

Thin UI only: wires `Harness` (agent_harness.py) together with
`build_gateway()` (gateways.py), `SkillContext` (skills.py), and
`TraceWriter` (trace.py) into a chat-style Streamlit page. No business
logic, no direct database access, and no backend selector live here --
every question is answered exclusively through `Harness.ask()`, and the
configured backend is read once, invisibly, inside `build_gateway()`. See
tasks 6.1-6.4 in `sdd/agentic-dashboard/tasks`.

`test_app_boundary.py` enforces this contract statically (import allowlist,
no direct database driver import, no business-logic tokens, no
backend-selector widget).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from agent_harness import AgentAnswer, AgentConfig, Harness
from gateways import build_gateway
from skills import SkillContext
from trace import TraceWriter

# `app.py` is this repository's one fixed UI entry point, not a reusable
# skill. A skill must never guess its database location relative to
# `__file__` (see `skills.py::SkillContext`'s docstring) because a skill is
# business logic that must stay portable and receive `db_path` explicitly
# from its caller. This IS that caller: app.py's own location relative to
# `data/` is a stable structural fact of this repo's layout, not a business
# assumption, so resolving it here once -- and passing it explicitly into
# `SkillContext` below -- is what lets every skill downstream keep receiving
# an explicit `db_path` with no guessing of its own.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _REPO_ROOT / "data" / "db_dashboard_course.db"
TRACES_DIR = Path(__file__).resolve().parent / "traces"


@st.cache_resource
def get_harness() -> Harness:
    """Build the `Harness` once per Streamlit process and cache it.

    The backend is selected exclusively inside `build_gateway()` from the
    `AGENT_LLM_BACKEND` environment variable -- there is no backend
    selector widget anywhere in this UI.
    """

    config = AgentConfig(
        gateway=build_gateway(),
        skill_context=SkillContext(db_path=str(DB_PATH)),
        trace_writer=TraceWriter(traces_dir=TRACES_DIR),
    )
    return Harness(config)


def _render_answer(answer: AgentAnswer) -> None:
    """Render one `AgentAnswer` -- text, citation, tables, and chart --
    exactly as the harness produced it. No reinterpretation of its fields."""

    st.markdown(answer.text)

    if answer.citation is not None:
        st.caption(answer.citation.render())

    if answer.tables:
        st.dataframe(answer.tables)

    if answer.chart_spec:
        # No chart-spec producer exists yet anywhere in the harness/skills
        # layer (Phase 6 scope), so this is rendered generically rather than
        # assuming a specific plotly figure shape.
        st.json(answer.chart_spec)


def main() -> None:
    st.set_page_config(page_title="Agentic Lead Dashboard")
    st.title("Agentic Lead Dashboard")

    if "history" not in st.session_state:
        st.session_state.history = []

    for question, answer in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            _render_answer(answer)

    question = st.chat_input("Ask about lead priority, tiers, or hobbies...")
    if question:
        with st.chat_message("user"):
            st.markdown(question)

        harness = get_harness()
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = harness.ask(question)
            _render_answer(answer)

        st.session_state.history.append((question, answer))


if __name__ == "__main__":
    main()
