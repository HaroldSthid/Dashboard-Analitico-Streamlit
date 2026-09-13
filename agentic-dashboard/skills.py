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

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel


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


class SkillValidationError(Exception):
    """Raised when a skill receives an argument that fails domain validation
    (e.g. an unknown `hobby_estandar` or an unknown `IDPROSPECTO`)."""


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


# ---------------------------------------------------------------------------
# Phase 2: skill implementations
#
# Every skill opens its own short-lived sqlite3 connection against the
# explicit `ctx.db_path` (never a path guessed relative to `__file__`).
# `Cluster` and `Probabilidad_Compra` are read directly from `tbl_leads` and
# are never recomputed here. `dim_comentario` is NEVER joined to `tbl_leads`
# at the row level, in any skill, ever.
# ---------------------------------------------------------------------------


def _fetch_all_leads(db_path: str) -> list[dict]:
    """Read the unfiltered lead population from `tbl_leads`."""

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT IDPROSPECTO, Cluster, Probabilidad_Compra, Hobbies_Estandar "
            "FROM tbl_leads;"
        )
        rows = cur.fetchall()
    finally:
        con.close()

    return [
        {
            "IDPROSPECTO": row[0],
            "Cluster": row[1],
            "Probabilidad_Compra": row[2],
            "Hobbies_Estandar": row[3],
        }
        for row in rows
    ]


def _validate_hobby_estandar(db_path: str, hobby_estandar: str) -> None:
    """Raise `SkillValidationError` unless `hobby_estandar` exists in `dim_hobby`."""

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM dim_hobby WHERE hobby_estandar = ?;",
            (hobby_estandar,),
        )
        found = cur.fetchone() is not None
    finally:
        con.close()

    if not found:
        raise SkillValidationError(f"Unknown hobby_estandar: {hobby_estandar!r}")


def listar_leads_priorizados(
    ctx: SkillContext,
    hobby_estandar: str | None = None,
    tier: str | None = None,
    limit: int = 50,
) -> SkillResult:
    """List leads ranked by contact priority.

    Ranks the FULL lead population with `orden_contacto` before any hobby or
    tier filtering, then filters the already-ranked result set in-memory on
    an exact `Hobbies_Estandar` / `tier_prioridad` match. This preserves the
    `orden_contacto` values computed from the full population — filtering is
    never a SQL JOIN and never re-ranks the filtered subset.
    """

    if hobby_estandar is not None:
        _validate_hobby_estandar(ctx.db_path, hobby_estandar)

    ranked = orden_contacto(_fetch_all_leads(ctx.db_path), ctx.thresholds)

    if hobby_estandar is not None:
        ranked = [row for row in ranked if row["Hobbies_Estandar"] == hobby_estandar]
    if tier is not None:
        ranked = [row for row in ranked if row["tier_prioridad"] == tier]

    ranked = ranked[:limit]

    citation = ThresholdCitation.from_thresholds(ctx.thresholds)
    return SkillResult(skill="listar_leads_priorizados", rows=ranked, citation=citation)


def explicar_tier_de_lead(ctx: SkillContext, idprospecto: int) -> SkillResult:
    """Explain the priority tier assigned to a single lead.

    Looks up exactly one lead by `IDPROSPECTO` and computes its
    `tier_prioridad` directly (no ranking against the rest of the
    population). Raises `SkillValidationError` for an unknown id.
    """

    con = sqlite3.connect(ctx.db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT IDPROSPECTO, Cluster, Probabilidad_Compra, Hobbies_Estandar "
            "FROM tbl_leads WHERE IDPROSPECTO = ?;",
            (idprospecto,),
        )
        row = cur.fetchone()
    finally:
        con.close()

    if row is None:
        raise SkillValidationError(f"Unknown idprospecto: {idprospecto!r}")

    lead = {
        "IDPROSPECTO": row[0],
        "Cluster": row[1],
        "Probabilidad_Compra": row[2],
        "Hobbies_Estandar": row[3],
        "tier_prioridad": tier_prioridad(row[1], row[2], ctx.thresholds),
    }

    citation = ThresholdCitation.from_thresholds(ctx.thresholds)
    return SkillResult(skill="explicar_tier_de_lead", rows=[lead], citation=citation)


def resumen_por_cluster(ctx: SkillContext, hobby_estandar: str | None = None) -> SkillResult:
    """Aggregate lead counts per `Cluster`, optionally filtered by hobby.

    `Cluster` is read-only and never recomputed. The optional hobby filter
    uses the same in-memory exact-match mechanism as
    `listar_leads_priorizados` (never a SQL JOIN). No `tier_prioridad` field
    is produced here, so no citation is required.
    """

    if hobby_estandar is not None:
        _validate_hobby_estandar(ctx.db_path, hobby_estandar)

    leads = _fetch_all_leads(ctx.db_path)
    if hobby_estandar is not None:
        leads = [lead for lead in leads if lead["Hobbies_Estandar"] == hobby_estandar]

    conteo: dict[int, int] = {}
    for lead in leads:
        conteo[lead["Cluster"]] = conteo.get(lead["Cluster"], 0) + 1

    rows = [
        {"Cluster": cluster, "cantidad_leads": cantidad}
        for cluster, cantidad in sorted(conteo.items())
    ]
    return SkillResult(skill="resumen_por_cluster", rows=rows, citation=None)


def catalogo_hobbies(ctx: SkillContext) -> SkillResult:
    """List the standardized hobby vocabulary (`dim_hobby`).

    Vocabulary only — no `tier_prioridad` rows, so no citation is required.
    """

    con = sqlite3.connect(ctx.db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT hobby_id, hobby_estandar FROM dim_hobby;")
        rows = cur.fetchall()
    finally:
        con.close()

    result_rows = [{"hobby_id": row[0], "hobby_estandar": row[1]} for row in rows]
    return SkillResult(skill="catalogo_hobbies", rows=result_rows, citation=None)


def catalogo_categorias_comentario(ctx: SkillContext) -> SkillResult:
    """List comment category vocabulary (`dim_comentario`).

    Reference catalog only: a single-table `SELECT DISTINCT` against
    `dim_comentario`, NEVER joined to `tbl_leads`. Rows never carry an
    `IDPROSPECTO` column or any other per-lead linkage.
    """

    con = sqlite3.connect(ctx.db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT comentario_id, categoria_comentario FROM dim_comentario;")
        rows = cur.fetchall()
    finally:
        con.close()

    result_rows = [{"comentario_id": row[0], "categoria_comentario": row[1]} for row in rows]
    return SkillResult(skill="catalogo_categorias_comentario", rows=result_rows, citation=None)


# ---------------------------------------------------------------------------
# Closed skills registry and TOOLS_SCHEMA
#
# Every entry's argument model uses only explicit, individually-typed
# fields (no free-form "query" / "sql" / "where" string parameter). This is
# a hard invariant: skills never accept arbitrary SQL from the caller.
# ---------------------------------------------------------------------------


class ListarLeadsPriorizadosArgs(BaseModel):
    hobby_estandar: str | None = None
    tier: str | None = None
    limit: int = 50


class ExplicarTierDeLeadArgs(BaseModel):
    idprospecto: int


class ResumenPorClusterArgs(BaseModel):
    hobby_estandar: str | None = None


class CatalogoHobbiesArgs(BaseModel):
    pass


class CatalogoCategoriasComentarioArgs(BaseModel):
    pass


SKILLS: dict[str, Callable[..., SkillResult]] = {
    "listar_leads_priorizados": listar_leads_priorizados,
    "explicar_tier_de_lead": explicar_tier_de_lead,
    "resumen_por_cluster": resumen_por_cluster,
    "catalogo_hobbies": catalogo_hobbies,
    "catalogo_categorias_comentario": catalogo_categorias_comentario,
}

_SKILL_DESCRIPTIONS: dict[str, str] = {
    "listar_leads_priorizados": (
        "List leads ranked by contact priority (orden_contacto), optionally "
        "filtered by hobby_estandar and/or tier."
    ),
    "explicar_tier_de_lead": (
        "Explain the priority tier assigned to a single lead by IDPROSPECTO."
    ),
    "resumen_por_cluster": (
        "Aggregate lead counts per Cluster, optionally filtered by hobby_estandar."
    ),
    "catalogo_hobbies": "List the standardized hobby vocabulary (dim_hobby).",
    "catalogo_categorias_comentario": (
        "List comment category vocabulary (dim_comentario) as a reference "
        "catalog — never joined or linked to individual leads."
    ),
}

_SKILL_ARGS_MODELS: dict[str, type[BaseModel]] = {
    "listar_leads_priorizados": ListarLeadsPriorizadosArgs,
    "explicar_tier_de_lead": ExplicarTierDeLeadArgs,
    "resumen_por_cluster": ResumenPorClusterArgs,
    "catalogo_hobbies": CatalogoHobbiesArgs,
    "catalogo_categorias_comentario": CatalogoCategoriasComentarioArgs,
}

# Wrapped as {"type": "function", "function": {...}} per the OpenAI/
# OpenRouter/Ollama chat-completions `tools` spec. A flat {"name", ...}
# entry (the pre-fix shape) is silently ignored by real providers, so no
# live model could ever call a tool -- only caught via a real Ollama smoke
# test, since FakeGateway-based unit tests never round-trip this shape
# through an actual provider. See gateways.py's _parse_openai_completion
# for the matching (already-correct) response-side shape.
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": _SKILL_DESCRIPTIONS[name],
            "parameters": _SKILL_ARGS_MODELS[name].model_json_schema(),
        },
    }
    for name in SKILLS
]
