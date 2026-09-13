"""Unit tests for the Phase 5 post-generation structural guardrail.

Phase 5 scope: `enforce_comment_guardrail`, `COMMENT_GUARDRAIL_REFUSAL`. Pure
function tests only — `lead_ids` and `vocabulary` are passed directly by
each test, independent of any real `Harness`/`skills.py` wiring (that
wiring is covered separately in `test_harness.py`).

See tasks 5.1/5.2 in `sdd/agentic-dashboard/tasks`.
"""

from __future__ import annotations

from agent_harness import AgentAnswer
from guardrail import COMMENT_GUARDRAIL_REFUSAL, enforce_comment_guardrail

VOCABULARY = ("Queja", "Elogio", "Consulta")


class TestTableRowCombination:
    def test_table_row_combining_lead_id_and_category_term_is_refused(self):
        answer = AgentAnswer(
            text="Aqui esta el detalle.",
            tables=[{"IDPROSPECTO": 1, "categoria_comentario": "Queja"}],
        )

        result = enforce_comment_guardrail(answer, frozenset({1, 2, 3}), VOCABULARY)

        assert result.refused_by == "comment_guardrail"
        assert result.text == COMMENT_GUARDRAIL_REFUSAL

    def test_table_row_with_lead_id_only_passes_through(self):
        answer = AgentAnswer(
            text="Aqui esta el detalle.",
            tables=[{"IDPROSPECTO": 1, "tier_prioridad": "Alto"}],
        )

        result = enforce_comment_guardrail(answer, frozenset({1, 2, 3}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None

    def test_table_row_with_category_term_only_passes_through(self):
        answer = AgentAnswer(
            text="Catalogo.",
            tables=[{"comentario_id": 1, "categoria_comentario": "Queja"}],
        )

        result = enforce_comment_guardrail(answer, frozenset({1, 2, 3}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None


class TestTextWindowCombination:
    def test_text_combining_lead_id_and_category_term_within_window_is_refused(self):
        padding = "x" * 100
        text = f"El lead 7 {padding} dejo una Queja sobre el producto."

        answer = AgentAnswer(text=text)

        result = enforce_comment_guardrail(answer, frozenset({7}), VOCABULARY)

        assert result.refused_by == "comment_guardrail"
        assert result.text == COMMENT_GUARDRAIL_REFUSAL

    def test_text_combination_beyond_window_passes_through(self):
        padding = "x" * 250
        text = f"El lead 3 {padding} menciono una Queja en otro contexto."

        answer = AgentAnswer(text=text)

        result = enforce_comment_guardrail(answer, frozenset({3}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None

    def test_accent_and_case_insensitive_matching(self):
        text = "El lead 2 genero una RECLAMACION fuerte."

        answer = AgentAnswer(text=text)

        result = enforce_comment_guardrail(answer, frozenset({2}), ("Reclamación",))

        assert result.refused_by == "comment_guardrail"


class TestPassthroughCases:
    def test_catalog_only_answer_no_lead_id_passes_through_unchanged(self):
        answer = AgentAnswer(
            text="Las categorias de comentario disponibles son Queja, Elogio y Consulta."
        )

        result = enforce_comment_guardrail(answer, frozenset({1, 2, 3}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None

    def test_leads_only_answer_no_category_term_passes_through_unchanged(self):
        answer = AgentAnswer(text="El lead 1 tiene tier Alto y probabilidad 0.95.")

        result = enforce_comment_guardrail(answer, frozenset({1, 2, 3}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None

    def test_empty_lead_ids_never_matches(self):
        answer = AgentAnswer(
            text="Alguien menciono una Queja sobre el lead 1.",
            tables=[{"IDPROSPECTO": 1, "categoria_comentario": "Queja"}],
        )

        result = enforce_comment_guardrail(answer, frozenset(), VOCABULARY)

        assert result is answer
        assert result.refused_by is None


class TestInventedCategoryTerm:
    def test_invented_category_term_in_table_row_is_still_refused(self):
        # "Reclamo Grave" is NOT in VOCABULARY -- an invented/near-miss
        # category the model made up. The conservative categoria-labeled-key
        # fallback must still catch it (see guardrail.py module docstring).
        answer = AgentAnswer(
            text="Resumen.",
            tables=[{"IDPROSPECTO": 4, "categoria_comentario": "Reclamo Grave"}],
        )

        result = enforce_comment_guardrail(answer, frozenset({4}), VOCABULARY)

        assert result.refused_by == "comment_guardrail"

    def test_numeric_categoria_labeled_value_does_not_false_positive(self):
        answer = AgentAnswer(
            text="Resumen.",
            tables=[{"IDPROSPECTO": 4, "categoria_id": 5}],
        )

        result = enforce_comment_guardrail(answer, frozenset({4}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None

    def test_invented_category_term_in_free_text_without_structural_label_passes_through(self):
        # Free text has no "categoria"-labeled structural signal, so the
        # conservative fallback (table-only, per design) does not apply
        # here; only a genuine vocabulary term triggers the text-window
        # check. See guardrail.py module docstring for the rationale.
        answer = AgentAnswer(text="El lead 4 tuvo un Reclamo Grave la semana pasada.")

        result = enforce_comment_guardrail(answer, frozenset({4}), VOCABULARY)

        assert result is answer
        assert result.refused_by is None


class TestRefusalMessageContent:
    def test_refusal_names_dim_comentario_and_missing_join_key(self):
        assert "dim_comentario" in COMMENT_GUARDRAIL_REFUSAL
        assert "join key" in COMMENT_GUARDRAIL_REFUSAL.lower()

    def test_refusal_states_what_is_allowed_instead(self):
        lowered = COMMENT_GUARDRAIL_REFUSAL.lower()
        assert "catalog" in lowered
        assert "separately" in lowered or "on its own" in lowered
