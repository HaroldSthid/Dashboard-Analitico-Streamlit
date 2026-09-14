"""Static boundary tests for `app.py` (Phase 6, tasks 6.1-6.4; PR7; PR8).

`app.py` is the Streamlit UI entry point wiring `Harness` (agent_harness.py),
`build_gateway()` (gateways.py), `SkillContext` (skills.py), and
`TraceWriter` (trace.py) together into a thin chat UI. These tests never
import or execute `app.py` -- doing so would require Streamlit's script
runner. Instead they parse its source with `ast` and assert its import
surface and business-logic boundary statically, which is exactly what a UI
layer's contract needs to prove: it wires the harness, it does not reimplement
or bypass it.

## PR8: deliberate revision of the business-logic boundary check

Through PR7, `FORBIDDEN_SOURCE_TOKENS` banned the literal substrings
`Cluster` and `Probabilidad_Compra` anywhere in `app.py`'s raw source. PR7
worked around this via positional column access (`df.columns[0]`) instead
of touching the list. PR8 needs sidebar filter widgets and a second chart
tab that reference `Cluster`, `Probabilidad_Compra`, `IDPROSPECTO`,
`Hobbies_Estandar`, and `tier_prioridad` directly as dict/DataFrame KEY
NAMES (e.g. `row["Cluster"] in selected_clusters`), and needs to import and
call the already-ported `banda_probabilidad()` skill function directly
(the same legitimate "call the skill, render its output" pattern PR7
already established for `listar_leads_priorizados`/`resumen_por_cluster`).
Continuing to dodge the old list via positional indexing would make PR8's
4x-larger filtering surface much harder to read and maintain.

This is a deliberate, documented boundary revision, not a shortcut:

- The ORIGINAL intent of the ban was to stop `app.py` from
  *recomputing business logic* -- re-deriving a tier from thresholds, or
  re-deriving a cluster's meaning from raw columns. It was never meant to
  forbid referencing already-computed field names for filtering, sorting,
  or display, nor to forbid calling an already-ported pure skill function
  directly (the exact PR7 precedent above).
- So PR8 splits the single token list in two:
    1. `ALLOWED_DATA_FIELD_TOKENS` -- pure column/field names a skill
       already computed and returned (`Cluster`, `Probabilidad_Compra`,
       `IDPROSPECTO`, `Hobbies_Estandar`, `tier_prioridad`,
       `orden_contacto`). These may now appear freely in `app.py`'s source
       as dict/DataFrame keys. This is an explicit, narrow allowlist, not a
       blanket removal of the guardrail.
    2. `FORBIDDEN_SOURCE_TOKENS` -- kept, unchanged in spirit, and still
       bans every literal threshold-constant NAME (`UMBRAL_`,
       `umbral_alto`, `umbral_medio`, `cluster_alta_conversion`,
       `tolerancia_empate`) and `sqlite3`. `app.py` must never define its
       own copy of a threshold or open a direct DB connection.
- What is still, and will always be, fully forbidden: `app.py` hardcoding
  one of the actual threshold NUMBERS (`0.70`, `0.30`, `2`, `0.01`) in a
  comparison against a Cluster/Probabilidad_Compra-shaped value -- i.e.
  re-implementing `tier_prioridad`/`orden_contacto`/`banda_probabilidad`'s
  own `>=`/`<` comparison chain instead of calling the real function. A
  bare token ban can no longer catch this (the field names it would have
  keyed off are now legitimately in scope), so
  `test_app_never_hardcodes_threshold_comparisons` below replaces it with
  an AST-based check: it walks every `ast.Compare` node in `app.py` and
  fails if a known threshold numeric literal is compared against anything
  whose name/key/attribute looks like a probability or cluster value. This
  stays a real, executable guardrail -- not a removed one -- for exactly
  the behavior the original list was written to prevent.

## PR9: threshold-reference-line chart needs `Thresholds` itself, not just its names

PR9 adds a probability histogram with vertical reference lines at the
`umbral_alto`/`umbral_medio` cut points (`fig.add_vline(x=..., ...)`), plus
an annotation label reading each cut's current value. Rendering that
requires importing the `Thresholds` dataclass from `skills.py` and
instantiating it once (`Thresholds()`, its own documented defaults) so
`app.py` reads `thresholds.umbral_alto` / `thresholds.umbral_medio` as
plain attribute access -- never redeclaring, re-deriving, or hardcoding
either value itself.

Through PR8, `FORBIDDEN_SOURCE_TOKENS` banned the raw substrings
`"umbral_alto"` and `"umbral_medio"` anywhere in `app.py`'s source. That
ban's ORIGINAL intent (same reasoning as PR8's own field-token split
above) was to stop `app.py` from declaring its OWN local threshold
constant (e.g. `umbral_alto = 0.70`) -- never to forbid reading the single
source of truth's own attribute names via `thresholds.umbral_alto`. Since
`thresholds.umbral_alto` necessarily contains the substring
`"umbral_alto"` in `app.py`'s raw source text, a blanket substring ban
cannot coexist with legitimate attribute access, so PR9 removes
`"umbral_alto"` / `"umbral_medio"` from `FORBIDDEN_SOURCE_TOKENS`. What
stays banned, unchanged: `"UMBRAL_"` (an uppercase local-constant naming
style), `"cluster_alta_conversion"`, `"tolerancia_empate"` (thresholds
`app.py` has no legitimate reason to reference), and `"sqlite3"`.

In exchange, PR9 adds two new, stronger guardrail tests:
`test_app_imports_thresholds_from_skills` (proves `Thresholds` really is
imported from `skills`, not locally redefined) and
`test_app_never_hardcodes_probability_threshold_literals` (a broader,
context-free AST sweep for the bare numeric literals `0.70`/`0.7`/
`0.30`/`0.3` ANYWHERE in `app.py`'s source -- not only inside an
`ast.Compare`, which is all `test_app_never_hardcodes_threshold_comparisons`
above checks. A hardcoded `fig.add_vline(x=0.70, ...)` is a `Call`
argument, not a `Compare`, so the existing PR8 check would miss it; this
new sweep does not).
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

# Plain `import x` modules app.py is allowed to use. `plotly.express` is
# required as of PR7: the persistent dashboard panel renders bar charts
# via `st.plotly_chart`, mirroring `reference-solution/app.py`'s own
# `plotly.express` usage -- see `test_app_imports_plotly_express` below.
ALLOWED_IMPORT_MODULES = {
    "streamlit",
    "pandas",
    "plotly.express",
}

# `from <module> import <names>` app.py is allowed to use. `skills` gained
# two names in PR7 (`listar_leads_priorizados`, `resumen_por_cluster`,
# called directly, not through the harness, to render a default view on
# page load) and three more in PR8 (`banda_probabilidad`, `catalogo_hobbies`,
# `interpretar_cluster`, for the sidebar filters and the second chart tab).
# This is legitimate per the same boundary this file enforces: the actual
# business-rule computation stays entirely inside skills.py; app.py only
# calls its public functions and renders the rows they already return.
ALLOWED_IMPORT_FROM = {
    "__future__": {"annotations"},
    "pathlib": {"Path"},
    "agent_harness": {"Harness", "AgentConfig", "AgentAnswer"},
    "gateways": {"build_gateway"},
    "skills": {
        "SkillContext",
        "listar_leads_priorizados",
        "resumen_por_cluster",
        "catalogo_hobbies",
        "interpretar_cluster",
        # PR9: catalogo_categorias_comentario is called directly for the
        # sidebar's dim_comentario catalog expander (same direct-skill-call
        # pattern as the other four names above). Thresholds is the single
        # source of truth for the histogram's reference-line x positions --
        # see the module docstring's PR9 section. `banda_probabilidad`
        # (PR8) is dropped here: PR9's tier-colored histogram replaces the
        # band-count chart that was its only caller, so app.py no longer
        # imports it.
        "catalogo_categorias_comentario",
        "Thresholds",
    },
    "trace": {"TraceWriter"},
}

# Pure, already-computed data field names -- column/dict keys a skill
# already returned. Referencing these in app.py for filtering, sorting, or
# display is presentation-layer plumbing, not a business-rule
# recomputation (see the PR8 section of the module docstring above), so
# they are explicitly EXEMPT from FORBIDDEN_SOURCE_TOKENS below.
ALLOWED_DATA_FIELD_TOKENS = (
    "Cluster",
    "Probabilidad_Compra",
    "IDPROSPECTO",
    "Hobbies_Estandar",
    "tier_prioridad",
    "orden_contacto",
)

# Business-threshold CONSTANT names (and their comparison-logic function
# names, where not already exempted above as legitimate direct skill
# calls) that must never appear in app.py's raw source. Actual thresholds
# live exclusively in skills.py; the UI layer must only ever call a public
# skill function (or `Harness.ask()`) and render its output.
#
# PR9: "umbral_alto" / "umbral_medio" are deliberately NOT in this list --
# see the module docstring's PR9 section. `app.py` now legitimately reads
# `thresholds.umbral_alto` / `thresholds.umbral_medio` as attribute access
# on an imported `Thresholds()` instance, which necessarily contains those
# substrings in the raw source. `test_app_imports_thresholds_from_skills`
# and `test_app_never_hardcodes_probability_threshold_literals` below
# replace the substring ban for this specific case with stronger,
# structural AST checks.
FORBIDDEN_SOURCE_TOKENS = (
    "UMBRAL_",
    "cluster_alta_conversion",
    "tolerancia_empate",
    "sqlite3",
)

# Threshold numeric literals that must never be compared against a
# probability/cluster-shaped value anywhere in app.py -- see
# `test_app_never_hardcodes_threshold_comparisons` below.
_THRESHOLD_NUMERIC_LITERALS = {0.70, 0.7, 0.30, 0.3, 0.01, 2}

# Identifier/key/attribute name fragments (case-insensitive) that mark an
# `ast.Compare` operand as "probability or cluster shaped" for the same
# check.
_LEAD_FIELD_NAME_FRAGMENTS = ("prob", "cluster")

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


def _stringify_compare_operand(node: ast.AST) -> str:
    """Best-effort textual fingerprint of a Compare operand's name-ish parts.

    Concatenates every `Name.id`, `Attribute.attr`, and string-literal
    `Constant` value reachable inside `node` (e.g. a `Subscript` like
    `row["Probabilidad_Compra"]` yields `"row" + "Probabilidad_Compra"`).
    Used only to decide whether an operand "looks like" a probability or
    cluster value -- see `test_app_never_hardcodes_threshold_comparisons`.
    """

    parts: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            parts.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            parts.append(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            parts.append(sub.value)
    return " ".join(parts)


def test_app_never_hardcodes_threshold_comparisons():
    """PR8 guardrail replacing the old blanket `Cluster`/`Probabilidad_Compra`
    token ban (see the module docstring's PR8 section for the full
    reasoning). Referencing those field names is now legitimate, so this
    test instead walks every `ast.Compare` node in app.py and fails if a
    known threshold numeric literal (0.70, 0.30, 0.01, 2) is compared
    against an operand whose name/key/attribute looks probability- or
    cluster-shaped. This is exactly the shape a re-implemented
    `tier_prioridad`/`banda_probabilidad` comparison chain would take
    (e.g. `if row["Probabilidad_Compra"] >= 0.70:` or
    `if row["Cluster"] == 2:`), and calling the real skill functions
    (already allowlisted above) never produces this AST shape.
    """

    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue

        operands = [node.left, *node.comparators]
        fingerprints = [_stringify_compare_operand(op) for op in operands]
        touches_lead_field = any(
            fragment in fingerprint.lower()
            for fingerprint in fingerprints
            for fragment in _LEAD_FIELD_NAME_FRAGMENTS
        )
        if not touches_lead_field:
            continue

        for op in operands:
            if (
                isinstance(op, ast.Constant)
                and isinstance(op.value, (int, float))
                and not isinstance(op.value, bool)
                and op.value in _THRESHOLD_NUMERIC_LITERALS
            ):
                violations.append(ast.dump(node))

    assert not violations, (
        "app.py hardcodes a threshold numeric literal in a comparison "
        f"against a probability/cluster-shaped value: {violations}. Call "
        "the real skills.py function (tier_prioridad/banda_probabilidad) "
        "instead of re-implementing its comparison chain."
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


def test_app_imports_thresholds_from_skills():
    """PR9: `app.py` must read threshold values through the `Thresholds`
    dataclass imported from `skills.py` -- never a locally-defined stand-in
    -- so the histogram's reference-line positions stay bound to the same
    single source of truth `tier_prioridad`/`banda_probabilidad` use. See
    the module docstring's PR9 section."""

    tree = _parse()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "skills":
            if any(alias.name == "Thresholds" for alias in node.names):
                return
    raise AssertionError(
        "app.py must import Thresholds from skills to read threshold values "
        "for the probability histogram's reference lines"
    )


def test_app_never_hardcodes_probability_threshold_literals():
    """PR9 guardrail, broader than `test_app_never_hardcodes_threshold_comparisons`
    above: no bare `0.70`/`0.7`/`0.30`/`0.3` numeric literal may appear
    ANYWHERE in app.py's source -- not only inside an `ast.Compare`. A
    hardcoded `fig.add_vline(x=0.70, ...)` is a `Call` keyword argument, a
    shape the Compare-scoped check above does not walk, so this test closes
    that gap explicitly. Threshold values must always be read via
    `thresholds.umbral_alto` / `thresholds.umbral_medio` attribute access
    on an imported `Thresholds()` instance (see
    `test_app_imports_thresholds_from_skills` above) -- `Thresholds`'s own
    default arguments live in skills.py, never in app.py.
    """

    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and node.value in {0.70, 0.7, 0.30, 0.3}
        ):
            violations.append(ast.dump(node))

    assert not violations, (
        "app.py hardcodes a probability threshold numeric literal "
        f"(0.70/0.30) directly in its source: {violations}. Read "
        "thresholds.umbral_alto / thresholds.umbral_medio from an imported "
        "Thresholds() instance instead -- app.py must never contain the "
        "literal threshold value itself."
    )
