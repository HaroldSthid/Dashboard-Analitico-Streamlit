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
    SKILLS,
    TOOLS_SCHEMA,
    SkillContext,
    SkillValidationError,
    catalogo_categorias_comentario,
    catalogo_hobbies,
    explicar_tier_de_lead,
    listar_leads_priorizados,
    resumen_por_cluster,
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


class TestResumenPorCluster:
    def test_counts_leads_per_cluster_unfiltered(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = resumen_por_cluster(ctx)

        assert result.skill == "resumen_por_cluster"
        conteo = {row["Cluster"]: row["cantidad_leads"] for row in result.rows}
        # FIXTURE_LEADS: Cluster 2 x4 (ids 1,2,3,7), Cluster 1 x2 (ids 4,6), Cluster 0 x2 (ids 5,8)
        assert conteo == {0: 2, 1: 2, 2: 4}

    def test_counts_leads_per_cluster_filtered_by_hobby(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = resumen_por_cluster(ctx, hobby_estandar="Deportes")

        # Deportes leads: id 2 (Cluster 2), id 5 (Cluster 0), id 8 (Cluster 0)
        conteo = {row["Cluster"]: row["cantidad_leads"] for row in result.rows}
        assert conteo == {0: 2, 2: 1}

    def test_unknown_hobby_raises_skill_validation_error(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        with pytest.raises(SkillValidationError):
            resumen_por_cluster(ctx, hobby_estandar="Ajedrez")


class TestCatalogoHobbies:
    def test_lists_full_hobby_vocabulary_without_citation(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = catalogo_hobbies(ctx)

        assert result.skill == "catalogo_hobbies"
        assert result.citation is None
        nombres = {row["hobby_estandar"] for row in result.rows}
        assert nombres == {"Lectura", "Deportes", "Musica"}
        assert len(result.rows) == 3
        assert all("hobby_id" in row for row in result.rows)


class TestCatalogoCategoriasComentario:
    def test_lists_categories_without_lead_linkage(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        result = catalogo_categorias_comentario(ctx)

        assert result.skill == "catalogo_categorias_comentario"
        assert result.citation is None
        categorias = {row["categoria_comentario"] for row in result.rows}
        assert categorias == {"Queja", "Elogio", "Consulta"}
        assert len(result.rows) == 3
        for row in result.rows:
            assert set(row.keys()) == {"comentario_id", "categoria_comentario"}
            assert "IDPROSPECTO" not in row


class TestListarLeadsPriorizadosSignature:
    def test_accepts_ctx_hobby_tier_limit_kwargs(self, tmp_db_path):
        # Guardrail: this skill must never accept a free-SQL parameter.
        params = inspect.signature(listar_leads_priorizados).parameters
        assert set(params) >= {"ctx", "hobby_estandar", "tier", "limit"}
        assert "query" not in params
        assert "sql" not in params
        assert "where" not in params


class TestSkillsRegistry:
    def test_registry_has_exactly_the_five_phase_2_skills(self):
        assert set(SKILLS.keys()) == {
            "listar_leads_priorizados",
            "explicar_tier_de_lead",
            "resumen_por_cluster",
            "catalogo_hobbies",
            "catalogo_categorias_comentario",
        }

    def test_registry_maps_names_to_the_actual_functions(self):
        assert SKILLS["listar_leads_priorizados"] is listar_leads_priorizados
        assert SKILLS["explicar_tier_de_lead"] is explicar_tier_de_lead
        assert SKILLS["resumen_por_cluster"] is resumen_por_cluster
        assert SKILLS["catalogo_hobbies"] is catalogo_hobbies
        assert SKILLS["catalogo_categorias_comentario"] is catalogo_categorias_comentario

    def test_tools_schema_wraps_each_entry_as_openai_function_type(self):
        # Regression test for a real smoke-test finding: a flat
        # {"name", "description", "parameters"} entry (the pre-fix shape)
        # is silently ignored by real OpenAI-compatible providers, so no
        # live model could ever call a tool. See skills.py's TOOLS_SCHEMA
        # comment for the full story.
        for tool in TOOLS_SCHEMA:
            assert tool["type"] == "function"
            assert "function" in tool
            assert set(tool.keys()) == {"type", "function"}

    def test_tools_schema_has_one_entry_per_registered_skill(self):
        assert len(TOOLS_SCHEMA) == 5
        names = {tool["function"]["name"] for tool in TOOLS_SCHEMA}
        assert names == set(SKILLS.keys())
        for tool in TOOLS_SCHEMA:
            assert tool["function"]["description"]
            assert "properties" in tool["function"]["parameters"]

    def test_tools_schema_has_no_free_sql_parameters(self):
        banned = {"query", "sql", "where"}
        for tool in TOOLS_SCHEMA:
            function = tool["function"]
            properties = set(function["parameters"].get("properties", {}).keys())
            assert not (properties & banned), (
                f"{function['name']} exposes a free-SQL parameter: {properties & banned}"
            )
            for field_name in properties:
                assert not any(term in field_name.lower() for term in banned)

    def test_no_skill_combines_lead_identifier_with_comentario_category(self, tmp_db_path):
        ctx = SkillContext(db_path=tmp_db_path)
        for name, skill_fn in SKILLS.items():
            params = inspect.signature(skill_fn).parameters
            if "idprospecto" not in params:
                continue
            result = skill_fn(ctx, idprospecto=1)
            for row in result.rows:
                assert "categoria_comentario" not in row
                assert "comentario_id" not in row
