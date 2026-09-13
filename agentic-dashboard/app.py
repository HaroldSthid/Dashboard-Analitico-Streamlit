"""Streamlit UI entry point for the agentic dashboard (Phase 6 + PR7).

Thin UI only: wires `Harness` (agent_harness.py) together with
`build_gateway()` (gateways.py), `SkillContext` (skills.py), and
`TraceWriter` (trace.py) into a chat-style Streamlit page. No business
logic, no direct database access, and no backend selector live here --
every chat answer is produced exclusively through `Harness.ask()`, and the
configured backend is read once, invisibly, inside `build_gateway()`. See
tasks 6.1-6.4 in `sdd/agentic-dashboard/tasks`.

PR7 adds a PERSISTENT dashboard panel (KPI metrics, a ranked-leads table,
and a chart) rendered directly from public `skills.py` functions -- never
through the harness/LLM -- so the dashboard has a default, always-visible
view on page load, exactly like the chat interface already does. This
mirrors how `reference-solution/app.py` calls its logic/interpretation
modules directly rather than through an agent: it stays legitimate because
the actual business-rule computation still lives entirely in `skills.py`;
this panel only calls public skill functions and renders the
`SkillResult.rows` they already return.

`test_app_boundary.py` enforces this contract statically (import allowlist,
no direct database driver import, no business-logic tokens, no
backend-selector widget). `test_app_panel_data.py` unit-tests the panel's
data-loading function directly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from agent_harness import AgentAnswer, AgentConfig, Harness
from gateways import build_gateway
from skills import SkillContext, listar_leads_priorizados, resumen_por_cluster
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

# Re-queried at most once per minute: the persistent panel's underlying
# data only changes when the database file itself changes, and a 60s TTL
# keeps a chat rerun from re-querying the database on every keystroke
# while still refreshing soon after any upstream data update.
_PANEL_CACHE_TTL_SECONDS = 60


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


@st.cache_data(ttl=_PANEL_CACHE_TTL_SECONDS)
def _load_panel_data(db_path: str) -> dict:
    """Fetch the persistent panel's KPI, table, and chart data.

    Calls public skill functions directly (no LLM/Harness involved) and
    returns only their already-computed rows -- this function never
    recomputes a business threshold or a priority tier itself; it only
    reads what the skill layer already produced.
    """

    ctx = SkillContext(db_path=db_path)

    grouped_rows = resumen_por_cluster(ctx).rows
    # The skill's own reported per-group counts are summed to get the true
    # population size -- never a guessed or hardcoded number.
    population_size = sum(row["cantidad_leads"] for row in grouped_rows)

    table_rows = listar_leads_priorizados(ctx).rows
    # Tier-specific counts must reflect the whole population, not the
    # table's own default page size, so each tier is queried with an
    # explicit limit derived from the population size above.
    high_tier_rows = listar_leads_priorizados(ctx, tier="Alto", limit=population_size).rows
    mid_tier_rows = listar_leads_priorizados(ctx, tier="Medio", limit=population_size).rows

    return {
        "total_leads": population_size,
        "high_tier_count": len(high_tier_rows),
        "mid_tier_count": len(mid_tier_rows),
        "table_rows": table_rows,
        "grouped_rows": grouped_rows,
    }


def _render_dashboard_panel() -> None:
    """Render the persistent KPI + table + chart panel above the chat.

    Every displayed value comes straight from `_load_panel_data()`'s
    already-computed output -- no threshold, tier, or ranking logic is
    evaluated in this file.
    """

    data = _load_panel_data(str(DB_PATH))

    col1, col2, col3 = st.columns(3)
    col1.metric("Leads totales", data["total_leads"])
    col2.metric("Tier Alto", data["high_tier_count"])
    col3.metric("Tier Medio", data["mid_tier_count"])

    st.subheader("Priority Leads")
    st.caption(f"Top {len(data['table_rows'])} leads by contact priority.")
    st.dataframe(data["table_rows"], use_container_width=True)

    st.subheader("Lead Distribution")
    grouped_df = pd.DataFrame(data["grouped_rows"])
    if not grouped_df.empty:
        group_col, count_col = grouped_df.columns[0], grouped_df.columns[1]
        fig = px.bar(grouped_df, x=group_col, y=count_col, title="Leads by Segment")
        st.plotly_chart(fig, use_container_width=True)


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
    st.set_page_config(page_title="Agentic Lead Dashboard", layout="wide")
    st.title("Agentic Lead Dashboard")

    _render_dashboard_panel()
    st.divider()
    st.subheader("Chat")

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
