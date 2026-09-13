"""Unit tests for agentic-dashboard/skills.py contracts and pure functions.

Phase 1 scope only: Thresholds, SkillContext, SkillResult/CitationMissing/
ThresholdCitation, tier_prioridad, orden_contacto, banda_probabilidad.

Business-rule boundaries (UMBRAL_ALTO, UMBRAL_MEDIO, CLUSTER_ALTA_CONVERSION,
TOLERANCIA_EMPATE, orden_contacto tie-break, banda_probabilidad bands) mirror
reference-solution/logic_priorizacion.py and reference-solution/interpretacion.py
exactly, since later PRs assert parity against that reference behavior.
"""

from __future__ import annotations

import pytest

from skills import (
    CitationMissing,
    SkillContext,
    SkillResult,
    Thresholds,
    ThresholdCitation,
    banda_probabilidad,
    orden_contacto,
    tier_prioridad,
)


class TestThresholds:
    def test_is_frozen(self):
        thresholds = Thresholds()
        with pytest.raises(Exception):
            thresholds.umbral_alto = 0.99  # type: ignore[misc]

    def test_default_values_match_business_rules(self):
        thresholds = Thresholds()
        assert thresholds.cluster_alta_conversion == 2
        assert thresholds.umbral_alto == 0.70
        assert thresholds.umbral_medio == 0.30
        assert thresholds.tolerancia_empate == 0.01


class TestSkillContext:
    def test_requires_db_path(self):
        with pytest.raises(TypeError):
            SkillContext()  # type: ignore[call-arg]

    def test_constructs_with_explicit_db_path(self):
        ctx = SkillContext(db_path="some/path.db")
        assert ctx.db_path == "some/path.db"
        assert ctx.thresholds == Thresholds()


class TestSkillResult:
    def test_raises_citation_missing_when_tier_row_has_no_citation(self):
        with pytest.raises(CitationMissing):
            SkillResult(
                skill="listar_leads_priorizados",
                rows=[{"IDPROSPECTO": 1, "tier_prioridad": "Alto"}],
                citation=None,
            )

    def test_accepts_tier_row_when_citation_present(self):
        citation = ThresholdCitation.from_thresholds(Thresholds())
        result = SkillResult(
            skill="listar_leads_priorizados",
            rows=[{"IDPROSPECTO": 1, "tier_prioridad": "Alto"}],
            citation=citation,
        )
        assert result.citation is citation

    def test_allows_missing_citation_when_no_tier_row(self):
        result = SkillResult(
            skill="catalogo_hobbies",
            rows=[{"hobby_id": 1, "hobby_estandar": "Lectura"}],
            citation=None,
        )
        assert result.citation is None


class TestThresholdCitationRender:
    def test_render_mentions_umbral_medio_review_pending(self):
        citation = ThresholdCitation.from_thresholds(Thresholds())
        rendered = citation.render()
        assert "UMBRAL_MEDIO" in rendered
        assert "review" in rendered.lower()

    def test_render_includes_threshold_values(self):
        citation = ThresholdCitation.from_thresholds(Thresholds())
        rendered = citation.render()
        assert "0.70" in rendered
        assert "0.30" in rendered


TIER_PRIORIDAD_CASES = [
    # (cluster, probabilidad_compra, expected_tier)
    (2, 0.70, "Alto"),  # boundary: exactly UMBRAL_ALTO on the alta-conversion cluster
    (2, 0.95, "Alto"),
    (2, 0.699999, "Medio"),  # just under UMBRAL_ALTO stays Medio (Cluster 2 doesn't matter here)
    (1, 0.95, "Medio"),  # high probability but wrong cluster -> never Alto
    (0, 0.99, "Medio"),
    (2, 0.30, "Medio"),  # boundary: exactly UMBRAL_MEDIO
    (1, 0.30, "Medio"),
    (2, 0.29999, "Bajo"),  # just under UMBRAL_MEDIO
    (0, 0.0, "Bajo"),
    (1, 0.10, "Bajo"),
]


class TestTierPrioridad:
    @pytest.mark.parametrize("cluster,probabilidad_compra,expected", TIER_PRIORIDAD_CASES)
    def test_tier_prioridad_matches_reference_boundaries(self, cluster, probabilidad_compra, expected):
        assert tier_prioridad(cluster, probabilidad_compra) == expected

    def test_tier_prioridad_respects_custom_thresholds(self):
        custom = Thresholds(cluster_alta_conversion=1, umbral_alto=0.5, umbral_medio=0.2)
        assert tier_prioridad(1, 0.5, custom) == "Alto"
        assert tier_prioridad(2, 0.5, custom) == "Medio"
        assert tier_prioridad(1, 0.1, custom) == "Bajo"


class TestOrdenContacto:
    def test_ranks_by_tier_then_probability_descending(self):
        leads = [
            {"IDPROSPECTO": 1, "Cluster": 2, "Probabilidad_Compra": 0.95},
            {"IDPROSPECTO": 2, "Cluster": 2, "Probabilidad_Compra": 0.71},
            {"IDPROSPECTO": 3, "Cluster": 1, "Probabilidad_Compra": 0.10},
        ]
        ranked = orden_contacto(leads)
        tiers = [r["tier_prioridad"] for r in ranked]
        ids = [r["IDPROSPECTO"] for r in ranked]
        assert tiers == ["Alto", "Alto", "Bajo"]
        assert ids == [1, 2, 3]
        assert ranked[0]["orden_contacto"] == 1
        assert ranked[1]["orden_contacto"] == 2
        assert ranked[2]["orden_contacto"] == 1  # per-tier counter resets for "Bajo"

    def test_within_tier_orders_by_probability_descending(self):
        leads = [
            {"IDPROSPECTO": 10, "Cluster": 0, "Probabilidad_Compra": 0.10},
            {"IDPROSPECTO": 11, "Cluster": 0, "Probabilidad_Compra": 0.29},
            {"IDPROSPECTO": 12, "Cluster": 0, "Probabilidad_Compra": 0.05},
        ]
        ranked = orden_contacto(leads)
        assert [r["IDPROSPECTO"] for r in ranked] == [11, 10, 12]
        assert [r["orden_contacto"] for r in ranked] == [1, 2, 3]

    def test_exact_probability_tie_breaks_by_idprospecto_ascending(self):
        leads = [
            {"IDPROSPECTO": 5, "Cluster": 0, "Probabilidad_Compra": 0.10},
            {"IDPROSPECTO": 2, "Cluster": 0, "Probabilidad_Compra": 0.10},
            {"IDPROSPECTO": 8, "Cluster": 0, "Probabilidad_Compra": 0.10},
        ]
        ranked = orden_contacto(leads)
        assert [r["IDPROSPECTO"] for r in ranked] == [2, 5, 8]

    def test_preserves_original_lead_fields(self):
        leads = [{"IDPROSPECTO": 1, "Cluster": 2, "Probabilidad_Compra": 0.9, "Hobbies_Estandar": "Lectura"}]
        ranked = orden_contacto(leads)
        assert ranked[0]["Hobbies_Estandar"] == "Lectura"

    def test_matches_reference_solution_ordering(self):
        # Mirrors reference-solution/logic_priorizacion.py::orden_contacto exactly:
        # global sort key is (tier_order, -Probabilidad_Compra, IDPROSPECTO).
        leads = [
            {"IDPROSPECTO": 3, "Cluster": 2, "Probabilidad_Compra": 0.80},
            {"IDPROSPECTO": 1, "Cluster": 1, "Probabilidad_Compra": 0.50},
            {"IDPROSPECTO": 2, "Cluster": 0, "Probabilidad_Compra": 0.05},
        ]
        ranked = orden_contacto(leads)
        assert [r["IDPROSPECTO"] for r in ranked] == [3, 1, 2]
        assert [r["tier_prioridad"] for r in ranked] == ["Alto", "Medio", "Bajo"]


BANDA_PROBABILIDAD_CASES = [
    (0.95, "Alta"),
    (0.70, "Alta"),  # boundary: exactly UMBRAL_ALTO
    (0.699999, "Media"),
    (0.30, "Media"),  # boundary: exactly UMBRAL_MEDIO
    (0.29999, "Baja"),
    (0.0, "Baja"),
]


class TestBandaProbabilidad:
    @pytest.mark.parametrize("probabilidad_compra,expected_prefix", BANDA_PROBABILIDAD_CASES)
    def test_banda_probabilidad_matches_reference_boundaries(self, probabilidad_compra, expected_prefix):
        assert banda_probabilidad(probabilidad_compra).startswith(expected_prefix)

    def test_banda_probabilidad_reuses_tier_prioridad_thresholds(self):
        # Same cuts as tier_prioridad (0.70/0.30) per reference-solution/interpretacion.py.
        assert banda_probabilidad(0.95) == "Alta (>= 0.70)"
        assert banda_probabilidad(0.50) == "Media (0.30-0.70)"
        assert banda_probabilidad(0.10) == "Baja (< 0.30)"
