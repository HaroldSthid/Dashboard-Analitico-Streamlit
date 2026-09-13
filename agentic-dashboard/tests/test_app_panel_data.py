"""Tests for the persistent dashboard panel's data-loading logic (PR7 + PR8).

These import `app.py` directly (safe: app.py's top-level code only defines
constants and functions -- `main()` runs only under
`if __name__ == "__main__":`) and exercise `_load_panel_data()` against the
same `tmp_db_path` fixture the skill tests use (see `conftest.py`'s
`FIXTURE_LEADS`: 8 leads across 3 clusters).

PR8 changes `_load_panel_data()`'s contract: it now returns the FULL ranked
population (`all_rows`, not capped at the `limit=50` default) plus the
hobby vocabulary, and no longer pre-computes KPI counts (`total_leads`,
`high_tier_count`, `mid_tier_count`, `grouped_rows`). Those now depend on
the sidebar's filter state, which is only known at render time, so
`_render_dashboard_panel()` recomputes them from `_apply_filters()`'s
output instead (see `test_app_filters.py`).

This is the one part of the persistent panel that is meaningfully
unit-testable without a live Streamlit script run: it is a plain function
returning plain data, with no `st.*` calls inside it. The actual widget
placement (`st.metric`/`st.dataframe`/`st.plotly_chart`/sidebar filters) is
UI rendering and is instead covered by the manual smoke test (see
apply-progress).

Expected tier breakdown for `FIXTURE_LEADS` under the default `Thresholds`
(cluster_alta_conversion=2, umbral_alto=0.70, umbral_medio=0.30):
  Alto: id=1 (cluster 2, 0.95), id=2 (cluster 2, 0.71)            -> 2
  Medio: id=3 (0.50), id=4 (0.65), id=5 (0.40), id=6 (0.30)       -> 4
  Bajo: id=7 (0.20), id=8 (0.05)                                  -> 2
"""

from __future__ import annotations

import app


def test_load_panel_data_population_size_matches_full_fixture(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)
    assert data["population_size"] == 8


def test_load_panel_data_all_rows_cover_whole_fixture_population(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)
    assert len(data["all_rows"]) == 8


def test_load_panel_data_all_rows_are_already_ranked(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)
    assert all("tier_prioridad" in row and "orden_contacto" in row for row in data["all_rows"])

    tiers = {row["IDPROSPECTO"]: row["tier_prioridad"] for row in data["all_rows"]}
    assert tiers[1] == "Alto"
    assert tiers[2] == "Alto"
    assert tiers[7] == "Bajo"
    assert tiers[8] == "Bajo"


def test_load_panel_data_hobby_options_match_fixture_vocabulary(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)
    assert set(data["hobby_options"]) == {"Lectura", "Deportes", "Musica"}
