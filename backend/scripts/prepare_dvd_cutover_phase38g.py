"""38G-A — preflight controlado do cutover DVD, sem escrita no MongoDB.

Sequência obrigatória:
1. recalcula o manifesto 38E usando o banco atual;
2. exige o SHA-256 aprovado e a quantidade aprovada de vínculos;
3. gera backup local das fontes e do estado anterior dos recursos afetados;
4. grava checksums dos arquivos do backup;
5. encerra sem criar/habilitar qualquer teacher_class_assignment.

A etapa 38G-B (apply) só pode existir depois de um preflight de produção aprovado.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts.audit_dvd_first_wave_manifest import collect_first_wave_manifest  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

APPROVED_MANIFEST_SHA256 = "6f40a48e1eb686412ead3342e2cdf7304ebf234d4a0f597eeb817300295743e2"
APPROVED_READY_COUNT = 228
DEFAULT_REFERENCE_DATE = "2026-08-18"

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class PreflightGateError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest_gate(
    summary: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_count: int,
) -> None:
    actual_sha = str(summary.get("manifest_sha256") or "")
    actual_count = int(summary.get("first_wave_ready") or 0)
    if actual_sha != expected_sha256:
        raise PreflightGateError(
            f"MANIFEST_SHA256_MISMATCH expected={expected_sha256} actual={actual_sha}"
        )
    if actual_count != expected_count:
        raise PreflightGateError(
            f"MANIFEST_COUNT_MISMATCH expected={expected_count} actual={actual_count}"
        )


def assert_script_read_only() -> None:
    """Defesa adicional contra introdução acidental de mutadores Mongo neste arquivo."""
    source = Path(__file__).read_text(encoding="utf-8")
    # Ignora a própria lista de tokens acima ao checar chamadas reais em linhas de código.
    executable_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    ]
    executable = "\n".join(executable_lines)
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise PreflightGateError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _sorted_docs(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    docs = [dict(item) for item in items]
    docs.sort(
        key=lambda row: (
            str(row.get("school_id") or ""),
            str(row.get("class_id") or row.get("id") or ""),
            str(row.get("component_id") or row.get("course_id") or ""),
            str(row.get("teacher_id") or row.get("staff_id") or ""),
            str(row.get("id") or ""),
        )
    )
    return docs


async def _find_all(collection, query: dict, projection: Optional[dict] = None, limit: int = 50000):
    return await collection.find(query, projection or {"_id": 0}).to_list(limit)


async def collect_backup_bundle(db, manifest: list[Mapping[str, Any]], *, academic_year: int) -> dict[str, Any]:
    class_ids = sorted({str(row.get("class_id")) for row in manifest if row.get("class_id")})
    teacher_ids = sorted({str(row.get("teacher_id")) for row in manifest if row.get("teacher_id")})
    component_ids = sorted({str(row.get("component_id")) for row in manifest if row.get("component_id")})
    source_legacy_ids = sorted(
        {
            str((row.get("cutover_provenance") or {}).get("source_legacy_assignment_id"))
            for row in manifest
            if (row.get("cutover_provenance") or {}).get("source_legacy_assignment_id")
        }
    )

    teacher_class_assignments = await _find_all(
        db.teacher_class_assignments,
        {"class_id": {"$in": class_ids}},
    ) if class_ids else []
    teacher_assignments = await _find_all(
        db.teacher_assignments,
        {"id": {"$in": source_legacy_ids}},
    ) if source_legacy_ids else []
    class_schedules = await _find_all(
        db.class_schedules,
        {
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
    ) if class_ids else []
    classes = await _find_all(db.classes, {"id": {"$in": class_ids}}) if class_ids else []
    users = await _find_all(db.users, {"id": {"$in": teacher_ids}}) if teacher_ids else []
    courses = await _find_all(db.courses, {"id": {"$in": component_ids}}) if component_ids else []

    return {
        "scope": {
            "academic_year": academic_year,
            "class_ids": class_ids,
            "teacher_ids": teacher_ids,
            "component_ids": component_ids,
            "source_legacy_assignment_ids": source_legacy_ids,
        },
        "collections": {
            "teacher_class_assignments_before": _sorted_docs(teacher_class_assignments),
            "teacher_assignments_source": _sorted_docs(teacher_assignments),
            "class_schedules_source": _sorted_docs(class_schedules),
            "classes_source": _sorted_docs(classes),
            "users_source": _sorted_docs(users),
            "courses_source": _sorted_docs(courses),
        },
    }


def write_backup_directory(
    backup_dir: Path,
    *,
    manifest_report: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)

    files: dict[str, Any] = {
        "manifest.json": manifest_report.get("manifest") or [],
        "scope.json": bundle.get("scope") or {},
    }
    for name, docs in (bundle.get("collections") or {}).items():
        files[f"{name}.json"] = docs

    checksums: dict[str, str] = {}
    counts: dict[str, int] = {}
    for filename, payload in files.items():
        path = backup_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        checksums[filename] = sha256_file(path)
        if isinstance(payload, list):
            counts[filename] = len(payload)

    metadata = {
        "mode": "38G_A_PREFLIGHT_READ_ONLY",
        "mutates_database": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_report["summary"]["manifest_sha256"],
        "first_wave_ready": manifest_report["summary"]["first_wave_ready"],
        "file_counts": counts,
        "file_sha256": checksums,
    }
    metadata_path = backup_dir / "backup-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    checksums[metadata_path.name] = sha256_file(metadata_path)

    bundle_digest = sha256_value({"file_sha256": checksums})
    seal = {
        "backup_bundle_sha256": bundle_digest,
        "files": checksums,
    }
    (backup_dir / "BACKUP-SEAL.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {**metadata, **seal}


async def run_preflight(
    db,
    *,
    academic_year: int,
    reference_date: str,
    expected_sha256: str,
    expected_count: int,
    backup_dir: Path,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    assert_script_read_only()
    report = await collect_first_wave_manifest(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        tenant_id=tenant_id,
    )
    validate_manifest_gate(
        report["summary"],
        expected_sha256=expected_sha256,
        expected_count=expected_count,
    )
    bundle = await collect_backup_bundle(db, report["manifest"], academic_year=academic_year)
    backup = write_backup_directory(
        backup_dir,
        manifest_report=report,
        bundle=bundle,
    )
    return {
        "meta": {
            "mode": "38G_A_PREFLIGHT_READ_ONLY",
            "mutates_database": False,
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
        },
        "summary": report["summary"],
        "backup": backup,
        "backup_dir": str(backup_dir),
    }


def print_compact(result: Mapping[str, Any], *, expected_sha256: str, expected_count: int) -> None:
    summary = result["summary"]
    backup = result["backup"]
    print("=== DVD 38G-A — PREFLIGHT READ-ONLY ===")
    print("DRY_RUN_PRONTOS:", summary["first_wave_ready"])
    print("ESPERADO_PRONTOS:", expected_count)
    print("MANIFEST_SHA256:", summary["manifest_sha256"])
    print("SHA_ESPERADO:", expected_sha256)
    print("HASH_MATCH: SIM")
    print("BACKUP_DIR:", result["backup_dir"])
    print("BACKUP_SHA256:", backup["backup_bundle_sha256"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=2026)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--expected-manifest-sha256", default=APPROVED_MANIFEST_SHA256)
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        result = await run_preflight(
            client[os.environ["DB_NAME"]],
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            expected_sha256=args.expected_manifest_sha256,
            expected_count=args.expected_count,
            backup_dir=Path(args.backup_dir),
            tenant_id=args.tenant_id,
        )
        print_compact(
            result,
            expected_sha256=args.expected_manifest_sha256,
            expected_count=args.expected_count,
        )
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
