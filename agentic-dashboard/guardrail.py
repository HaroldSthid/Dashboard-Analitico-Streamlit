"""Post-generation structural guardrail for the agent harness (Phase 5).

Phase 5 scope only: `enforce_comment_guardrail` and `COMMENT_GUARDRAIL_REFUSAL`.
This module has no I/O and no dependency on `sqlite3`, `agent_harness.py`, or
`skills.py` at runtime — it is a pure structural check over an already-built
`AgentAnswer`. See tasks 5.1/5.2 in `sdd/agentic-dashboard/tasks`.

Why this exists: `dim_comentario` (comment categories) is a vocabulary-only
reference catalog with no per-lead join key — see `skills.py`'s
`catalogo_categorias_comentario` docstring. `agent_harness.py`'s Phase-4
`_is_forbidden_intent` guard only catches a *hallucinated tool call* that
tries to reach for that join. It cannot catch the model simply asserting, in
plain prose or in a rendered table, that a specific lead (an `IDPROSPECTO`)
is associated with a specific comment category — whether that assertion came
from a real tool result the model then over-interpreted, or from the model
answering purely from its own (hallucinated) knowledge with no tool call at
all. `enforce_comment_guardrail` is the final structural checkpoint that
catches both: it inspects the finished answer's text and tables for a
lead-id + comment-category-term co-occurrence and, if found, discards the
entire answer in favor of a fixed refusal message.

Design choice for an invented/near-miss category term (case (e) in the task
list): a category term the model invents is, by definition, *not* found in
`vocabulary`, so the term-matching rule alone cannot flag it — that would be
a false-negative escape hatch. Rather than trying to fuzzy-match arbitrary
invented strings against the known vocabulary (which risks both false
negatives for genuinely novel wording and false positives for unrelated
text), this module takes the simpler, more conservative structural rule
described in the task: for **table rows only**, treat any row that combines
a value from `lead_ids` with a `categoria`-labeled key holding non-numeric
text as a match, regardless of whether that text is a real vocabulary term.
This closes the "invented category" gap structurally (a fabricated
`categoria_comentario` value in a lead-linked row is exactly the shape of
row this guardrail exists to catch) without requiring free-text fuzzy
matching, which would be its own source of false positives/negatives. This
conservative rule intentionally does not extend to free text (case (b)):
free-text matching still requires a genuine `vocabulary` term, since without
a `categoria`-style structural label there is no reliable signal that a
given word in prose is "category-shaped" at all.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only, never at runtime
    from agent_harness import AgentAnswer

# Roughly how close (in normalized-text character positions) a lead id and a
# vocabulary term must be to count as "in the same breath". This is a loose,
# documented approximation ("roughly a 200-character window" per the task),
# implemented as the absolute distance between each match's start position —
# simpler than true interval-overlap distance and conservative enough to
# catch same-sentence / same-paragraph co-occurrence without requiring exact
# span geometry.
_TEXT_WINDOW_CHARS = 200

COMMENT_GUARDRAIL_REFUSAL = (
    "I can't answer that: it would combine an individual lead identifier "
    "with a comment-category term. `dim_comentario` is a vocabulary-only "
    "reference catalog of comment categories — it has no per-lead join key, "
    "and it is never joined to `tbl_leads` or to any individual lead "
    "identifier, in any skill. What IS allowed instead: ask for the "
    "comment-category catalog on its own (no lead reference), or ask for a "
    "specific lead's tier/priority information separately (no comment "
    "category reference)."
)


def _normalize(text: str) -> str:
    """Lowercase + accent-strip for matching (NFKD, drop combining marks)."""

    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


def _find_id_positions(haystack: str, lead_ids: frozenset[int]) -> list[int]:
    positions: list[int] = []
    for lead_id in lead_ids:
        pattern = re.compile(rf"(?<!\d){re.escape(str(lead_id))}(?!\d)")
        positions.extend(match.start() for match in pattern.finditer(haystack))
    return positions


def _find_term_positions(haystack: str, vocabulary: tuple[str, ...]) -> list[int]:
    positions: list[int] = []
    for term in vocabulary:
        normalized_term = _normalize(term)
        if not normalized_term:
            continue
        pattern = re.compile(rf"\b{re.escape(normalized_term)}\b")
        positions.extend(match.start() for match in pattern.finditer(haystack))
    return positions


def _text_has_forbidden_combination(
    text: str, lead_ids: frozenset[int], vocabulary: tuple[str, ...]
) -> bool:
    if not lead_ids or not text or not vocabulary:
        return False

    normalized = _normalize(text)
    id_positions = _find_id_positions(normalized, lead_ids)
    if not id_positions:
        return False
    term_positions = _find_term_positions(normalized, vocabulary)
    if not term_positions:
        return False

    return any(
        abs(id_pos - term_pos) <= _TEXT_WINDOW_CHARS
        for id_pos in id_positions
        for term_pos in term_positions
    )


# Row keys that identify a lead (never a comment/hobby id, which also
# happen to be small integers and must not be mistaken for a lead id).
_LEAD_ID_KEY_MARKERS = ("idprospecto", "lead_id", "leadid")


def _row_has_lead_id_value(row: dict, lead_ids: frozenset[int]) -> bool:
    for key, value in row.items():
        key_lower = str(key).lower()
        if not any(marker in key_lower for marker in _LEAD_ID_KEY_MARKERS):
            continue
        try:
            if int(value) in lead_ids:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _row_matches_vocabulary_term(row: dict, vocabulary: tuple[str, ...]) -> bool:
    for value in row.values():
        if not isinstance(value, str):
            continue
        normalized_value = _normalize(value)
        for term in vocabulary:
            normalized_term = _normalize(term)
            if normalized_term and re.search(
                rf"\b{re.escape(normalized_term)}\b", normalized_value
            ):
                return True
    return False


def _row_has_category_labeled_text(row: dict) -> bool:
    """Conservative fallback for an invented/unknown category term (case
    (e)): any `categoria`-labeled key whose value is non-numeric text counts
    as a category-shaped value even when it is not a known vocabulary term.
    See the module docstring for the rationale."""

    for key, value in row.items():
        if "categoria" not in str(key).lower():
            continue
        if isinstance(value, str) and value.strip() and not value.strip().isdigit():
            return True
    return False


def _table_has_forbidden_row(
    tables: list[dict], lead_ids: frozenset[int], vocabulary: tuple[str, ...]
) -> bool:
    if not lead_ids:
        return False

    for row in tables:
        if not isinstance(row, dict):
            continue
        if not _row_has_lead_id_value(row, lead_ids):
            continue
        if _row_matches_vocabulary_term(row, vocabulary) or _row_has_category_labeled_text(row):
            return True
    return False


def enforce_comment_guardrail(
    answer: "AgentAnswer",
    lead_ids: frozenset[int],
    vocabulary: tuple[str, ...],
) -> "AgentAnswer":
    """Structural post-generation validator (tasks 5.1/5.2).

    Pure function, no I/O. Inspects `answer.tables` and `answer.text` for a
    forbidden lead-id + comment-category-term combination:

    - A single structured row in `answer.tables` combines a value from
      `lead_ids` with either a `vocabulary` term (case-insensitive,
      word-boundary match) or any `categoria`-labeled non-numeric value
      (closes the invented-category gap — see module docstring).
    - `answer.text` contains both an id from `lead_ids` and a term from
      `vocabulary` (accent-normalized, case-insensitive, word-boundary
      match) within roughly a 200-character window.

    If either check matches, the entire answer is replaced with
    `AgentAnswer(text=COMMENT_GUARDRAIL_REFUSAL, refused_by="comment_guardrail")`.
    Otherwise the original `answer` is returned unchanged (same object).
    """

    # Local import: `AgentAnswer` lives in `agent_harness.py`, which imports
    # this module at module load time. By the time this function actually
    # runs, `agent_harness` has finished importing, so this resolves from
    # `sys.modules` with no circular-import error. See the `TYPE_CHECKING`
    # import above for the (never-executed-at-runtime) static type hint.
    from agent_harness import AgentAnswer

    if _table_has_forbidden_row(answer.tables, lead_ids, vocabulary) or _text_has_forbidden_combination(
        answer.text, lead_ids, vocabulary
    ):
        return AgentAnswer(text=COMMENT_GUARDRAIL_REFUSAL, refused_by="comment_guardrail")

    return answer
