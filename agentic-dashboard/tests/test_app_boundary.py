"""Static boundary tests for `app.py` (Phase 6, tasks 6.1-6.4).

`app.py` is the Streamlit UI entry point wiring `Harness` (agent_harness.py),
`build_gateway()` (gateways.py), `SkillContext` (skills.py), and
`TraceWriter` (trace.py) together into a thin chat UI. These tests never
import or execute `app.py` -- doing so would require Streamlit's script
runner. Instead they parse its source with `ast` and assert its import
surface and business-logic boundary statically, which is exactly what a UI
layer's contract needs to prove: it wires the harness, it does not reimplement
or bypass it.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

# Plain `import x` modules app.py is allowed to use. `plotly.express` is
# required as of PR7: the persistent dashboard panel renders a bar chart
# of `resumen_por_cluster()` output via `st.plotly_chart`, mirroring
# `reference-solution/app.py`'s own `plotly.express` usage -- see
# `test_app_imports_plotly_express` below.
ALLOWED_IMPORT_MODULES = {
    "streamlit",
    "pandas",
    "plotly.express",
}

# `from <module> import <names>` app.py is allowed to use. `skills` gained
# two names in PR7: the persistent dashboard panel calls
# `listar_leads_priorizados` / `resumen_por_cluster` directly (not through
# the harness) to render a default view on page load. This is legitimate
# per the same boundary this file enforces: the actual business-rule
# computation stays entirely inside skills.py; app.py only calls its
# public functions and renders the rows they already return.
ALLOWED_IMPORT_FROM = {
    "__future__": {"annotations"},
    "pathlib": {"Path"},
    "agent_harness": {"Harness", "AgentConfig", "AgentAnswer"},
    "gateways": {"build_gateway"},
    "skills": {"SkillContext", "listar_leads_priorizados", "resumen_por_cluster"},
    "trace": {"TraceWriter"},
}

# Business-logic tokens that must never appear in app.py's raw source.
# Thresholds, tier/order business fields, and business functions all live in
# skills.py / agent_harness.py; the UI layer must only ever call
# `Harness.ask()` and render the resulting `AgentAnswer`.
FORBIDDEN_SOURCE_TOKENS = (
    "UMBRAL_",
    "umbral_alto",
    "umbral_medio",
    "tier_prioridad",
    "orden_contacto",
    "banda_probabilidad",
    "cluster_alta_conversion",
    "tolerancia_empate",
    "Probabilidad_Compra",
    "Cluster",
    "sqlite3",
)

# Backend identifiers that must never appear as selectable widget option
# strings: there is no backend selector in this UI. `AGENT_LLM_BACKEND` is
# read exactly once, invisibly, inside `build_gateway()`.
FORBIDDEN_BACKEND_OPTION_TOKENS = ("openrouter", "ollama")


def _read_source() -> str:
    assert APP_PATH.exists(), f"{APP_PATH} does not exist"
    return APP_PATH.read_text(encoding="utf-8")


def _parse() -> ast.Module:
    return ast.parse(_read_source(), filename=str(APP_PATH))


def test_app_imports_are_allowlisted():
    tree = _parse()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in ALLOWED_IMPORT_MODULES, (
                    f"app.py imports disallowed module {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            allowed_names = ALLOWED_IMPORT_FROM.get(module)
            assert allowed_names is not None, (
                f"app.py imports from disallowed module {module!r}"
            )
            for alias in node.names:
                assert alias.name in allowed_names, (
                    f"app.py imports disallowed name {alias.name!r} from {module!r}"
                )


def test_app_never_imports_sqlite3():
    tree = _parse()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name == "sqlite3" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "sqlite3"


def test_app_source_has_no_business_logic_tokens():
    source = _read_source()
    for token in FORBIDDEN_SOURCE_TOKENS:
        assert token not in source, (
            f"app.py source contains business-logic token {token!r}; business "
            "rules must live in skills.py/agent_harness.py, never in the UI layer"
        )


def test_app_has_no_backend_selector_widget():
    source = _read_source().lower()
    for token in FORBIDDEN_BACKEND_OPTION_TOKENS:
        assert token not in source, (
            f"app.py source contains backend-selector token {token!r}; "
            "AGENT_LLM_BACKEND must be read only inside build_gateway(), "
            "never exposed via a UI widget"
        )


def test_app_calls_harness_ask():
    """The only way app.py may produce an answer is `Harness.ask(...)`."""

    source = _read_source()
    assert ".ask(" in source, "app.py must drive the conversation through Harness.ask()"


def test_app_imports_plotly_express():
    """PR7: the persistent dashboard panel's chart requires `plotly.express`
    to actually be imported, not merely tolerated by the allowlist."""

    tree = _parse()
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "plotly.express" in imported, (
        "app.py must import plotly.express for the persistent dashboard panel's chart"
    )
