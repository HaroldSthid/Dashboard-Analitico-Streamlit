"""Tests for the persistent dashboard panel's data-loading logic (PR7).

These import `app.py` directly (safe: app.py's top-level code only defines
constants and functions -- `main()` runs only under
`if __name__ == "__main__":`) and exercise `_load_panel_data()` against the
same `tmp_db_path` fixture the skill tests use (see `conftest.py`'s
`FIXTURE_LEADS`: 8 leads across 3 clusters).

This is the one part of the persistent panel that is meaningfully
unit-testable without a live Streamlit script run: it is a plain function
returning plain data, with no `st.*` calls inside it. The actual widget
placement (`st.metric`/`st.dataframe`/`st.plotly_chart`) is UI rendering
and is instead covered by the manual smoke test (see apply-progress).

Expected tier breakdown for `FIXTURE_LEADS` under the default `Thresholds`
(cluster_alta_conversion=2, umbral_alto=0.70, umbral_medio=0.30):
  Alto: id=1 (cluster 2, 0.95), id=2 (cluster 2, 0.71)            -> 2
  Medio: id=3 (0.50), id=4 (0.65), id=5 (0.40), id=6 (0.30)       -> 4
  Bajo: id=7 (0.20), id=8 (0.05)                                  -> 2
"""

from __future__ import annotations

import app


def test_load_panel_data_totals_match_full_population(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)

    assert data["total_leads"] == 8
    assert data["high_tier_count"] == 2
    assert data["mid_tier_count"] == 4


def test_load_panel_data_table_rows_cover_whole_fixture_population(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)

    assert len(data["table_rows"]) == 8


def test_load_panel_data_grouped_rows_sum_to_total(tmp_db_path):
    data = app._load_panel_data(tmp_db_path)

    assert sum(row["cantidad_leads"] for row in data["grouped_rows"]) == data["total_leads"]
