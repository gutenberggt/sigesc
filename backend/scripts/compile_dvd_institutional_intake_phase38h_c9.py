#!/usr/bin/env python3

import argparse
import hashlib
import csv
import json
import re
import unicodedata
from copy import deepcopy
from datetime import datetime
from pathlib import Path


DAYS = (
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
)

MAX_SLOTS_PER_DAY = 12

TIME_RE = re.compile(
    r"^(?:[01]\d|2[0-3]):[0-5]\d$"
)

EXPECTED_SCHEMA = (
    "SIGESC_DVD_38H_C9_OPERATIONAL_INTAKE_V1"
)

EXPECTED_SOURCE_C4_SHA256 = (
    "353c72ca0c2d90383fd2965ebf94d6bb"
    "fa2786a1513a446d4066aedd0718a740"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compila os CSVs institucionais DVD 38H-C9 "
            "para 00_manifesto_institucional.json."
        )
    )

    parser.add_argument(
        "--input-dir",
        required=True,
        help="Diretório do pacote C9 preenchido.",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Manifesto JSON compilado.",
    )

    return parser.parse_args()


def normalize_name(value):
    value = str(value or "").strip().casefold()
    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    return "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )


def valid_time_pair(start, end):
    start = str(start or "").strip()
    end = str(end or "").strip()

    return bool(
        TIME_RE.fullmatch(start)
        and TIME_RE.fullmatch(end)
        and end > start
    )


def valid_date(value):
    value = str(value or "").strip()

    try:
        datetime.strptime(
            value,
            "%Y-%m-%d",
        )
        return True
    except ValueError:
        return False



def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def read_csv(path):
    if not path.is_file():
        raise SystemExit(
            f"REQUIRED_FILE_MISSING: {path.name}"
        )

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


def load_base_manifest(input_dir):
    path = (
        input_dir
        / "00_manifesto_institucional.json"
    )

    summary_path = (
        input_dir
        / "06_resumo.json"
    )

    if not path.is_file():
        raise SystemExit(
            "BASE_MANIFEST_MISSING"
        )

    if not summary_path.is_file():
        raise SystemExit(
            "BASE_SUMMARY_MISSING"
        )

    with summary_path.open(
        encoding="utf-8",
    ) as f:
        summary = json.load(f)

    if (
        summary.get("schema")
        != EXPECTED_SCHEMA
    ):
        raise SystemExit(
            "BASE_SUMMARY_SCHEMA_MISMATCH: "
            f"expected={EXPECTED_SCHEMA} "
            f"actual={summary.get('schema')!r}"
        )

    if (
        summary.get("source_c4_sha256")
        != EXPECTED_SOURCE_C4_SHA256
    ):
        raise SystemExit(
            "BASE_SUMMARY_SOURCE_SHA256_MISMATCH"
        )

    if summary.get("database_writes") is not False:
        raise SystemExit(
            "BASE_SUMMARY_DATABASE_WRITES_NOT_FALSE"
        )

    expected_manifest_sha256 = str(
        summary.get("base_manifest_sha256")
        or ""
    ).strip().lower()

    if not re.fullmatch(
        r"[0-9a-f]{64}",
        expected_manifest_sha256,
    ):
        raise SystemExit(
            "BASE_MANIFEST_SHA256_MISSING_OR_INVALID"
        )

    actual_manifest_sha256 = sha256_file(
        path
    )

    if (
        actual_manifest_sha256
        != expected_manifest_sha256
    ):
        raise SystemExit(
            "BASE_MANIFEST_SHA256_MISMATCH: "
            f"expected={expected_manifest_sha256} "
            f"actual={actual_manifest_sha256}"
        )

    with path.open(
        encoding="utf-8",
    ) as f:
        manifest = json.load(f)

    if (
        manifest.get("schema")
        != EXPECTED_SCHEMA
    ):
        raise SystemExit(
            "BASE_SCHEMA_MISMATCH: "
            f"expected={EXPECTED_SCHEMA} "
            f"actual={manifest.get('schema')!r}"
        )

    if (
        manifest.get("source_c4_sha256")
        != EXPECTED_SOURCE_C4_SHA256
    ):
        raise SystemExit(
            "BASE_SOURCE_SHA256_MISMATCH: "
            f"expected={EXPECTED_SOURCE_C4_SHA256} "
            f"actual={manifest.get('source_c4_sha256')!r}"
        )

    if manifest.get("database_writes") is not False:
        raise SystemExit(
            "BASE_DATABASE_WRITES_NOT_FALSE"
        )

    classes = (
        manifest.get("classes")
        or []
    )

    if len(classes) != 78:
        raise SystemExit(
            "BASE_CLASS_COUNT_MISMATCH: "
            f"expected=78 actual={len(classes)}"
        )

    class_ids = [
        str(entry.get("class_id") or "")
        for entry in classes
    ]

    if (
        any(not class_id for class_id in class_ids)
        or len(set(class_ids)) != 78
    ):
        raise SystemExit(
            "BASE_CLASS_IDS_INVALID"
        )

    return manifest


def build_component_lookup(classes):
    lookup = {}

    for entry in classes:
        class_id = str(
            entry.get("class_id")
            or ""
        )

        class_lookup = {}

        for component in (
            entry.get("components")
            or []
        ):
            course_id = str(
                component.get("course_id")
                or ""
            )

            course_name = str(
                component.get("course_name")
                or ""
            ).strip()

            normalized = normalize_name(
                course_name
            )

            if (
                not course_id
                or not normalized
            ):
                raise SystemExit(
                    "BASE_COMPONENT_INVALID: "
                    f"class_id={class_id}"
                )

            if normalized in class_lookup:
                raise SystemExit(
                    "BASE_COMPONENT_NAME_AMBIGUOUS: "
                    f"class_id={class_id} "
                    f"course_name={course_name!r}"
                )

            class_lookup[
                normalized
            ] = {
                "course_id": course_id,
                "course_name": course_name,
            }

        if not class_lookup:
            raise SystemExit(
                "BASE_COMPONENT_SET_EMPTY: "
                f"class_id={class_id}"
            )

        lookup[class_id] = (
            class_lookup
        )

    return lookup


def validate_input_grids(
    input_dir,
    classes,
):
    class_ids = {
        str(entry.get("class_id") or "")
        for entry in classes
    }

    slot_rows = read_csv(
        input_dir
        / "03_horarios_de_aula_para_confirmacao.csv"
    )

    weekly_rows = read_csv(
        input_dir
        / "04_distribuicao_semanal_para_confirmacao.csv"
    )

    confirmation_rows = read_csv(
        input_dir
        / "05_confirmacao_institucional.csv"
    )

    if len(slot_rows) != 936:
        raise SystemExit(
            "SLOT_ROW_COUNT_MISMATCH: "
            f"expected=936 actual={len(slot_rows)}"
        )

    if len(weekly_rows) != 4680:
        raise SystemExit(
            "WEEKLY_ROW_COUNT_MISMATCH: "
            f"expected=4680 actual={len(weekly_rows)}"
        )

    if len(confirmation_rows) != 78:
        raise SystemExit(
            "CONFIRMATION_ROW_COUNT_MISMATCH: "
            f"expected=78 actual={len(confirmation_rows)}"
        )

    seen_slot_keys = set()

    for row in slot_rows:
        class_id = str(
            row.get("class_id") or ""
        ).strip()

        if class_id not in class_ids:
            raise SystemExit(
                "UNKNOWN_CLASS_ID_IN_SLOT_GRID: "
                f"class_id={class_id!r}"
            )

        try:
            slot_number = int(
                row.get("slot_number")
            )
        except (
            TypeError,
            ValueError,
        ):
            raise SystemExit(
                "INVALID_SLOT_NUMBER_IN_SLOT_GRID: "
                f"class_id={class_id}"
            )

        if not (
            1
            <= slot_number
            <= MAX_SLOTS_PER_DAY
        ):
            raise SystemExit(
                "SLOT_NUMBER_OUT_OF_RANGE_IN_SLOT_GRID: "
                f"class_id={class_id} "
                f"slot_number={slot_number}"
            )

        key = (
            class_id,
            slot_number,
        )

        if key in seen_slot_keys:
            raise SystemExit(
                "DUPLICATE_SLOT_GRID_KEY: "
                f"class_id={class_id} "
                f"slot_number={slot_number}"
            )

        seen_slot_keys.add(key)

    if len(seen_slot_keys) != 936:
        raise SystemExit(
            "SLOT_GRID_KEY_COUNT_MISMATCH"
        )

    seen_weekly_keys = set()

    for row in weekly_rows:
        class_id = str(
            row.get("class_id") or ""
        ).strip()

        if class_id not in class_ids:
            raise SystemExit(
                "UNKNOWN_CLASS_ID_IN_WEEKLY_GRID: "
                f"class_id={class_id!r}"
            )

        day = str(
            row.get("day") or ""
        ).strip()

        if day not in DAYS:
            raise SystemExit(
                "INVALID_DAY_IN_WEEKLY_GRID: "
                f"class_id={class_id} "
                f"day={day!r}"
            )

        try:
            slot_number = int(
                row.get("slot_number")
            )
        except (
            TypeError,
            ValueError,
        ):
            raise SystemExit(
                "INVALID_SLOT_NUMBER_IN_WEEKLY_GRID: "
                f"class_id={class_id} "
                f"day={day}"
            )

        if not (
            1
            <= slot_number
            <= MAX_SLOTS_PER_DAY
        ):
            raise SystemExit(
                "SLOT_NUMBER_OUT_OF_RANGE_IN_WEEKLY_GRID: "
                f"class_id={class_id} "
                f"day={day} "
                f"slot_number={slot_number}"
            )

        key = (
            class_id,
            day,
            slot_number,
        )

        if key in seen_weekly_keys:
            raise SystemExit(
                "DUPLICATE_WEEKLY_GRID_KEY: "
                f"class_id={class_id} "
                f"day={day} "
                f"slot_number={slot_number}"
            )

        seen_weekly_keys.add(key)

    if len(seen_weekly_keys) != 4680:
        raise SystemExit(
            "WEEKLY_GRID_KEY_COUNT_MISMATCH"
        )

    seen_confirmation_ids = set()

    for row in confirmation_rows:
        class_id = str(
            row.get("class_id") or ""
        ).strip()

        if class_id not in class_ids:
            raise SystemExit(
                "UNKNOWN_CLASS_ID_IN_CONFIRMATION: "
                f"class_id={class_id!r}"
            )

        if class_id in seen_confirmation_ids:
            raise SystemExit(
                "DUPLICATE_CONFIRMATION_CLASS_ID: "
                f"class_id={class_id}"
            )

        seen_confirmation_ids.add(
            class_id
        )

    if seen_confirmation_ids != class_ids:
        raise SystemExit(
            "CONFIRMATION_CLASS_SET_MISMATCH"
        )

    return (
        slot_rows,
        weekly_rows,
        confirmation_rows,
    )


def assert_base_institutional_empty(classes):
    for entry in classes:
        institutional = (
            entry.get("institutional_input")
            or {}
        )

        if any(
            value not in (None, "", [], {})
            for value in institutional.values()
        ):
            raise SystemExit(
                "BASE_INSTITUTIONAL_INPUT_NOT_EMPTY: "
                f"class_id={entry.get('class_id')}"
            )


def compile_institutional_inputs(
    classes,
    component_lookup,
    slot_rows,
    weekly_rows,
    confirmation_rows,
):
    slot_by_class = {}

    for row in slot_rows:
        class_id = str(
            row.get("class_id") or ""
        ).strip()

        slot_number = int(
            row.get("slot_number")
        )

        slot_by_class.setdefault(
            class_id,
            {},
        )[slot_number] = row

    weekly_by_class = {}

    for row in weekly_rows:
        class_id = str(
            row.get("class_id") or ""
        ).strip()

        weekly_by_class.setdefault(
            class_id,
            [],
        ).append(row)

    confirmation_by_class = {
        str(row.get("class_id") or "").strip(): row
        for row in confirmation_rows
    }

    compiled = {}

    for entry in classes:
        class_id = str(
            entry.get("class_id") or ""
        )

        confirmation = (
            confirmation_by_class[
                class_id
            ]
        )

        raw_slots_per_day = str(
            confirmation.get(
                "slots_per_day_confirmed"
            )
            or ""
        ).strip()

        if raw_slots_per_day:
            try:
                slots_per_day = int(
                    raw_slots_per_day
                )
            except ValueError:
                raise SystemExit(
                    "SLOTS_PER_DAY_NOT_INTEGER: "
                    f"class_id={class_id}"
                )

            if not (
                1
                <= slots_per_day
                <= MAX_SLOTS_PER_DAY
            ):
                raise SystemExit(
                    "SLOTS_PER_DAY_OUT_OF_RANGE: "
                    f"class_id={class_id} "
                    f"value={slots_per_day}"
                )
        else:
            slots_per_day = None

        slot_times = {}
        populated_time_slots = set()

        for slot_number, row in sorted(
            slot_by_class[class_id].items()
        ):
            start = str(
                row.get("start_confirmed")
                or ""
            ).strip()

            end = str(
                row.get("end_confirmed")
                or ""
            ).strip()

            if bool(start) != bool(end):
                raise SystemExit(
                    "HALF_FILLED_SLOT_TIME: "
                    f"class_id={class_id} "
                    f"slot_number={slot_number}"
                )

            if not start:
                continue

            if slots_per_day is None:
                raise SystemExit(
                    "TIME_WITHOUT_SLOTS_PER_DAY: "
                    f"class_id={class_id} "
                    f"slot_number={slot_number}"
                )

            if slot_number > slots_per_day:
                raise SystemExit(
                    "TIME_BEYOND_SLOTS_PER_DAY: "
                    f"class_id={class_id} "
                    f"slot_number={slot_number} "
                    f"slots_per_day={slots_per_day}"
                )

            if not valid_time_pair(
                start,
                end,
            ):
                raise SystemExit(
                    "INVALID_SLOT_TIME_PAIR: "
                    f"class_id={class_id} "
                    f"slot_number={slot_number}"
                )

            populated_time_slots.add(
                slot_number
            )

            slot_times[
                str(slot_number)
            ] = {
                "start": start,
                "end": end,
            }

        if populated_time_slots:
            expected = set(
                range(
                    1,
                    slots_per_day + 1,
                )
            )

            if populated_time_slots != expected:
                raise SystemExit(
                    "PARTIAL_SLOT_TIME_SET: "
                    f"class_id={class_id} "
                    f"expected={sorted(expected)} "
                    f"actual={sorted(populated_time_slots)}"
                )

        schedule_slots = []

        for row in weekly_by_class[
            class_id
        ]:
            day = str(
                row.get("day") or ""
            ).strip()

            slot_number = int(
                row.get("slot_number")
            )

            supplied_resolved_id = str(
                row.get("course_id_resolved")
                or ""
            ).strip()

            if supplied_resolved_id:
                raise SystemExit(
                    "COURSE_ID_RESOLVED_MUST_BE_EMPTY: "
                    f"class_id={class_id} "
                    f"day={day} "
                    f"slot_number={slot_number}"
                )

            course_name = str(
                row.get(
                    "course_name_confirmed"
                )
                or ""
            ).strip()

            if not course_name:
                continue

            if slots_per_day is None:
                raise SystemExit(
                    "WEEKLY_DATA_WITHOUT_SLOTS_PER_DAY: "
                    f"class_id={class_id} "
                    f"day={day} "
                    f"slot_number={slot_number}"
                )

            if slot_number > slots_per_day:
                raise SystemExit(
                    "WEEKLY_SLOT_BEYOND_SLOTS_PER_DAY: "
                    f"class_id={class_id} "
                    f"day={day} "
                    f"slot_number={slot_number} "
                    f"slots_per_day={slots_per_day}"
                )

            normalized = normalize_name(
                course_name
            )

            resolved = (
                component_lookup[
                    class_id
                ].get(
                    normalized
                )
            )

            if not resolved:
                raise SystemExit(
                    "UNKNOWN_COMPONENT_NAME: "
                    f"class_id={class_id} "
                    f"course_name={course_name!r}"
                )

            schedule_slots.append({
                "day": day,
                "slot_number": slot_number,
                "course_id": resolved[
                    "course_id"
                ],
            })

        source = str(
            confirmation.get(
                "institutional_source"
            )
            or ""
        ).strip()

        confirmed_by = str(
            confirmation.get(
                "confirmed_by"
            )
            or ""
        ).strip()

        confirmation_date = str(
            confirmation.get(
                "confirmation_date"
            )
            or ""
        ).strip()

        notes = str(
            confirmation.get("notes")
            or ""
        ).strip()

        if (
            confirmation_date
            and not valid_date(
                confirmation_date
            )
        ):
            raise SystemExit(
                "INVALID_CONFIRMATION_DATE: "
                f"class_id={class_id} "
                f"value={confirmation_date!r}"
            )

        compiled[class_id] = {
            "slots_per_day_confirmed": (
                slots_per_day
            ),
            "slot_times_confirmed": (
                slot_times
            ),
            "schedule_slots_confirmed": (
                schedule_slots
            ),
            "institutional_source": source,
            "confirmed_by": confirmed_by,
            "confirmation_date": (
                confirmation_date
            ),
            "notes": notes,
        }

    return compiled


def main():
    args = parse_args()

    input_dir = Path(
        args.input_dir
    ).resolve()

    output_path = Path(
        args.output
    ).resolve()

    base_path = (
        input_dir
        / "00_manifesto_institucional.json"
    ).resolve()

    if output_path == base_path:
        raise SystemExit(
            "OUTPUT_MUST_NOT_OVERWRITE_BASE_MANIFEST"
        )

    manifest = load_base_manifest(
        input_dir
    )

    classes = (
        manifest.get("classes")
        or []
    )

    assert_base_institutional_empty(
        classes
    )

    component_lookup = (
        build_component_lookup(
            classes
        )
    )

    (
        slot_rows,
        weekly_rows,
        confirmation_rows,
    ) = validate_input_grids(
        input_dir,
        classes,
    )

    compiled = (
        compile_institutional_inputs(
            classes,
            component_lookup,
            slot_rows,
            weekly_rows,
            confirmation_rows,
        )
    )

    output_manifest = deepcopy(
        manifest
    )

    for entry in (
        output_manifest.get("classes")
        or []
    ):
        class_id = str(
            entry.get("class_id")
            or ""
        )

        entry["institutional_input"] = (
            compiled[class_id]
        )

    output_manifest[
        "mode"
    ] = "INSTITUTIONAL_COMPILED"

    output_manifest[
        "database_writes"
    ] = False

    output_manifest[
        "compiled_by"
    ] = "DVD_38H_C9_COMPILER_V1"

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output_manifest,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    populated_classes = sum(
        any(
            value
            not in (None, "", [], {})
            for value in (
                compiled[class_id]
            ).values()
        )
        for class_id in compiled
    )

    print("STATUS=PASS")
    print(
        f"CLASSES={len(classes)}"
    )
    print(
        f"POPULATED_CLASSES={populated_classes}"
    )
    print(
        f"OUTPUT={output_path}"
    )
    print("DATABASE_WRITES=0")


if __name__ == "__main__":
    main()
