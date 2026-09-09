"""One-off script: builds the public, anonymized dashboard dataset.

Reads the private DataScienceAplicado-Fundamentals sibling-repo dictionaries
(`sourcesbusinesscase/*.xlsx`, git-ignored there) and the existing public
`tbl_Kmean_Iteracion_3vmi` table, and emits `data/db_dashboard_course.db`
with three tables: `tbl_leads` (copied from the fact table plus two computed
ML columns, see below), `dim_hobby`, and `dim_comentario`.

This script holds no PII itself — only allow-lists, PII-pattern rejection
checks, and deterministic surrogate-key mapping logic, mirroring the
`SOURCE_TYPES` / `vendedor_map` discipline in
`DSUnidistrital_CaseInmobiliario/anonymize_db.py`. It reads raw dictionary
values only to compute deduplicated category labels; it does not print or
persist any raw per-row value from the source dictionaries.

Inspection gate finding (tasks 1.1-1.2, recorded here per design.md's
anonymization design table):
  - `dim_hobby` DOES join to the fact table: 38 of 40 (95%) distinct
    `Hobbies_Estandar` values in `tbl_Kmean_Iteracion_3vmi` match the
    dictionary's `ESTANDAR` column by value. The 2 non-matching fact-table
    values ("Areas Sociales", "Otros") are folded into `dim_hobby` by taking
    the union of the dictionary's label universe and the fact table's actual
    distinct values, so the join has zero orphans by construction.
  - `dim_comentario` has NO column joinable to any column in
    `tbl_Kmean_Iteracion_3vmi`, by name or by overlapping values (checked
    against every text column in the fact table). Per the CONFIRMED design
    decision, it ships as a standalone vocabulary table.

CRITICAL-1 remediation (verify-report.md): `Cluster` and `Probabilidad_Compra`
were previously asserted by spec.md/contratos-datos.md/roles/*.md but never
computed or persisted anywhere — `copy_tbl_leads` blindly reflected whatever
columns `tbl_Kmean_Iteracion_3vmi` already had (22, neither of the two). This
script now imports and re-runs Módulo 4's *actual* trained pipeline
(`DataScienceAplicado-Fundamentals/src/data_processing.py` +
`src/models.py`, the same functions/call sequence `main.py` uses there) via
`compute_ml_outputs()`, and merges the two computed columns into `tbl_leads`
by `IDPROSPECTO` (see `copy_tbl_leads`). No K-Means/Random Forest logic is
reimplemented here — the sibling repo's own functions are imported and
invoked as-is. `tbl_leads` therefore now ships 24 columns (22 original + 2
computed). Every random_state in that pipeline is pinned to 42
(`KMeans`, `DecisionTreeClassifier`, `train_test_split`,
`RandomForestClassifier`), so the computed values — and this script's
byte-identical-rebuild property (design decision 3) — remain deterministic
across runs on the same installed sklearn version.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_REPO = REPO_ROOT.parent / "DataScienceAplicado-Fundamentals"
SOURCE_DB = SOURCE_REPO / "db_casoInmobiliaria_DS_course.db"
SOURCES_DIR = SOURCE_REPO / "sourcesbusinesscase"
HOBBIES_XLSX = SOURCES_DIR / "Diccionarios_Hobbies.xlsx"
COMENTARIOS_XLSX = SOURCES_DIR / "Diccionario_ComentariosEstandarizado.xlsx"

OUT_DB = REPO_ROOT / "data" / "db_dashboard_course.db"

FACT_TABLE = "tbl_Kmean_Iteracion_3vmi"

# --- Allow-lists: only these columns are ever written to the public tables ---
DIM_HOBBY_ALLOW_LIST = ["hobby_id", "hobby_estandar"]
DIM_COMENTARIO_ALLOW_LIST = ["comentario_id", "categoria_comentario"]

# --- Sibling repo: Módulo 4's real, already-trained-and-contracted pipeline.
# Imported (not reimplemented) so Cluster/Probabilidad_Compra are computed by
# the same K-Means + Random Forest logic pytest already validates there.
sys.path.insert(0, str(SOURCE_REPO))
from src.data_processing import (  # noqa: E402
    cargar_datos,
    ejecutar_limpieza_pipeline,
    imputar_estado_civil,
)
from src.models import (  # noqa: E402
    entrenar_evaluar_probabilidad,
    segmentar_clientes_kmeans,
)

# Mirrors main.py's PREDICTORES_ESTADO_CIVIL in DataScienceAplicado-Fundamentals.
PREDICTORES_ESTADO_CIVIL = [
    "Salario_MarcaClase",
    "InteresMetraje_MarcaClase",
    "$KMD-K-Means",
    "mvi_Edad1",
]

# FIX 2 (verify-report SUGGESTION-2): "Celeus" is the source client's real
# company name; genericize it in the published output label only. The source
# xlsx itself is never modified.
DIM_COMENTARIO_LABEL_OVERRIDES = {
    "Evaluá a Celeus como empresa": "Evaluá a la empresa",
}

# --- PII-pattern rejection rules (spec.md `dashboard-dataset` scenarios) ---
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"\+?\d[\d\-\s]{6,}\d")
FREE_TEXT_TOKEN_THRESHOLD = 6


def reject_reasons(series: pd.Series) -> list[str]:
    """Return PII-pattern rejection reasons for a candidate column, or [] if clean."""
    reasons: list[str] = []
    text = series.dropna().astype(str)
    if text.empty:
        return reasons
    if text.str.contains(EMAIL_RE).any():
        reasons.append("email-pattern match")
    if text.str.contains(PHONE_RE).any():
        reasons.append("phone-number-pattern match")
    # Average token count (not worst-case max) distinguishes "free-text
    # sentences" from a deduplicated categorical label column that happens
    # to have a few longer entries (spec.md's "Valid categorical projection
    # accepted" scenario: short deduplicated category labels must pass).
    token_counts = text.str.split().apply(len)
    if token_counts.mean() > FREE_TEXT_TOKEN_THRESHOLD:
        reasons.append(f"average free text length > {FREE_TEXT_TOKEN_THRESHOLD} tokens")
    # Near-unique values relative to row count is the primary proxy for
    # "this is raw per-row text, not a deduplicated category label".
    if len(text) > 10 and text.nunique() / len(text) > 0.9:
        reasons.append("near-unique per-row values (not a deduplicated category label)")
    return reasons


def assert_allow_list(emitted_cols: list[str], allow_list: list[str], table_name: str) -> None:
    assert set(emitted_cols) == set(allow_list), (
        f"{table_name}: emitted schema {emitted_cols} must exactly match allow-list {allow_list}"
    )


def build_dim_hobby(con_out: sqlite3.Connection, con_src: sqlite3.Connection) -> None:
    hob = pd.read_excel(HOBBIES_XLSX)

    cp13_reasons = reject_reasons(hob["cp13"])
    print(
        "[dim_hobby] excluded column 'cp13' (raw source code, not on allow-list); "
        f"PII scan reasons if it had been a candidate: {cp13_reasons or 'none'}"
    )

    estandar_reasons = reject_reasons(hob["ESTANDAR"])
    assert not estandar_reasons, f"dim_hobby: ESTANDAR column failed PII scan: {estandar_reasons}"

    # FIX 3 (verify-report WARNING-3): strip every label before dedup so a
    # trailing-space variant does not survive as a distinct row.
    dict_labels = {label.strip() for label in hob["ESTANDAR"].dropna().unique()}

    fact_labels = {
        row[0].strip()
        for row in con_src.execute(f'SELECT DISTINCT "Hobbies_Estandar" FROM "{FACT_TABLE}"')
        if row[0] is not None
    }

    # Union of the dictionary's label universe and the fact table's actual
    # values guarantees zero orphans on the fact-table join (inspection
    # finding 1.2: 2 of 40 fact-table labels are not present in the xlsx
    # dictionary snapshot).
    fact_only = fact_labels - dict_labels
    all_labels = sorted(dict_labels | fact_labels)

    emitted_cols = ["hobby_id", "hobby_estandar"]
    assert_allow_list(emitted_cols, DIM_HOBBY_ALLOW_LIST, "dim_hobby")

    rows = [(i, label) for i, label in enumerate(all_labels, start=1)]

    con_out.execute(
        "CREATE TABLE dim_hobby (hobby_id INTEGER PRIMARY KEY, hobby_estandar TEXT NOT NULL)"
    )
    con_out.executemany("INSERT INTO dim_hobby VALUES (?, ?)", rows)
    print(
        f"[dim_hobby] wrote {len(rows)} rows "
        f"(dictionary labels: {len(dict_labels)}, fact-table-only additions: {len(fact_only)})"
    )


def build_dim_comentario(con_out: sqlite3.Connection) -> None:
    com = pd.read_excel(COMENTARIOS_XLSX)

    for col in ["recodificar", "ComentarioStandarizado", "Tono"]:
        reasons = reject_reasons(com[col])
        print(
            f"[dim_comentario] excluded column '{col}' (not on allow-list); "
            f"PII scan reasons: {reasons or 'none, excluded because not part of the documented contract'}"
        )

    categoria_reasons = reject_reasons(com["Categoria"])
    assert not categoria_reasons, f"dim_comentario: Categoria column failed PII scan: {categoria_reasons}"

    # FIX 3 (verify-report WARNING-3): strip every label before dedup.
    # FIX 2 (verify-report SUGGESTION-2): genericize the source client's
    # company name in the published label only (source xlsx untouched).
    raw_labels = {label.strip() for label in com["Categoria"].dropna().unique()}
    labels = sorted(DIM_COMENTARIO_LABEL_OVERRIDES.get(label, label) for label in raw_labels)
    rows = [(i, label) for i, label in enumerate(labels, start=1)]

    emitted_cols = ["comentario_id", "categoria_comentario"]
    assert_allow_list(emitted_cols, DIM_COMENTARIO_ALLOW_LIST, "dim_comentario")

    con_out.execute(
        "CREATE TABLE dim_comentario (comentario_id INTEGER PRIMARY KEY, categoria_comentario TEXT NOT NULL)"
    )
    con_out.executemany("INSERT INTO dim_comentario VALUES (?, ?)", rows)
    print(
        f"[dim_comentario] wrote {len(rows)} rows "
        f"(standalone vocabulary table — no proven join key to {FACT_TABLE}, per inspection gate 1.2)"
    )


def compute_ml_outputs() -> pd.DataFrame:
    """
    Re-runs Módulo 4's real, trained pipeline against its own public source DB
    (`DataScienceAplicado-Fundamentals/db_casoInmobiliaria_DS_course.db`), using
    the exact same imported functions and call sequence as that repo's
    `main.py` (cargar_datos -> ejecutar_limpieza_pipeline ->
    imputar_estado_civil -> segmentar_clientes_kmeans ->
    entrenar_evaluar_probabilidad). No K-Means/Random Forest logic is
    duplicated here.

    Returns a DataFrame with `IDPROSPECTO`, `Cluster` (int), and
    `Probabilidad_Compra` (float in [0, 1]), one row per lead.
    """
    df = cargar_datos(str(SOURCE_DB), FACT_TABLE)
    df = ejecutar_limpieza_pipeline(df)
    df = imputar_estado_civil(df, PREDICTORES_ESTADO_CIVIL)
    df = segmentar_clientes_kmeans(df)
    df = entrenar_evaluar_probabilidad(df)
    return df[["IDPROSPECTO", "Cluster", "Probabilidad_Compra"]]


def copy_tbl_leads(
    con_out: sqlite3.Connection, con_src: sqlite3.Connection, ml_df: pd.DataFrame
) -> None:
    """
    Copies the fact table's original columns unchanged, plus the two
    computed ML columns (Cluster, Probabilidad_Compra) merged in by
    IDPROSPECTO (FIX 1 / CRITICAL-1 remediation, see module docstring).
    """
    cols = con_src.execute(f'PRAGMA table_info("{FACT_TABLE}")').fetchall()
    col_defs = ", ".join(f'"{c[1]}" {c[2]}' for c in cols)
    col_defs += ', "Cluster" INTEGER, "Probabilidad_Compra" REAL'
    con_out.execute(f"CREATE TABLE tbl_leads ({col_defs})")

    col_names = [c[1] for c in cols]
    cols_sql = ", ".join(f'"{c}"' for c in col_names)
    rows = con_src.execute(f'SELECT {cols_sql} FROM "{FACT_TABLE}"').fetchall()

    id_idx = col_names.index("IDPROSPECTO")
    ml_lookup = ml_df.set_index("IDPROSPECTO")[["Cluster", "Probabilidad_Compra"]].to_dict("index")

    extended_rows = []
    for row in rows:
        idprospecto = row[id_idx]
        ml_vals = ml_lookup.get(idprospecto)
        assert ml_vals is not None, (
            f"tbl_leads: IDPROSPECTO {idprospecto} has no computed ML outputs "
            "(compute_ml_outputs() and the fact-table copy diverged in row set)"
        )
        extended_rows.append(row + (int(ml_vals["Cluster"]), float(ml_vals["Probabilidad_Compra"])))

    placeholders = ", ".join("?" for _ in range(len(col_names) + 2))
    con_out.executemany(f"INSERT INTO tbl_leads VALUES ({placeholders})", extended_rows)
    print(
        f"[tbl_leads] copied {len(rows)} rows x {len(col_names)} original cols from "
        f"{FACT_TABLE}, plus 2 computed cols (Cluster, Probabilidad_Compra) via "
        f"compute_ml_outputs() re-running Módulo 4's K-Means + Random Forest pipeline "
        f"({len(col_names) + 2} cols total)"
    )


def verify_no_orphan_hobbies(con_out: sqlite3.Connection) -> None:
    orphans = con_out.execute(
        """
        SELECT COUNT(*)
        FROM tbl_leads t
        LEFT JOIN dim_hobby h ON t."Hobbies_Estandar" = h.hobby_estandar
        WHERE t."Hobbies_Estandar" IS NOT NULL AND h.hobby_id IS NULL
        """
    ).fetchone()[0]
    assert orphans == 0, f"dim_hobby join has {orphans} orphan Hobbies_Estandar rows"
    print("[verify] dim_hobby join: 0 orphan Hobbies_Estandar rows")


def main() -> None:
    assert SOURCE_DB.exists(), f"Source DB not found: {SOURCE_DB}"
    assert HOBBIES_XLSX.exists(), f"Hobbies dictionary not found: {HOBBIES_XLSX}"
    assert COMENTARIOS_XLSX.exists(), f"Comentarios dictionary not found: {COMENTARIOS_XLSX}"

    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()

    print("[tbl_leads] computing Cluster / Probabilidad_Compra via Módulo 4's pipeline...")
    ml_df = compute_ml_outputs()

    con_src = sqlite3.connect(SOURCE_DB)
    con_out = sqlite3.connect(OUT_DB)
    try:
        copy_tbl_leads(con_out, con_src, ml_df)
        build_dim_hobby(con_out, con_src)
        build_dim_comentario(con_out)
        con_out.commit()
        verify_no_orphan_hobbies(con_out)
    finally:
        con_src.close()
        con_out.close()

    print(f"Done. Wrote {OUT_DB}")


if __name__ == "__main__":
    main()
