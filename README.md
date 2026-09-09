# Dashboard Analítico — Streamlit (extra chapter)

Role-simulated data team exercise: three role-scoped markdown specs (data engineer, data
analyst, data scientist) plus an anonymized public dataset. A learner's own code agent reads
`roles/*.md` and `data/db_dashboard_course.db` and writes a running Streamlit + Plotly dashboard
from them — this repo does not ship the dashboard app itself.

This is a spec-first, code-deferred repo. See `EXERCISE.md` for how its conventions differ from
`DataScienceAplicado-Fundamentals` Módulo 4 (strict TDD, contract tests, `src/` pipeline layout).

## Structure

- `roles/` — the three role-scoped specs, read in order: `01-data-engineer.md` →
  `02-data-analyst.md` → `03-data-scientist.md`.
- `data/db_dashboard_course.db` — committed, anonymized SQLite dataset (`tbl_leads`, `dim_hobby`,
  `dim_comentario`).
- `docs/contratos-datos.md` — data contracts and validation for the tables above.
- `docs/negociacion.md` — the one explicit disagreement point in the role handoff chain.
- `scripts/build_public_dataset.py` — the (auditable, PII-free) script that produced
  `data/db_dashboard_course.db` from private sibling-repo sources.

## How to run the exercise

1. Read `EXERCISE.md` for the convention contrast with Módulo 4.
2. Read `roles/01-data-engineer.md`, then `02-data-analyst.md`, then `03-data-scientist.md`.
3. Using only those specs and `data/db_dashboard_course.db`, build a Streamlit dashboard.

## Status

Spec package in progress. See `openspec/changes/ml-dashboard-chapter` in
`DataScienceAplicado-Fundamentals` for the full change tracking this repo's build-out.
