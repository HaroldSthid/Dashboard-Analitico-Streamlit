"""Streamlit UI entry point for the agentic dashboard (Phase 6 + PR7 + PR8).

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

PR8 enriches that panel (UI/UX inspired by another student's reference
dashboard -- never its code, only its layout ideas): human-readable
`interpretar_cluster` labels, KPI deltas, sidebar filters
(tier/cluster/hobby/exact IDPROSPECTO), and a second chart tab for
`banda_probabilidad` bands. The filters fetch the FULL ranked lead
population via `listar_leads_priorizados()` exactly ONCE (the same
population-size-derivation trick PR7 already used to defeat the
`limit=50` default), then apply all four filters as a pure, in-memory,
AND-combined filter over those already-skill-computed rows
(`_apply_filters`, unit-tested directly in `test_app_filters.py`) --
never a skill call per filter combination, and never a re-ranking of the
filtered subset. KPIs and both chart tabs are then recomputed from that
filtered subset, never from the original unfiltered fetch.

Deliberate boundary-test revision (full reasoning lives in
`test_app_boundary.py`'s module docstring): building the filter widgets
and the second chart tab requires referencing already-computed field
names (`Cluster`, `Probabilidad_Compra`, `IDPROSPECTO`,
`Hobbies_Estandar`, `tier_prioridad`) as dict/DataFrame keys, and requires
importing and calling the already-ported `banda_probabilidad()` skill
function directly (the same legitimate "call the skill, render its
output" pattern PR7 already established). None of that is business-rule
re-implementation -- the actual threshold comparisons still live
exclusively in `skills.py`. What remains, and stays fully forbidden, is
app.py ever defining its own copy of a threshold constant or writing its
own `>=`/`<` comparison chain against a hardcoded threshold value; see
`test_app_never_hardcodes_threshold_comparisons` for the AST-based
guardrail that replaced the old blunt token ban.

`test_app_boundary.py` enforces the overall contract statically (import
allowlist, no direct database driver import, no business-logic constants,
no hardcoded threshold comparisons, no backend-selector widget).
`test_app_panel_data.py` and `test_app_filters.py` unit-test the panel's
pure data-loading and filtering/aggregation functions directly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from agent_harness import AgentAnswer, AgentConfig, Harness
from gateways import build_gateway
from skills import (
    SkillContext,
    banda_probabilidad,
    catalogo_hobbies,
    interpretar_cluster,
    listar_leads_priorizados,
    resumen_por_cluster,
)
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

# Sentinel hobby-selectbox option meaning "no hobby restriction", matching
# `reference-solution/app.py`'s own `hobby_sel == "(todos)"` UX convention.
_HOBBY_ALL_OPTION = "Todos"

# Fixed tier vocabulary for the sidebar multiselect's option/default list.
# Not a business threshold -- `tier_prioridad()` already guarantees every
# row's `tier_prioridad` is one of exactly these three strings; this is the
# same kind of literal label PR7 already used for `col2.metric("Tier Alto", ...)`.
_ALL_TIERS = ("Alto", "Medio", "Bajo")


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
    """Fetch the FULL ranked lead population and hobby vocabulary once.

    Calls public skill functions directly (no LLM/Harness involved) and
    returns only their already-computed rows -- this function never
    recomputes a business threshold or a priority tier itself; it only
    reads what the skill layer already produced.

    KPI counts are NOT computed here (PR8 change from PR7): they now
    depend on the sidebar's filter state, which is only known at render
    time, so `_render_dashboard_panel()` recomputes them from the
    filtered subset of `all_rows` via `_apply_filters()`.
    """

    ctx = SkillContext(db_path=db_path)

    grouped_rows = resumen_por_cluster(ctx).rows
    # The skill's own reported per-group counts are summed to get the true
    # population size -- never a guessed or hardcoded number.
    population_size = sum(row["cantidad_leads"] for row in grouped_rows)

    # Full ranked population (not the default limit=50): every filter
    # combination below must be able to select from the whole dataset.
    all_rows = listar_leads_priorizados(ctx, limit=population_size).rows

    hobby_options = sorted(row["hobby_estandar"] for row in catalogo_hobbies(ctx).rows)

    return {
        "population_size": population_size,
        "all_rows": all_rows,
        "hobby_options": hobby_options,
    }


def _apply_filters(
    rows: list[dict],
    tiers,
    clusters,
    hobby: str,
    idprospecto: int,
) -> list[dict]:
    """Filter already-ranked lead rows in-memory (AND across all four filters).

    Pure presentation-layer filtering over rows the skill layer already
    computed and ranked -- mirrors `reference-solution/app.py`'s own
    `df_filtrado = df_leads if hobby_sel == "(todos)" else df_leads[...]`
    pattern. Never issues a new query, never calls the skill layer once
    per filter combination, and never re-ranks the filtered subset:
    `orden_contacto` values are preserved exactly as `_load_panel_data()`
    computed them over the full population, identically to how
    `listar_leads_priorizados()` itself filters its own hobby/tier
    arguments after ranking.

    `tiers`/`clusters` restrict via plain membership (an empty container
    yields no rows). `hobby == _HOBBY_ALL_OPTION` and `idprospecto == 0`
    both mean "no restriction", matching the reference dashboard's own UX
    convention.
    """

    filtered = [
        row for row in rows if row["tier_prioridad"] in tiers and row["Cluster"] in clusters
    ]
    if hobby != _HOBBY_ALL_OPTION:
        filtered = [row for row in filtered if row["Hobbies_Estandar"] == hobby]
    if idprospecto:
        filtered = [row for row in filtered if row["IDPROSPECTO"] == idprospecto]
    return filtered


def _delta_pct(part: int, whole: int) -> str:
    """Format `part` as a percentage of `whole`, for an `st.metric` delta.

    Pure presentation arithmetic over counts the panel already computed --
    never a business threshold. Guards against division by zero (e.g.
    every lead filtered out) by returning `"0.0%"`.
    """

    if whole == 0:
        return "0.0%"
    return f"{part / whole:.1%}"


def _render_sidebar_filters(ctx: SkillContext, data: dict) -> tuple[list, list, str, int]:
    """Render the sidebar filter widgets and return the selected filter state.

    Widget placement itself is UI rendering (see module docstring) and is
    covered by the manual `AppTest` smoke test, not a plain unit test --
    only the resulting `_apply_filters()` call is meaningfully testable
    without a live Streamlit script run (see `test_app_filters.py`).
    """

    st.sidebar.header("Filtros")

    available_clusters = sorted({row["Cluster"] for row in data["all_rows"]})

    selected_tiers = st.sidebar.multiselect(
        "Tier de prioridad", options=list(_ALL_TIERS), default=list(_ALL_TIERS)
    )
    selected_clusters = st.sidebar.multiselect(
        "Cluster",
        options=available_clusters,
        default=available_clusters,
        format_func=lambda cluster: (
            f"{cluster} - {interpretar_cluster(ctx, cluster=cluster).rows[0]['label']}"
        ),
    )
    selected_hobby = st.sidebar.selectbox(
        "Hobby", options=[_HOBBY_ALL_OPTION] + data["hobby_options"]
    )
    selected_idprospecto = st.sidebar.number_input(
        "ID Prospecto (0 = todos)", min_value=0, value=0, step=1
    )

    return selected_tiers, selected_clusters, selected_hobby, int(selected_idprospecto)


def _render_dashboard_panel() -> None:
    """Render the persistent KPI + filters + table + chart-tabs panel above
    the chat.

    Every displayed value comes straight from `_load_panel_data()`'s
    already-computed output, filtered in-memory via `_apply_filters()` --
    no threshold, tier, or ranking logic is evaluated in this file.
    """

    ctx = SkillContext(db_path=str(DB_PATH))
    data = _load_panel_data(str(DB_PATH))

    selected_tiers, selected_clusters, selected_hobby, selected_idprospecto = (
        _render_sidebar_filters(ctx, data)
    )

    filtered_rows = _apply_filters(
        data["all_rows"], selected_tiers, selected_clusters, selected_hobby, selected_idprospecto
    )
    filtered_df = pd.DataFrame(filtered_rows) if filtered_rows else pd.DataFrame()

    total_leads = len(filtered_rows)
    high_tier_count = sum(1 for row in filtered_rows if row["tier_prioridad"] == "Alto")
    mid_tier_count = sum(1 for row in filtered_rows if row["tier_prioridad"] == "Medio")

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Leads totales", total_leads, delta=_delta_pct(total_leads, data["population_size"])
    )
    col2.metric("Tier Alto", high_tier_count, delta=_delta_pct(high_tier_count, total_leads))
    col3.metric("Tier Medio", mid_tier_count, delta=_delta_pct(mid_tier_count, total_leads))

    st.subheader("Priority Leads")
    st.caption(
        f"Showing {total_leads} of {data['population_size']} total leads "
        "matching the current filters."
    )
    st.dataframe(filtered_rows, use_container_width=True)

    tab_cluster, tab_probabilidad = st.tabs(
        ["Distribución por Cluster", "Distribución de Probabilidad de Compra"]
    )

    with tab_cluster:
        if not filtered_df.empty:
            cluster_counts = filtered_df["Cluster"].value_counts().sort_index().reset_index()
            cluster_counts.columns = ["Cluster", "Leads"]
            cluster_counts["Perfil"] = cluster_counts["Cluster"].apply(
                lambda cluster: interpretar_cluster(ctx, cluster=cluster).rows[0]["label"]
            )
            fig_cluster = px.bar(cluster_counts, x="Perfil", y="Leads", title="Leads by Cluster")
            st.plotly_chart(fig_cluster, use_container_width=True)
        else:
            st.info("No leads match the current filters.")

    with tab_probabilidad:
        if not filtered_df.empty:
            bands = filtered_df["Probabilidad_Compra"].apply(banda_probabilidad)
            band_counts = bands.value_counts().reset_index()
            band_counts.columns = ["Banda", "Leads"]
            fig_band = px.bar(
                band_counts, x="Banda", y="Leads", title="Leads by Probability Band"
            )
            st.plotly_chart(fig_band, use_container_width=True)
        else:
            st.info("No leads match the current filters.")


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
