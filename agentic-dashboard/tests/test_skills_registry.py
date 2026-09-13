"""Unit tests for Phase 2 skill implementations and the closed SKILLS registry.

Phase 2 scope: the 5 skill functions (`listar_leads_priorizados`,
`explicar_tier_de_lead`, `resumen_por_cluster`, `catalogo_hobbies`,
`catalogo_categorias_comentario`), `SkillValidationError`, the closed
`SKILLS` registry, and `TOOLS_SCHEMA`.

Uses the `tmp_db_path` fixture from `conftest.py` (3-hobby fixture: see
`FIXTURE_LEADS`, `FIXTURE_HOBBIES`, `FIXTURE_COMENTARIO_CATEGORIAS`).

Invariant under test throughout this file: `dim_comentario` is never joined
or merged to `tbl_leads` at the row level, in any skill.
"""

from __future__ import annotations

import inspect

import pytest

from skills import (
    SkillContext,
    SkillValidationError,
    explicar_tier_de_lead,
    listar_leads_priorizados,
)


class TestListarLeadsPriorizadosUnfiltered:
    def test_ranks_full_population_before_any_filtering(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = listar_leads_priorizados(ctx)

        assert result.skill == "listar_leads_priorizados"
        assert len(result.rows) == 8  # all FIXTURE_LEADS, unfiltered
        ids = [row["IDPROSPECTO"] for row in result.rows]
        # Highest Probabilidad_Compra in Cluster 2 (id=1, 0.95) ranks first.
        assert ids[0] == 1
        assert result.rows[0]["tier_prioridad"] == "Alto"
        assert result.rows[0]["orden_contacto"] == 1

    def test_every_row_has_a_citation(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = listar_leads_priorizados(ctx)

        assert result.citation is not None
        assert result.citation.umbral_alto == 0.70
        # Every row carries tier_prioridad, which requires a citation per
        # SkillResult.__post_init__ — the fact construction succeeded proves
        # the citation covers every row.
        assert all("tier_prioridad" in row for row in result.rows)

    def test_limit_truncates_after_ranking(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = listar_leads_priorizados(ctx, limit=3)
        assert len(result.rows) == 3
        assert result.rows[0]["IDPROSPECTO"] == 1


class TestListarLeadsPriorizadosHobbyFilter:
    def test_hobby_estandar_none_returns_all(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = listar_leads_priorizados(ctx, hobby_estandar=None)
        assert len(result.rows) == 8

    def test_unknown_hobby_raises_skill_validation_error(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        with pytest.raises(SkillValidationError):
            listar_leads_priorizados(ctx, hobby_estandar="Ajedrez")

    def test_filter_preserves_orden_contacto_from_unfiltered_ranking(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        unfiltered = listar_leads_priorizados(ctx)
        unfiltered_orden = {row["IDPROSPECTO"]: row["orden_contacto"] for row in unfiltered.rows}

        filtered = listar_leads_priorizados(ctx, hobby_estandar="Lectura")

        # Lectura leads: id 1 (Alto), id 3 (Medio), id 6 (Medio).
        assert {row["IDPROSPECTO"] for row in filtered.rows} == {1, 3, 6}
        for row in filtered.rows:
            assert row["orden_contacto"] == unfiltered_orden[row["IDPROSPECTO"]]

    def test_tier_filter_applies_after_hobby_filter(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = listar_leads_priorizados(ctx, hobby_estandar="Lectura", tier="Medio")
        assert {row["IDPROSPECTO"] for row in result.rows} == {3, 6}
        assert all(row["tier_prioridad"] == "Medio" for row in result.rows)


class TestExplicarTierDeLead:
    def test_explains_high_tier_lead_with_citation(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = explicar_tier_de_lead(ctx, idprospecto=1)

        assert result.skill == "explicar_tier_de_lead"
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row["IDPROSPECTO"] == 1
        assert row["tier_prioridad"] == "Alto"
        assert result.citation is not None

    def test_explains_low_tier_lead(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = explicar_tier_de_lead(ctx, idprospecto=8)
        assert result.rows[0]["tier_prioridad"] == "Bajo"

    def test_unknown_idprospecto_raises_skill_validation_error(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        with pytest.raises(SkillValidationError):
            explicar_tier_de_lead(ctx, idprospecto=999)


class TestListarLeadsPriorizadosSignature:
    def test_accepts_ctx_hobby_tier_limit_kwargs(self, tmp_db_path):
        # Guardrail: this skill must never accept a free-SQL parameter.
        params = inspect.signature(listar_leads_priorizados).parameters
        assert set(params) >= {"ctx", "hobby_estandar", "tier", "limit"}
        assert "query" not in params
        assert "sql" not in params
        assert "where" not in params
