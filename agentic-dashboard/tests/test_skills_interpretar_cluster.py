"""Unit tests for `skills.py::interpretar_cluster` (PR8).

Table-driven parity check against `reference-solution/interpretacion.py`'s
`CLUSTER_LABELS` / `CLUSTER_DESCRIPTIONS`: same values, same out-of-range
fallback. `interpretar_cluster` is registered as the 6th skill in the
closed `SKILLS` registry (see `test_skills_registry.py`); this file only
covers the pure function's own contract, including the calling-convention
guardrail (`ctx` first, even though the function never touches
`ctx.db_path`) documented in its docstring.
"""

from __future__ import annotations

import inspect

import pytest

from skills import SkillContext, SkillResult, interpretar_cluster

# (cluster, expected_label, expected_description_substring)
INTERPRETAR_CLUSTER_CASES = [
    (0, "Salario alto, conversión baja", "29 leads"),
    (1, "Maduro, baja urgencia de compra", "250 leads"),
    (2, "Alto interés, alta probabilidad de compra", "343 leads"),
    (99, "Cluster 99 (sin perfil documentado)", None),
]


class TestInterpretarCluster:
    @pytest.mark.parametrize(
        "cluster,expected_label,expected_description_substring",
        INTERPRETAR_CLUSTER_CASES,
    )
    def test_matches_reference_solution_labels(
        self, cluster, expected_label, expected_description_substring
    ):
        # db_path is never touched by this skill (pure dict lookup), so an
        # obviously-invalid path proves that.
        ctx = SkillContext(db_path="unused/for/this/skill.db")
        result = interpretar_cluster(ctx, cluster=cluster)

        assert isinstance(result, SkillResult)
        assert result.skill == "interpretar_cluster"
        assert result.citation is None
        row = result.rows[0]
        assert row["cluster"] == cluster
        assert row["label"] == expected_label
        if expected_description_substring is not None:
            assert expected_description_substring in row["description"]

    def test_unknown_cluster_never_raises(self):
        ctx = SkillContext(db_path="unused/for/this/skill.db")
        result = interpretar_cluster(ctx, cluster=-1)
        assert result.rows[0]["label"] == "Cluster -1 (sin perfil documentado)"

    def test_accepts_ctx_as_first_positional_parameter(self):
        # Calling-convention guardrail: agent_harness.py invokes every
        # registered skill uniformly as `skill_fn(ctx, **validated_args)`,
        # so interpretar_cluster must accept ctx first even though its own
        # implementation never reads ctx.db_path.
        params = list(inspect.signature(interpretar_cluster).parameters)
        assert params[0] == "ctx"
        assert "cluster" in params
