"""Agentic dashboard skills: contracts and pure business-rule functions.

Phase 1 scope only (contracts + pure functions). No skill implementations,
no SQLite access, and no registry live here yet — those are later PRs
(PR2+). See tasks 1.1-1.14 in `sdd/agentic-dashboard/tasks`.

Business-rule thresholds and the `tier_prioridad` / `orden_contacto` /
`banda_probabilidad` boundary logic are re-implemented here to mirror
`reference-solution/logic_priorizacion.py` and
`reference-solution/interpretacion.py` exactly, since later PRs assert
parity against that reference behavior. `reference-solution/` is read-only
context, not an import target (its flat `from logic_priorizacion import
...` does not resolve from a sibling `agentic-dashboard/` package).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Thresholds:
    """Business thresholds for lead prioritization.

    `umbral_medio` is an analyst-invented business threshold (not derived
    from the original spec) and ships as `review_pending` by default — see
    `reference-solution/logic_priorizacion.py` decision #3.
    """

    cluster_alta_conversion: int = 2
    umbral_alto: float = 0.70
    umbral_medio: float = 0.30
    tolerancia_empate: float = 0.01
    review_pending: tuple[str, ...] = ("umbral_medio",)


@dataclass
class SkillContext:
    """Execution context passed to every skill.

    `db_path` is required with no fallback: skills must never guess a
    database location relative to `__file__` or the current working
    directory.
    """

    db_path: str
    thresholds: Thresholds = field(default_factory=Thresholds)


class CitationMissing(Exception):
    """Raised when a `SkillResult` row exposes a business-threshold-derived
    field (e.g. `tier_prioridad`) without an accompanying citation."""


@dataclass(frozen=True)
class ThresholdCitation:
    """Human-readable record of which thresholds produced a skill's rows."""

    cluster_alta_conversion: int
    umbral_alto: float
    umbral_medio: float
    tolerancia_empate: float
    review_pending: tuple[str, ...] = ()

    @classmethod
    def from_thresholds(cls, thresholds: Thresholds) -> "ThresholdCitation":
        return cls(
            cluster_alta_conversion=thresholds.cluster_alta_conversion,
            umbral_alto=thresholds.umbral_alto,
            umbral_medio=thresholds.umbral_medio,
            tolerancia_empate=thresholds.tolerancia_empate,
            review_pending=thresholds.review_pending,
        )

    def render(self) -> str:
        rendered = (
            f"Thresholds used: CLUSTER_ALTA_CONVERSION={self.cluster_alta_conversion}, "
            f"UMBRAL_ALTO={self.umbral_alto:.2f}, UMBRAL_MEDIO={self.umbral_medio:.2f}, "
            f"TOLERANCIA_EMPATE={self.tolerancia_empate:.2f}."
        )
        if "umbral_medio" in self.review_pending:
            rendered += (
                " Note: UMBRAL_MEDIO is an analyst-invented business threshold, "
                "not derived from the original spec, and is pending review."
            )
        return rendered


# Fields whose presence in a row means the row was produced using business
# thresholds and therefore requires a citation.
_CITATION_REQUIRING_FIELDS = ("tier_prioridad",)


@dataclass
class SkillResult:
    """Envelope returned by every skill: its rows plus an optional citation.

    `__post_init__` enforces that any row carrying a threshold-derived field
    (currently `tier_prioridad`) is never returned without a citation.
    """

    skill: str
    rows: list[dict]
    citation: ThresholdCitation | None

    def __post_init__(self) -> None:
        if self.citation is None and any(
            field_name in row for row in self.rows for field_name in _CITATION_REQUIRING_FIELDS
        ):
            raise CitationMissing(
                f"SkillResult for '{self.skill}' has rows with threshold-derived fields "
                f"{_CITATION_REQUIRING_FIELDS} but no citation was provided."
            )


def tier_prioridad(
    cluster: int,
    probabilidad_compra: float,
    thresholds: Thresholds = Thresholds(),
) -> str:
    """Alto / Medio / Bajo per Cluster + Probabilidad_Compra.

    Mirrors reference-solution/logic_priorizacion.py::tier_prioridad:
    - Alto: cluster of highest historical conversion AND
      probabilidad_compra >= umbral_alto.
    - Medio: everything else with probabilidad_compra >= umbral_medio
      (regardless of cluster).
    - Bajo: everything else.
    """

    if cluster == thresholds.cluster_alta_conversion and probabilidad_compra >= thresholds.umbral_alto:
        return "Alto"
    if probabilidad_compra >= thresholds.umbral_medio:
        return "Medio"
    return "Bajo"


def orden_contacto(
    leads: list[dict],
    thresholds: Thresholds = Thresholds(),
) -> list[dict]:
    """Rank leads for contact order (1 = first) within each tier.

    Pure ranking function operating on plain dicts (not yet wired to a
    skill). Mirrors reference-solution/logic_priorizacion.py::orden_contacto:
    global sort key is (tier order, probabilidad_compra descending,
    IDPROSPECTO ascending as the final deterministic tie-break). Each
    returned dict is the original lead dict plus `tier_prioridad` and
    `orden_contacto`.
    """

    tier_orden = {"Alto": 0, "Medio": 1, "Bajo": 2}
    enriquecidos = [
        (tier_prioridad(lead["Cluster"], lead["Probabilidad_Compra"], thresholds), lead)
        for lead in leads
    ]

    enriquecidos.sort(
        key=lambda tl: (
            tier_orden[tl[0]],
            -tl[1]["Probabilidad_Compra"],
            tl[1]["IDPROSPECTO"],
        )
    )

    resultado: list[dict] = []
    contador_por_tier = {"Alto": 0, "Medio": 0, "Bajo": 0}
    for t, lead in enriquecidos:
        contador_por_tier[t] += 1
        resultado.append(
            {
                **lead,
                "tier_prioridad": t,
                "orden_contacto": contador_por_tier[t],
            }
        )
    return resultado


def banda_probabilidad(probabilidad_compra: float) -> str:
    """Confidence band for Probabilidad_Compra, same cuts as tier_prioridad.

    Mirrors reference-solution/interpretacion.py::banda_probabilidad exactly
    (uses the default Thresholds so the label never contradicts
    tier_prioridad's own boundaries).
    """

    thresholds = Thresholds()
    if probabilidad_compra >= thresholds.umbral_alto:
        return f"Alta (>= {thresholds.umbral_alto:.2f})"
    if probabilidad_compra >= thresholds.umbral_medio:
        return f"Media ({thresholds.umbral_medio:.2f}-{thresholds.umbral_alto:.2f})"
    return f"Baja (< {thresholds.umbral_medio:.2f})"
