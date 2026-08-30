"""P0-F7.9D7.6.1 — compatibility guard for the sealed retire-status CAS.

D7.3/D7.5 preserve the exact observed active status (``active`` or ``ativo``)
for the duplicate-retirement operation. The initial D7.6 validator accidentally
required only the synthetic legacy token ``ativo_or_active`` used by older
fixtures. This shim keeps the authorized D7.5 manifest immutable, accepts only
an exact active status for the retirement operation, requires rollback to the
same exact status, and preserves that exact value in the generated CAS filter.

All other validation and writer generation remain delegated to the reviewed
D7.6 builder. This module is local-only and does not execute the writer.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any, Mapping

BASE_BUILDER_PATH = Path(__file__).with_name(
    "build_p0f7_9d76_authorized_revised_executor_js.py"
)
_spec = importlib.util.spec_from_file_location("p0f7_9d76_base_builder", BASE_BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D761_BASE_BUILDER_IMPORT_FAILED")
d76 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d76)

_BASE_VALIDATE_OPERATION = d76._validate_operation


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _validate_operation_compatible(
    op: Mapping[str, Any], expected_index: int
) -> dict[str, Any]:
    """Accept the exact active status sealed by D7.3/D7.5 for operation 22.

    The base D7.6 validator remains authoritative for every other invariant.
    For an exact ``active``/``ativo`` CAS, validation is performed through the
    base validator using its legacy alias and then the exact sealed value is
    restored before writer materialization. This makes the runtime CAS stricter,
    not broader.
    """

    if _norm(op.get("operation_type")) != "RETIRE_DUPLICATE_ASSIGNMENT":
        return _BASE_VALIDATE_OPERATION(op, expected_index)

    cas = dict(op.get("cas_expected") or {})
    rollback = dict(op.get("rollback_set_fields") or {})
    status_raw = _norm(cas.get("status"))
    status = status_raw.lower()

    # Preserve support for the previously tested legacy alias without changing
    # its existing semantics. The real sealed manifest uses an exact status.
    if status == "ativo_or_active":
        return _BASE_VALIDATE_OPERATION(op, expected_index)

    if status not in d76.ACTIVE_STATUSES:
        raise ValueError("P0F7_9D76_RETIRE_STATUS_CAS_INVALID")

    rollback_status = _norm(rollback.get("status"))
    if rollback_status.lower() != status:
        raise ValueError("P0F7_9D761_RETIRE_ROLLBACK_STATUS_MISMATCH")

    patched = copy.deepcopy(dict(op))
    patched_cas = dict(cas)
    patched_cas["status"] = "ativo_or_active"
    patched["cas_expected"] = patched_cas

    validated = _BASE_VALIDATE_OPERATION(patched, expected_index)
    validated["cas_expected"]["status"] = status_raw
    return validated


# build_executor() resolves this module-global symbol inside the imported base
# module at runtime. Replacing only this validator preserves the writer itself.
d76._validate_operation = _validate_operation_compatible


def main() -> None:
    d76.main()


if __name__ == "__main__":
    main()
