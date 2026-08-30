"""P0-F7.9D7.6.3 — mongosh projection compatibility for the authorized executor.

The D7.6 writer template was generated using Node-driver style
``findOne(filter, {projection: {...}})`` calls. In mongosh, ``findOne`` uses
``findOne(query, projection, options)``; the second positional argument is the
projection document itself. The previous shape therefore reached mongosh as a
projection containing a nested ``projection`` field and failed before the
first write.

This compatibility layer preserves the exact D7.6.1 manifest validation and
write semantics. It changes only the generated read projections used by the
runtime safety checks. No database/network access is performed by this module.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

D761_BUILDER_PATH = Path(__file__).with_name(
    "build_p0f7_9d761_authorized_revised_executor_js.py"
)
_spec = importlib.util.spec_from_file_location("p0f7_9d761_builder", D761_BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D763_D761_BUILDER_IMPORT_FAILED")
d761 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d761)

# D7.6.1 delegates writer generation to the reviewed D7.6 base module. Patch
# only the mongosh projection call shape, and fail closed if the reviewed
# template drifts from the exact occurrences we expect.
_TEMPLATE = d761.d76._JS_TEMPLATE
_REPLACEMENTS = (
    (
        "{projection:{_id:0,id:1}}",
        "{_id:0,id:1}",
        1,
    ),
    (
        "{projection:{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}}",
        "{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}",
        4,
    ),
    (
        "{projection:{_id:0,id:1,status:1,course_id:1,carga_horaria_semanal:1}}",
        "{_id:0,id:1,status:1,course_id:1,carga_horaria_semanal:1}",
        1,
    ),
)

for _old, _new, _expected_count in _REPLACEMENTS:
    _actual_count = _TEMPLATE.count(_old)
    if _actual_count != _expected_count:
        raise RuntimeError(
            "P0F7_9D763_PROJECTION_TEMPLATE_DRIFT:"
            f"expected={_expected_count}:actual={_actual_count}:token={_old}"
        )
    _TEMPLATE = _TEMPLATE.replace(_old, _new)

if "{projection:" in _TEMPLATE:
    raise RuntimeError("P0F7_9D763_UNPATCHED_MONGOSH_PROJECTION")

# build_executor() resolves this module-global template inside the imported
# D7.6 base module, so writer semantics remain otherwise identical.
d761.d76._JS_TEMPLATE = _TEMPLATE


def main() -> None:
    d761.main()


if __name__ == "__main__":
    main()
