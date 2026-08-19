import importlib.util
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name,
        SCRIPTS / filename,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module(
    "dvd_c9_generator",
    "generate_dvd_institutional_intake_phase38h_c9.py",
)

compiler = load_module(
    "dvd_c9_compiler",
    "compile_dvd_institutional_intake_phase38h_c9.py",
)


def make_classes():
    classes = []

    # 18 x 8 + 60 x 7 = 564 componentes.
    for index in range(78):
        component_count = 8 if index < 18 else 7

        components = [
            {
                "course_id": f"course-{index}-{course}",
                "course_name": f"Componente {course}",
            }
            for course in range(component_count)
        ]

        classes.append({
            "class_id": f"class-{index}",
            "class_name": f"Turma {index}",
            "school_id": f"school-{index % 13}",
            "school_name": f"Escola {index % 13}",
            "academic_year": 2026,
            "shift": "morning",
            "operation": (
                "CREATE"
                if index < 75
                else "UPDATE"
            ),
            "existing_schedule_id": (
                ""
                if index < 75
                else f"schedule-{index}"
            ),
            "component_count": component_count,
            "components": components,
            "institutional_input": {
                "slots_per_day_confirmed": None,
                "slot_times_confirmed": {},
                "schedule_slots_confirmed": [],
                "institutional_source": "",
                "confirmed_by": "",
                "confirmation_date": "",
                "notes": "",
            },
        })

    return classes


def test_generator_source_structure_invariants():
    classes = make_classes()

    checks = generator.validate_source_structure({
        "classes": classes,
    })

    assert checks == {
        "classes": 78,
        "unique_class_ids": 78,
        "schools": 13,
        "create": 75,
        "update": 3,
        "components": 564,
        "unique_class_course": 564,
    }


def test_generator_operational_grid_cardinalities():
    classes = make_classes()

    class_rows = generator.build_class_catalog(
        classes
    )
    component_rows = (
        generator.build_component_catalog(
            classes
        )
    )
    slot_rows = generator.build_slot_time_grid(
        classes
    )
    weekly_rows = generator.build_weekly_grid(
        classes
    )
    confirmation_rows = (
        generator.build_confirmation_catalog(
            classes
        )
    )

    assert len(class_rows) == 78
    assert len(component_rows) == 564
    assert len(slot_rows) == 936
    assert len(weekly_rows) == 4680
    assert len(confirmation_rows) == 78


def test_generator_never_promotes_reference_to_confirmation():
    classes = make_classes()

    classes[0][
        "existing_slot_times_reference"
    ] = {
        "1": {
            "start": "07:30",
            "end": "08:20",
        }
    }

    slot_rows = generator.build_slot_time_grid(
        classes
    )

    first = next(
        row
        for row in slot_rows
        if (
            row["class_id"] == "class-0"
            and row["slot_number"] == 1
        )
    )

    assert first["reference_start"] == "07:30"
    assert first["reference_end"] == "08:20"

    assert first["start_confirmed"] == ""
    assert first["end_confirmed"] == ""


def test_generator_weekly_grid_starts_without_components():
    rows = generator.build_weekly_grid(
        make_classes()
    )

    assert len(rows) == 4680

    assert all(
        row["course_name_confirmed"] == ""
        for row in rows
    )

    assert all(
        row["course_id_resolved"] == ""
        for row in rows
    )


def test_component_lookup_is_unambiguous():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    assert len(lookup) == 78

    assert (
        lookup["class-0"][
            compiler.normalize_name(
                "Componente 0"
            )
        ]["course_id"]
        == "course-0-0"
    )


def make_compiler_rows(classes):
    return (
        generator.build_slot_time_grid(classes),
        generator.build_weekly_grid(classes),
        generator.build_confirmation_catalog(classes),
    )


def test_compiler_empty_input_stays_empty():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    slot_rows, weekly_rows, confirmation_rows = (
        make_compiler_rows(classes)
    )

    compiled = compiler.compile_institutional_inputs(
        classes,
        lookup,
        slot_rows,
        weekly_rows,
        confirmation_rows,
    )

    assert len(compiled) == 78

    assert all(
        value["slots_per_day_confirmed"] is None
        and value["slot_times_confirmed"] == {}
        and value["schedule_slots_confirmed"] == []
        and value["institutional_source"] == ""
        and value["confirmed_by"] == ""
        and value["confirmation_date"] == ""
        for value in compiled.values()
    )


def test_compiler_complete_class_resolves_all_components():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    slot_rows, weekly_rows, confirmation_rows = (
        make_compiler_rows(classes)
    )

    class_id = "class-0"

    for row in confirmation_rows:
        if row["class_id"] == class_id:
            row["slots_per_day_confirmed"] = "2"
            row["institutional_source"] = "TESTE"
            row["confirmed_by"] = "AUTOMATIZADO"
            row["confirmation_date"] = "2026-08-19"

    for row in slot_rows:
        if row["class_id"] != class_id:
            continue

        if row["slot_number"] == 1:
            row["start_confirmed"] = "07:00"
            row["end_confirmed"] = "07:45"

        elif row["slot_number"] == 2:
            row["start_confirmed"] = "07:50"
            row["end_confirmed"] = "08:35"

    targets = [
        row
        for row in weekly_rows
        if (
            row["class_id"] == class_id
            and row["day"] in (
                "segunda",
                "terca",
                "quarta",
                "quinta",
            )
            and int(row["slot_number"]) <= 2
        )
    ]

    assert len(targets) == 8

    for target, component in zip(
        targets,
        classes[0]["components"],
    ):
        target["course_name_confirmed"] = (
            component["course_name"]
        )

    compiled = compiler.compile_institutional_inputs(
        classes,
        lookup,
        slot_rows,
        weekly_rows,
        confirmation_rows,
    )

    value = compiled[class_id]

    assert value["slots_per_day_confirmed"] == 2
    assert len(value["slot_times_confirmed"]) == 2
    assert len(value["schedule_slots_confirmed"]) == 8

    assert {
        row["course_id"]
        for row in value["schedule_slots_confirmed"]
    } == {
        component["course_id"]
        for component in classes[0]["components"]
    }


def test_compiler_rejects_half_filled_time():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    slot_rows, weekly_rows, confirmation_rows = (
        make_compiler_rows(classes)
    )

    confirmation_rows[0][
        "slots_per_day_confirmed"
    ] = "1"

    slot_rows[0]["start_confirmed"] = "07:00"

    with pytest.raises(
        SystemExit,
        match="HALF_FILLED_SLOT_TIME",
    ):
        compiler.compile_institutional_inputs(
            classes,
            lookup,
            slot_rows,
            weekly_rows,
            confirmation_rows,
        )


def test_compiler_rejects_unknown_component_name():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    slot_rows, weekly_rows, confirmation_rows = (
        make_compiler_rows(classes)
    )

    confirmation_rows[0][
        "slots_per_day_confirmed"
    ] = "1"

    weekly_rows[0][
        "course_name_confirmed"
    ] = "COMPONENTE INEXISTENTE"

    with pytest.raises(
        SystemExit,
        match="UNKNOWN_COMPONENT_NAME",
    ):
        compiler.compile_institutional_inputs(
            classes,
            lookup,
            slot_rows,
            weekly_rows,
            confirmation_rows,
        )


def test_compiler_rejects_manual_course_id_resolved():
    classes = make_classes()

    lookup = compiler.build_component_lookup(
        classes
    )

    slot_rows, weekly_rows, confirmation_rows = (
        make_compiler_rows(classes)
    )

    weekly_rows[0][
        "course_id_resolved"
    ] = "manual-id"

    with pytest.raises(
        SystemExit,
        match="COURSE_ID_RESOLVED_MUST_BE_EMPTY",
    ):
        compiler.compile_institutional_inputs(
            classes,
            lookup,
            slot_rows,
            weekly_rows,
            confirmation_rows,
        )


def test_component_lookup_rejects_ambiguous_name():
    classes = make_classes()

    classes[0]["components"][1][
        "course_name"
    ] = "Componente 0"

    with pytest.raises(
        SystemExit,
        match="BASE_COMPONENT_NAME_AMBIGUOUS",
    ):
        compiler.build_component_lookup(
            classes
        )


def write_integrity_package(tmp_path):
    import hashlib
    import json

    manifest = {
        "schema": compiler.EXPECTED_SCHEMA,
        "source_c4_sha256": (
            compiler.EXPECTED_SOURCE_C4_SHA256
        ),
        "database_writes": False,
        "classes": make_classes(),
    }

    manifest_path = (
        tmp_path
        / "00_manifesto_institucional.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    digest = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()

    summary = {
        "schema": compiler.EXPECTED_SCHEMA,
        "source_c4_sha256": (
            compiler.EXPECTED_SOURCE_C4_SHA256
        ),
        "base_manifest_sha256": digest,
        "database_writes": False,
    }

    (
        tmp_path / "06_resumo.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return manifest_path


def test_compiler_accepts_intact_base_manifest_hash(
    tmp_path,
):
    write_integrity_package(tmp_path)

    manifest = compiler.load_base_manifest(
        tmp_path
    )

    assert len(manifest["classes"]) == 78
    assert manifest["database_writes"] is False


def test_compiler_rejects_tampered_base_manifest(
    tmp_path,
):
    manifest_path = write_integrity_package(
        tmp_path
    )

    with manifest_path.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(" ")

    with pytest.raises(
        SystemExit,
        match="BASE_MANIFEST_SHA256_MISMATCH",
    ):
        compiler.load_base_manifest(
            tmp_path
        )


def test_compiler_requires_summary_hash(
    tmp_path,
):
    import json

    write_integrity_package(tmp_path)

    summary_path = (
        tmp_path / "06_resumo.json"
    )

    summary = json.loads(
        summary_path.read_text(
            encoding="utf-8"
        )
    )

    summary.pop(
        "base_manifest_sha256"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match=(
            "BASE_MANIFEST_SHA256_"
            "MISSING_OR_INVALID"
        ),
    ):
        compiler.load_base_manifest(
            tmp_path
        )


def test_generator_contains_operational_readme_contract():
    source = (
        generator.__file__
    )

    text = Path(source).read_text(
        encoding="utf-8"
    )

    required = (
        'output_dir / "README.txt"',
        "Nao inferir horarios.",
        "NAO EDITAR.",
        "course_id_resolved SEMPRE vazio",
        "READY_FOR_DRY_RUN",
        "nao grava MongoDB",
        "AEE",
        "nao faz parte deste escopo",
    )

    for marker in required:
        assert marker in text
