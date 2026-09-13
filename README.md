# Dashboard Analítico — Streamlit (extra chapter)

Role-simulated data team exercise: three role-scoped markdown specs (data engineer, data
analyst, data scientist) plus an anonymized public dataset. A learner's own code agent reads
`roles/*.md` and `data/db_dashboard_course.db` and writes a running Streamlit + Plotly dashboard
from them — the *original exercise* does not ship that dashboard pre-built, on purpose.

What this repo *does* ship, pre-built and merged: `reference-solution/` (a worked reference
answer to the exercise above) and `agentic-dashboard/` (a separate, later extension — a real AI
agent wrapping that same business logic in specs, guardrails, and observability). See the
[narrative site](https://haroldsthid.github.io/Dashboard-Analitico-Streamlit/) for the full story
of both, with screenshots and a step-by-step walkthrough of the agent's Reason→Select→Execute→
Retry loop.

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
- `reference-solution/` — a worked, rule-based Streamlit + Plotly answer to the exercise below
  (spoiler — use it to get unstuck, not to copy first).
- `agentic-dashboard/` — the agentic extension: `skills.py` (pure business-rule functions, closed
  registry), `agent_harness.py` (Reason→Select→Execute→Retry loop), `gateways.py`
  (OpenRouter/Ollama, interchangeable via env var), `guardrail.py` (structural, never-leak-PII
  post-generation check), `trace.py` (Markdown trace notes for Obsidian's Graph View), and
  `app.py` (a persistent KPI/table/chart panel plus a chat interface — the dashboard, not just a
  chatbot). Built via 8 chained/follow-up Spec-Driven Development PRs, each independently
  verified before merging.

## How to run the exercise

1. Read `EXERCISE.md` for the convention contrast with Módulo 4.
2. Read `roles/01-data-engineer.md`, then `02-data-analyst.md`, then `03-data-scientist.md`.
3. Using only those specs and `data/db_dashboard_course.db`, build a Streamlit dashboard.

## How to run the agentic extension

1. `pip install -r requirements.txt`.
2. Pick a backend: either install [Ollama](https://ollama.com/download) and `ollama pull
   qwen2.5:7b` (free, local), or set `OPENROUTER_API_KEY` and `AGENT_LLM_BACKEND=openrouter`.
3. `streamlit run agentic-dashboard/app.py`.
4. `python -m pytest agentic-dashboard/tests/` runs the full test suite (strict TDD throughout).

## Status

Both the original exercise chapter and the agentic extension are complete and merged to `main`.
See `openspec/changes/archive/2026-09-09-ml-dashboard-chapter` in
`DataScienceAplicado-Fundamentals` for the original chapter's SDD history, and this repo's merged
PRs for the agentic extension's.
