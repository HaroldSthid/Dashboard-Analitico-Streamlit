"""Shared pytest fixtures for agentic-dashboard tests.

Adds the `agentic-dashboard/` package directory to `sys.path` so test modules
can `import skills` directly (the folder name uses a hyphen and is not a
valid Python package identifier, so it cannot be imported as a package).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 3-hobby vocabulary used across fixtures and tests.
FIXTURE_HOBBIES = ["Lectura", "Deportes", "Musica"]

# Comment-category vocabulary (dim_comentario ships as a catalog only, never
# joined to tbl_leads).
FIXTURE_COMENTARIO_CATEGORIAS = ["Queja", "Elogio", "Consulta"]

# (IDPROSPECTO, Cluster, Probabilidad_Compra, Hobbies_Estandar)
FIXTURE_LEADS = [
    (1, 2, 0.95, "Lectura"),
    (2, 2, 0.71, "Deportes"),
    (3, 2, 0.50, "Lectura"),
    (4, 1, 0.65, "Musica"),
    (5, 0, 0.40, "Deportes"),
    (6, 1, 0.30, "Lectura"),
    (7, 2, 0.20, "Musica"),
    (8, 0, 0.05, "Deportes"),
]


def _build_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE tbl_leads (
            IDPROSPECTO INTEGER PRIMARY KEY,
            Cluster INTEGER NOT NULL,
            Probabilidad_Compra REAL NOT NULL,
            Hobbies_Estandar TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE dim_hobby (
            hobby_id INTEGER PRIMARY KEY,
            hobby_estandar TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE dim_comentario (
            comentario_id INTEGER PRIMARY KEY,
            categoria_comentario TEXT NOT NULL
        );
        """
    )


def _populate(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.executemany(
        "INSERT INTO tbl_leads (IDPROSPECTO, Cluster, Probabilidad_Compra, Hobbies_Estandar) "
        "VALUES (?, ?, ?, ?);",
        FIXTURE_LEADS,
    )
    cur.executemany(
        "INSERT INTO dim_hobby (hobby_id, hobby_estandar) VALUES (?, ?);",
        list(enumerate(FIXTURE_HOBBIES, start=1)),
    )
    cur.executemany(
        "INSERT INTO dim_comentario (comentario_id, categoria_comentario) VALUES (?, ?);",
        list(enumerate(FIXTURE_COMENTARIO_CATEGORIAS, start=1)),
    )
    con.commit()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Create a tmp-file SQLite DB matching the real schema and return its path."""
    db_path = str(tmp_path / "test_dashboard.db")
    con = sqlite3.connect(db_path)
    try:
        _build_schema(con)
        _populate(con)
    finally:
        con.close()
    return db_path
