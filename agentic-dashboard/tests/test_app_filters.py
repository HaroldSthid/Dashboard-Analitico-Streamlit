"""Unit tests for app.py's pure, in-memory filtering/aggregation helpers (PR8).

`_apply_filters` is the presentation-layer filter the persistent panel runs
over the already-ranked FULL population `_load_panel_data()` returns -- it
never re-queries the skill layer per filter combination and never re-ranks
the filtered subset (`orden_contacto` values are preserved from the
original ranking, exactly like `listar_leads_priorizados`' own hobby/tier
filtering already does). See `app.py`'s module docstring for the full
reasoning, and `test_app_boundary.py` for why referencing `Cluster`,
`Probabilidad_Compra`, `IDPROSPECTO`, `Hobbies_Estandar`, and
`tier_prioridad` as dict keys here is allowed.

This is the one part of PR8's filtering logic that is meaningfully
unit-testable without a live Streamlit script run: it is a plain function
returning plain data, with no `st.*` calls inside it. The actual sidebar
widget placement is UI rendering and is instead covered by the manual
`AppTest` smoke test (see apply-progress).
"""

from __future__ import annotations

import app

_ROWS = [
    {
        "IDPROSPECTO": 1,
        "Cluster": 2,
        "Probabilidad_Compra": 0.95,
        "Hobbies_Estandar": "Lectura",
        "tier_prioridad": "Alto",
        "orden_contacto": 1,
    },
    {
        "IDPROSPECTO": 2,
        "Cluster": 2,
        "Probabilidad_Compra": 0.71,
        "Hobbies_Estandar": "Deportes",
        "tier_prioridad": "Alto",
        "orden_contacto": 2,
    },
    {
        "IDPROSPECTO": 3,
        "Cluster": 1,
        "Probabilidad_Compra": 0.50,
        "Hobbies_Estandar": "Lectura",
        "tier_prioridad": "Medio",
        "orden_contacto": 1,
    },
    {
        "IDPROSPECTO": 4,
        "Cluster": 0,
        "Probabilidad_Compra": 0.05,
        "Hobbies_Estandar": "Musica",
        "tier_prioridad": "Bajo",
        "orden_contacto": 1,
    },
]

_ALL_TIERS = ("Alto", "Medio", "Bajo")
_ALL_CLUSTERS = (0, 1, 2)


class TestApplyFilters:
    def test_no_restriction_returns_all_rows_unchanged_order(self):
        result = app._apply_filters(
            _ROWS,
            tiers=_ALL_TIERS,
            clusters=_ALL_CLUSTERS,
            hobby=app._HOBBY_ALL_OPTION,
            idprospecto=0,
        )
        assert result == _ROWS

    def test_tier_filter(self):
        result = app._apply_filters(
            _ROWS, tiers=("Alto",), clusters=_ALL_CLUSTERS, hobby=app._HOBBY_ALL_OPTION, idprospecto=0
        )
        assert {row["IDPROSPECTO"] for row in result} == {1, 2}

    def test_cluster_filter(self):
        result = app._apply_filters(
            _ROWS, tiers=_ALL_TIERS, clusters=(2,), hobby=app._HOBBY_ALL_OPTION, idprospecto=0
        )
        assert {row["IDPROSPECTO"] for row in result} == {1, 2}

    def test_hobby_filter(self):
        result = app._apply_filters(
            _ROWS, tiers=_ALL_TIERS, clusters=_ALL_CLUSTERS, hobby="Lectura", idprospecto=0
        )
        assert {row["IDPROSPECTO"] for row in result} == {1, 3}

    def test_idprospecto_zero_means_no_restriction(self):
        result = app._apply_filters(
            _ROWS, tiers=_ALL_TIERS, clusters=_ALL_CLUSTERS, hobby=app._HOBBY_ALL_OPTION, idprospecto=0
        )
        assert len(result) == 4

    def test_idprospecto_filter_matches_exact_id(self):
        result = app._apply_filters(
            _ROWS, tiers=_ALL_TIERS, clusters=_ALL_CLUSTERS, hobby=app._HOBBY_ALL_OPTION, idprospecto=2
        )
        assert [row["IDPROSPECTO"] for row in result] == [2]

    def test_all_four_filters_combine_with_and_logic(self):
        result = app._apply_filters(
            _ROWS, tiers=("Alto",), clusters=(2,), hobby="Deportes", idprospecto=0
        )
        assert [row["IDPROSPECTO"] for row in result] == [2]

    def test_empty_tier_selection_yields_no_rows(self):
        result = app._apply_filters(
            _ROWS, tiers=(), clusters=_ALL_CLUSTERS, hobby=app._HOBBY_ALL_OPTION, idprospecto=0
        )
        assert result == []

    def test_preserves_original_ranking_order(self):
        # Filtering must never re-sort -- it only removes non-matching rows,
        # preserving the orden_contacto ranking _load_panel_data() already
        # computed over the full population.
        result = app._apply_filters(
            _ROWS, tiers=_ALL_TIERS, clusters=_ALL_CLUSTERS, hobby=app._HOBBY_ALL_OPTION, idprospecto=0
        )
        assert [row["IDPROSPECTO"] for row in result] == [1, 2, 3, 4]


class TestDeltaPct:
    def test_computes_percentage_of_whole(self):
        assert app._delta_pct(2, 4) == "50.0%"

    def test_zero_whole_returns_zero_percent_without_raising(self):
        assert app._delta_pct(0, 0) == "0.0%"

    def test_full_share_is_one_hundred_percent(self):
        assert app._delta_pct(3, 3) == "100.0%"
