#!/usr/bin/env python3

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pymongo import MongoClient


ALLOWED_DAYS = {
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
}

TIME_RE = re.compile(
    r"^(?:[01]\d|2[0-3]):[0-5]\d$"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Validador fail-closed do pacote institucional "
            "SIGESC DVD 38H-C4/C5."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="00_manifesto_institucional.json preenchido",
    )

    parser.add_argument(
        "--report",
        required=True,
        help="Arquivo JSON de saída",
    )

    parser.add_argument(
        "--mode",
        choices=("baseline", "operational"),
        default="baseline",
        help="Modo do gate final: baseline ou operational",
    )

    return parser.parse_args()


def valid_time_pair(value):
    if not isinstance(value, dict):
        return False

    start = str(
        value.get("start")
        or ""
    ).strip()

    end = str(
        value.get("end")
        or ""
    ).strip()

    return bool(
        TIME_RE.fullmatch(start)
        and TIME_RE.fullmatch(end)
        and end > start
    )


def normalize_slot_times(value):
    result = {}

    if not isinstance(value, dict):
        return result

    for raw_key, pair in value.items():
        try:
            number = int(raw_key)
        except (TypeError, ValueError):
            continue

        result[number] = pair

    return result


def has_nonempty_text(value):
    return bool(
        isinstance(value, str)
        and value.strip()
    )


def valid_date(value):
    if not has_nonempty_text(value):
        return False

    try:
        datetime.strptime(
            value.strip(),
            "%Y-%m-%d",
        )
        return True
    except ValueError:
        return False


args = parse_args()

input_path = Path(args.input)
report_path = Path(args.report)

with input_path.open(
    encoding="utf-8"
) as f:
    package = json.load(f)

classes = package.get("classes") or []

# ------------------------------------------------------------
# Mongo — somente leitura
# ------------------------------------------------------------
mongo_url = (
    os.environ.get("MONGO_URL")
    or os.environ.get("MONGODB_URL")
    or os.environ.get("MONGO_URI")
    or os.environ.get("MONGODB_URI")
)

db_name = (
    os.environ.get("DB_NAME")
    or os.environ.get("MONGO_DB_NAME")
    or os.environ.get("MONGODB_DB")
)

if not mongo_url:
    raise SystemExit(
        "MONGO_URL ausente"
    )

if not db_name:
    parsed = urlparse(mongo_url)
    db_name = (
        (parsed.path or "")
        .lstrip("/")
        .split("/")[0]
    )

client = MongoClient(
    mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)

client.admin.command("ping")
db = client[db_name]

# ------------------------------------------------------------
# Contexto canônico
# ------------------------------------------------------------
class_ids = sorted({
    str(row.get("class_id"))
    for row in classes
    if row.get("class_id")
})

class_docs = list(
    db.classes.find(
        {
            "id": {
                "$in": class_ids
            }
        },
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "academic_year": 1,
            "shift": 1,
        },
    )
)

class_by_id = {
    str(row["id"]): row
    for row in class_docs
    if row.get("id")
}

current_schedules = list(
    db.class_schedules.find(
        {
            "class_id": {
                "$in": class_ids
            },
            "academic_year": {
                "$in": [2026, "2026"]
            },
        },
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "school_id": 1,
            "academic_year": 1,
            "schedule_slots": 1,
            "slot_times": 1,
            "slots_per_day": 1,
        },
    )
)

schedule_by_class = defaultdict(list)

for row in current_schedules:
    cid = str(
        row.get("class_id")
        or ""
    )

    if cid:
        schedule_by_class[
            cid
        ].append(row)

# ------------------------------------------------------------
# Validação turma a turma
# ------------------------------------------------------------
state_counts = Counter()
error_counts = Counter()
pending_field_counts = Counter()

results = []

for entry in classes:
    cid = str(
        entry.get("class_id")
        or ""
    )

    errors = []
    pending = []
    warnings = []

    klass = class_by_id.get(cid)

    # --------------------------------------------------------
    # Metadados imutáveis/canônicos
    # --------------------------------------------------------
    if not klass:
        errors.append(
            "CLASS_NOT_FOUND"
        )
    else:
        if str(
            klass.get("school_id")
            or ""
        ) != str(
            entry.get("school_id")
            or ""
        ):
            errors.append(
                "SCHOOL_ID_MISMATCH"
            )

        if str(
            klass.get("academic_year")
            or ""
        ) != str(
            entry.get("academic_year")
            or ""
        ):
            errors.append(
                "ACADEMIC_YEAR_MISMATCH"
            )

        if str(
            klass.get("shift")
            or ""
        ) != str(
            entry.get("shift")
            or ""
        ):
            errors.append(
                "CLASS_SHIFT_MISMATCH"
            )

    operation = str(
        entry.get("operation")
        or ""
    ).upper()

    docs = schedule_by_class.get(
        cid, []
    )

    if operation == "CREATE":
        if len(docs) != 0:
            errors.append(
                "CREATE_TARGET_ALREADY_EXISTS"
            )

    elif operation == "UPDATE":
        if len(docs) != 1:
            errors.append(
                "UPDATE_TARGET_NOT_UNIQUE"
            )
        else:
            expected_id = str(
                entry.get(
                    "existing_schedule_id"
                )
                or ""
            )

            actual_id = str(
                docs[0].get("id")
                or ""
            )

            if (
                not expected_id
                or expected_id
                != actual_id
            ):
                errors.append(
                    "UPDATE_SCHEDULE_ID_MISMATCH"
                )

    else:
        errors.append(
            "INVALID_OPERATION"
        )

    # --------------------------------------------------------
    # Conjunto canônico de componentes
    # --------------------------------------------------------
    canonical_components = {
        str(row.get("course_id"))
        for row in (
            entry.get("components")
            or []
        )
        if row.get("course_id")
    }

    if not canonical_components:
        errors.append(
            "CANONICAL_COMPONENT_SET_EMPTY"
        )

    # --------------------------------------------------------
    # Confirmação institucional
    # --------------------------------------------------------
    institutional = (
        entry.get(
            "institutional_input"
        )
        or {}
    )

    raw_slots_per_day = (
        institutional.get(
            "slots_per_day_confirmed"
        )
    )

    if raw_slots_per_day in (
        None,
        "",
    ):
        pending.append(
            "slots_per_day_confirmed"
        )
        slots_per_day = None
    else:
        try:
            slots_per_day = int(
                raw_slots_per_day
            )
        except (
            TypeError,
            ValueError,
        ):
            slots_per_day = None
            errors.append(
                "SLOTS_PER_DAY_NOT_INTEGER"
            )

        if (
            slots_per_day is not None
            and not (
                1
                <= slots_per_day
                <= 12
            )
        ):
            errors.append(
                "SLOTS_PER_DAY_OUT_OF_RANGE"
            )

    slot_times_raw = (
        institutional.get(
            "slot_times_confirmed"
        )
    )

    if not slot_times_raw:
        pending.append(
            "slot_times_confirmed"
        )

    slot_times = normalize_slot_times(
        slot_times_raw
    )

    slots_raw = (
        institutional.get(
            "schedule_slots_confirmed"
        )
    )

    if not slots_raw:
        pending.append(
            "schedule_slots_confirmed"
        )

    if (
        slots_raw
        and not isinstance(
            slots_raw,
            list,
        )
    ):
        errors.append(
            "SCHEDULE_SLOTS_NOT_LIST"
        )
        slots_raw = []

    if not has_nonempty_text(
        institutional.get(
            "institutional_source"
        )
    ):
        pending.append(
            "institutional_source"
        )

    if not has_nonempty_text(
        institutional.get(
            "confirmed_by"
        )
    ):
        pending.append(
            "confirmed_by"
        )

    confirmation_date = (
        institutional.get(
            "confirmation_date"
        )
    )

    if not confirmation_date:
        pending.append(
            "confirmation_date"
        )
    elif not valid_date(
        confirmation_date
    ):
        errors.append(
            "INVALID_CONFIRMATION_DATE"
        )

    # --------------------------------------------------------
    # Validações detalhadas só quando quantidade de slots
    # já foi informada.
    # --------------------------------------------------------
    if slots_per_day is not None:
        expected_slot_numbers = set(
            range(
                1,
                slots_per_day + 1,
            )
        )

        actual_time_numbers = set(
            slot_times
        )

        missing_time_defs = sorted(
            expected_slot_numbers
            - actual_time_numbers
        )

        extra_time_defs = sorted(
            actual_time_numbers
            - expected_slot_numbers
        )

        if (
            slot_times_raw
            and missing_time_defs
        ):
            errors.append(
                "MISSING_SLOT_TIME_DEFINITIONS"
            )

        if extra_time_defs:
            errors.append(
                "EXTRA_SLOT_TIME_DEFINITIONS"
            )

        for number, pair in (
            slot_times.items()
        ):
            if (
                number
                in expected_slot_numbers
                and not valid_time_pair(
                    pair
                )
            ):
                errors.append(
                    "INVALID_SLOT_TIME_PAIR"
                )
                break

    # --------------------------------------------------------
    # Grade semanal
    # --------------------------------------------------------
    seen_cells = set()
    used_components = set()
    used_slot_numbers = set()

    for index, slot in enumerate(
        slots_raw or []
    ):
        if not isinstance(
            slot,
            dict,
        ):
            errors.append(
                "SCHEDULE_SLOT_NOT_OBJECT"
            )
            continue

        day = str(
            slot.get("day")
            or ""
        ).strip()

        if day not in ALLOWED_DAYS:
            errors.append(
                "INVALID_DAY"
            )

        try:
            slot_number = int(
                slot.get(
                    "slot_number"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            slot_number = None
            errors.append(
                "INVALID_SLOT_NUMBER"
            )

        if (
            slot_number is not None
            and slots_per_day
            is not None
            and not (
                1
                <= slot_number
                <= slots_per_day
            )
        ):
            errors.append(
                "SLOT_NUMBER_OUT_OF_RANGE"
            )

        course_id = str(
            slot.get("course_id")
            or ""
        )

        if (
            not course_id
            or course_id
            not in canonical_components
        ):
            errors.append(
                "UNKNOWN_COURSE_ID"
            )

        if (
            day in ALLOWED_DAYS
            and slot_number
            is not None
        ):
            cell = (
                day,
                slot_number,
            )

            if cell in seen_cells:
                errors.append(
                    "DUPLICATE_DAY_SLOT"
                )

            seen_cells.add(cell)
            used_slot_numbers.add(
                slot_number
            )

        if course_id:
            used_components.add(
                course_id
            )

    if slots_raw:
        missing_components = sorted(
            canonical_components
            - used_components
        )

        if missing_components:
            errors.append(
                "ACTIVE_COMPONENT_WITHOUT_WEEKLY_SLOT"
            )

        # Ausencia total de slot_times_confirmed e um estado
    # PENDING, nao INVALID. Somente avaliamos coerencia entre
    # slots usados e horarios quando a instituicao efetivamente
    # forneceu alguma definicao de horario.
    if (
            slots_per_day
            is not None
            and slot_times_raw
        ):
            missing_used_times = sorted(
                number
                for number in (
                    used_slot_numbers
                )
                if number not in slot_times
            )

            if missing_used_times:
                errors.append(
                    "USED_SLOT_WITHOUT_TIME_DEFINITION"
                )

    # --------------------------------------------------------
    # Estado
    # --------------------------------------------------------
    errors = sorted(set(errors))
    pending = sorted(set(pending))
    warnings = sorted(set(warnings))

    for value in errors:
        error_counts[value] += 1

    for value in pending:
        pending_field_counts[
            value
        ] += 1

    if errors:
        state = "INVALID"

    elif pending:
        state = "PENDING"

    else:
        state = "READY_FOR_DRY_RUN"

    state_counts[state] += 1

    results.append({
        "school_id":
            entry.get("school_id"),

        "school_name":
            entry.get("school_name"),

        "class_id":
            cid,

        "class_name":
            entry.get("class_name"),

        "operation":
            operation,

        "state":
            state,

        "errors":
            errors,

        "pending_fields":
            pending,

        "warnings":
            warnings,

        "canonical_component_count":
            len(
                canonical_components
            ),

        "confirmed_schedule_slot_count":
            len(
                slots_raw
                or []
            ),

        "confirmed_slots_per_day":
            slots_per_day,
    })

# ------------------------------------------------------------
# Resumo por escola
# ------------------------------------------------------------
school_summary = defaultdict(
    Counter
)

for row in results:
    school_name = str(
        row.get("school_name")
        or "-"
    )

    school_summary[
        school_name
    ][row["state"]] += 1

print("=== RESULTADO DO VALIDADOR ===")

print(
    "INPUT_CLASSES=",
    len(classes),
)

for state in (
    "READY_FOR_DRY_RUN",
    "PENDING",
    "INVALID",
):
    print(
        f"{state}=",
        state_counts[state],
    )

print()
print(
    "PENDING_FIELDS=",
    dict(
        sorted(
            pending_field_counts.items()
        )
    ),
)

print(
    "VALIDATION_ERRORS=",
    dict(
        sorted(
            error_counts.items()
        )
    ),
)

print()
print("=== POR ESCOLA ===")

for school_name in sorted(
    school_summary,
    key=str.casefold,
):
    print(
        "ESCOLA:",
        school_name,
        "|",
        dict(
            school_summary[
                school_name
            ]
        ),
    )

# ------------------------------------------------------------
# Gate estrutural do validador.
# Baseline C5 deve ser PENDING, não INVALID.
# ------------------------------------------------------------
baseline_pass = (
    len(classes) == 78
    and state_counts[
        "READY_FOR_DRY_RUN"
    ] == 0
    and state_counts[
        "PENDING"
    ] == 78
    and state_counts[
        "INVALID"
    ] == 0
)

# Gate operacional fail-closed:
# INVALID prevalece; depois PENDING; READY somente
# quando todas as classes estiverem completas e validas.
if not classes:
    operational_state = "INVALID"
elif state_counts["INVALID"] > 0:
    operational_state = "INVALID"
elif state_counts["PENDING"] > 0:
    operational_state = "PENDING"
elif state_counts["READY_FOR_DRY_RUN"] == len(classes):
    operational_state = "READY_FOR_DRY_RUN"
else:
    operational_state = "INVALID"

operational_pass = (
    operational_state == "READY_FOR_DRY_RUN"
)

selected_gate_pass = (
    baseline_pass
    if args.mode == "baseline"
    else operational_pass
)

report = {
    "audit":
        "DVD_38H_C5_INSTITUTIONAL_VALIDATOR",

    "mode":
        "READ_ONLY_VALIDATION",

    "gate_mode":
        args.mode,

    "mutates_database":
        False,

    "summary": {
        "input_classes":
            len(classes),

        "states":
            dict(state_counts),

        "pending_fields":
            dict(
                pending_field_counts
            ),

        "validation_errors":
            dict(error_counts),

        "baseline_expected_pending":
            args.mode == "baseline",

        "baseline_gate":
            (
                "PASS"
                if baseline_pass
                else "REVIEW_REQUIRED"
            ),

        "operational_state":
            operational_state,

        "operational_gate":
            (
                "PASS"
                if operational_pass
                else "REVIEW_REQUIRED"
            ),

        "selected_gate":
            (
                "PASS"
                if selected_gate_pass
                else "REVIEW_REQUIRED"
            ),
    },

    "school_summary": {
        school: dict(counts)
        for school, counts
        in school_summary.items()
    },

    "classes":
        results,

    "guarantees": {
        "mongo_writes": 0,
        "schedule_writes": 0,
        "dvd_writes": 0,
        "apply_mode": False,
    },
}

with report_path.open(
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        report,
        f,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    f.write("\n")

print()
print("REPORT_JSON=", report_path)

print("MONGO_WRITES=0")
print("SCHEDULE_WRITES=0")
print("DVD_WRITES=0")
print("APPLY_MODE=NAO")

print()
print(
    "STATUS="
    + (
        "PASS"
        if selected_gate_pass
        else "REVIEW_REQUIRED"
    )
)

client.close()
