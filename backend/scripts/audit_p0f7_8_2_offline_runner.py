"""Official P0-F7.8.2 local runner.

This entrypoint is intentionally offline-only. It delegates parsing/report
construction to the offline core and replaces its self-inspection hook with a
resolver-contract check that has no database, Docker or SSH capability.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Mapping

CORE_PATH = Path(__file__).resolve().with_name("audit_p0f7_8_2_offline_snapshot.py")
spec = importlib.util.spec_from_file_location("p0f782_core", CORE_PATH)
core = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(core)

SNAPSHOT_PHASE = core.SNAPSHOT_PHASE
validate_snapshot = core.validate_snapshot
classify_pair_policy = core.classify_pair_policy
_expected_rank_from_p0f75 = core._expected_rank_from_p0f75


_base_course_snapshot = core._course_snapshot


def course_snapshot_with_legacy_active_semantics(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve the tri-state `active` value sealed by P0-F7.4/P0-F7.5.

    P0-F7.4 serialized legacy courses with `active=null` when the field did not
    exist. The minimal live snapshot may omit the field entirely. Those two
    representations carry the same historical information and must normalize to
    `None`; explicit `True` and `False` remain distinct and continue to trigger
    drift when they differ from the sealed state.
    """
    snapshot = _base_course_snapshot(row)
    snapshot["active"] = row.get("active")
    return snapshot


core._course_snapshot = course_snapshot_with_legacy_active_semantics


def validate_resolver_hardening_contract() -> dict:
    path = Path(core.curriculum_resolver_module.__file__).resolve()
    source = path.read_text(encoding="utf-8")
    pick = inspect.getsource(core._pick_winner)
    if "curricular_rank" not in pick or "evidence_score" not in pick:
        raise RuntimeError("P0F7_7_HARDENING_MARKERS_MISSING")
    if pick.find("curricular_rank") >= pick.find("evidence_score"):
        raise RuntimeError("P0F7_7_CURRICULAR_PRECEDENCE_NOT_CONFIRMED")

    unknown_course = core._curricular_fit(
        {"grade_levels": ["8º ANO"]},
        class_level="fundamental_anos_finais",
        class_series={"ano:8"},
    )
    if unknown_course.get("rank") != 2:
        raise RuntimeError("P0F7_7_UNKNOWN_COURSE_LEVEL_NOT_REVIEW")
    if unknown_course.get("classification") != "COURSE_LEVEL_UNKNOWN_REQUIRES_REVIEW":
        raise RuntimeError("P0F7_7_UNKNOWN_COURSE_LEVEL_CLASSIFICATION_INVALID")

    mutators = [token for token in core.MUTATOR_TOKENS if token in source]
    if mutators:
        raise RuntimeError(f"RESOLVER_READ_ONLY_GUARD_FAILED forbidden={mutators}")

    return {
        "resolver_path": str(path),
        "resolver_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "curricular_rank_precedes_evidence_score": True,
        "unknown_course_level_is_review": True,
        "resolver_mutator_surface_detected": False,
        "database_client_available_in_analyzer": False,
    }


core.validate_resolver_hardening_contract = validate_resolver_hardening_contract


def main() -> None:
    core.main()


if __name__ == "__main__":
    main()
