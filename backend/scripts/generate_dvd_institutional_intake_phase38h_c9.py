#!/usr/bin/env python3

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path


DAYS = (
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
)

MAX_SLOTS_PER_DAY = 12

EXPECTED_C4_SHA256 = (
    "353c72ca0c2d90383fd2965ebf94d6bb"
    "fa2786a1513a446d4066aedd0718a740"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Gera o pacote operacional de coleta institucional "
            "DVD 38H-C9 a partir do manifesto C4 homologado."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Manifesto C4 homologado.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Diretório de saída do pacote C9.",
    )

    return parser.parse_args()


def sha256_file(path):
    import hashlib

    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_verified_source(path):
    actual_sha256 = sha256_file(path)

    if actual_sha256 != EXPECTED_C4_SHA256:
        raise SystemExit(
            "SOURCE_SHA256_MISMATCH: "
            f"expected={EXPECTED_C4_SHA256} "
            f"actual={actual_sha256}"
        )

    with path.open(
        encoding="utf-8"
    ) as f:
        package = json.load(f)

    classes = package.get("classes") or []

    if len(classes) != 78:
        raise SystemExit(
            "SOURCE_CLASS_COUNT_MISMATCH: "
            f"expected=78 actual={len(classes)}"
        )

    return package, actual_sha256


def validate_source_structure(package):
    classes = package.get("classes") or []

    class_ids = [
        str(entry.get("class_id") or "")
        for entry in classes
    ]

    school_ids = {
        str(entry.get("school_id") or "")
        for entry in classes
        if entry.get("school_id")
    }

    operations = {
        "CREATE": 0,
        "UPDATE": 0,
    }

    component_pairs = []

    for entry in classes:
        operation = str(
            entry.get("operation") or ""
        ).upper()

        if operation not in operations:
            raise SystemExit(
                "SOURCE_INVALID_OPERATION: "
                f"class_id={entry.get('class_id')} "
                f"operation={operation!r}"
            )

        operations[operation] += 1

        class_id = str(
            entry.get("class_id") or ""
        )

        for component in (
            entry.get("components") or []
        ):
            course_id = str(
                component.get("course_id") or ""
            )

            component_pairs.append(
                (class_id, course_id)
            )

    checks = {
        "classes": len(classes),
        "unique_class_ids": len(set(class_ids)),
        "schools": len(school_ids),
        "create": operations["CREATE"],
        "update": operations["UPDATE"],
        "components": len(component_pairs),
        "unique_class_course": len(
            set(component_pairs)
        ),
    }

    expected = {
        "classes": 78,
        "unique_class_ids": 78,
        "schools": 13,
        "create": 75,
        "update": 3,
        "components": 564,
        "unique_class_course": 564,
    }

    if checks != expected:
        raise SystemExit(
            "SOURCE_STRUCTURE_MISMATCH: "
            f"expected={expected} actual={checks}"
        )

    if any(not value for value in class_ids):
        raise SystemExit(
            "SOURCE_EMPTY_CLASS_ID"
        )

    if any(
        not class_id or not course_id
        for class_id, course_id
        in component_pairs
    ):
        raise SystemExit(
            "SOURCE_EMPTY_COMPONENT_ID"
        )

    return checks


def validate_source_structure(package):
    classes = package.get("classes") or []

    class_ids = [
        str(entry.get("class_id") or "")
        for entry in classes
    ]

    school_ids = {
        str(entry.get("school_id") or "")
        for entry in classes
        if entry.get("school_id")
    }

    operations = {
        "CREATE": 0,
        "UPDATE": 0,
    }

    component_pairs = []

    for entry in classes:
        operation = str(
            entry.get("operation") or ""
        ).upper()

        if operation not in operations:
            raise SystemExit(
                "SOURCE_INVALID_OPERATION: "
                f"class_id={entry.get('class_id')} "
                f"operation={operation!r}"
            )

        operations[operation] += 1

        class_id = str(
            entry.get("class_id") or ""
        )

        for component in (
            entry.get("components") or []
        ):
            course_id = str(
                component.get("course_id") or ""
            )

            component_pairs.append(
                (class_id, course_id)
            )

    checks = {
        "classes": len(classes),
        "unique_class_ids": len(set(class_ids)),
        "schools": len(school_ids),
        "create": operations["CREATE"],
        "update": operations["UPDATE"],
        "components": len(component_pairs),
        "unique_class_course": len(
            set(component_pairs)
        ),
    }

    expected = {
        "classes": 78,
        "unique_class_ids": 78,
        "schools": 13,
        "create": 75,
        "update": 3,
        "components": 564,
        "unique_class_course": 564,
    }

    if checks != expected:
        raise SystemExit(
            "SOURCE_STRUCTURE_MISMATCH: "
            f"expected={expected} actual={checks}"
        )

    if any(not value for value in class_ids):
        raise SystemExit(
            "SOURCE_EMPTY_CLASS_ID"
        )

    if any(
        not class_id or not course_id
        for class_id, course_id
        in component_pairs
    ):
        raise SystemExit(
            "SOURCE_EMPTY_COMPONENT_ID"
        )

    return checks


def write_csv(path, fieldnames, rows):
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def build_class_catalog(classes):
    rows = []

    for entry in classes:
        rows.append({
            "school_name": entry.get("school_name", ""),
            "school_id": entry.get("school_id", ""),
            "class_name": entry.get("class_name", ""),
            "class_id": entry.get("class_id", ""),
            "academic_year": entry.get("academic_year", ""),
            "shift": entry.get("shift", ""),
            "education_level": entry.get("education_level", ""),
            "grade_level": entry.get("grade_level", ""),
            "is_multi_grade": entry.get("is_multi_grade", ""),
            "series": entry.get("series", ""),
            "operation": entry.get("operation", ""),
            "schedule_state": entry.get("schedule_state", ""),
            "existing_schedule_id": entry.get(
                "existing_schedule_id",
                "",
            ),
            "component_count": entry.get(
                "component_count",
                "",
            ),
            "conditionally_ready_bindings": entry.get(
                "conditionally_ready_bindings_after_valid_schedule",
                "",
            ),
        })

    return rows


def build_component_catalog(classes):
    rows = []

    for entry in classes:
        for component in (
            entry.get("components") or []
        ):
            rows.append({
                "school_name": entry.get("school_name", ""),
                "school_id": entry.get("school_id", ""),
                "class_name": entry.get("class_name", ""),
                "class_id": entry.get("class_id", ""),
                "shift": entry.get("shift", ""),
                "course_name": component.get("course_name", ""),
                "course_id": component.get("course_id", ""),
                "teacher_assignment_count": component.get(
                    "teacher_assignment_count",
                    "",
                ),
                "staff_count": component.get(
                    "staff_count",
                    "",
                ),
                "has_substitution_assignment": component.get(
                    "has_substitution_assignment",
                    "",
                ),
                "atendimento_programa": component.get(
                    "atendimento_programa",
                    "",
                ),
                "optativo": component.get(
                    "optativo",
                    "",
                ),
                "workload": component.get(
                    "workload",
                    "",
                ),
            })

    return rows


def build_slot_time_grid(classes):
    rows = []

    for entry in classes:
        reference_times = (
            entry.get(
                "existing_slot_times_reference"
            )
            or {}
        )

        for slot_number in range(
            1,
            MAX_SLOTS_PER_DAY + 1,
        ):
            reference = (
                reference_times.get(
                    str(slot_number)
                )
                or reference_times.get(
                    slot_number
                )
                or {}
            )

            rows.append({
                "school_name": entry.get("school_name", ""),
                "class_name": entry.get("class_name", ""),
                "class_id": entry.get("class_id", ""),
                "shift": entry.get("shift", ""),
                "operation": entry.get("operation", ""),
                "slot_number": slot_number,
                "reference_start": reference.get("start", ""),
                "reference_end": reference.get("end", ""),
                "start_confirmed": "",
                "end_confirmed": "",
            })

    return rows


def build_weekly_grid(classes):
    rows = []

    for entry in classes:
        for day in DAYS:
            for slot_number in range(
                1,
                MAX_SLOTS_PER_DAY + 1,
            ):
                rows.append({
                    "school_name": entry.get("school_name", ""),
                    "class_name": entry.get("class_name", ""),
                    "class_id": entry.get("class_id", ""),
                    "shift": entry.get("shift", ""),
                    "day": day,
                    "slot_number": slot_number,
                    "course_name_confirmed": "",
                    "course_id_resolved": "",
                })

    return rows


def build_confirmation_catalog(classes):
    rows = []

    for entry in classes:
        rows.append({
            "school_name": entry.get("school_name", ""),
            "class_name": entry.get("class_name", ""),
            "class_id": entry.get("class_id", ""),
            "shift": entry.get("shift", ""),
            "slots_per_day_confirmed": "",
            "institutional_source": "",
            "confirmed_by": "",
            "confirmation_date": "",
            "notes": "",
        })

    return rows


def main():
    args = parse_args()

    source_path = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()

    package, source_sha256 = load_verified_source(
        source_path
    )

    checks = validate_source_structure(
        package
    )

    classes = deepcopy(
        package.get("classes") or []
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    class_rows = build_class_catalog(classes)
    component_rows = build_component_catalog(classes)
    slot_time_rows = build_slot_time_grid(classes)
    weekly_rows = build_weekly_grid(classes)
    confirmation_rows = build_confirmation_catalog(classes)

    write_csv(
        output_dir / "01_turmas_para_confirmacao.csv",
        list(class_rows[0].keys()),
        class_rows,
    )

    write_csv(
        output_dir / "02_componentes_por_turma.csv",
        list(component_rows[0].keys()),
        component_rows,
    )

    write_csv(
        output_dir / "03_horarios_de_aula_para_confirmacao.csv",
        list(slot_time_rows[0].keys()),
        slot_time_rows,
    )

    write_csv(
        output_dir / "04_distribuicao_semanal_para_confirmacao.csv",
        list(weekly_rows[0].keys()),
        weekly_rows,
    )

    write_csv(
        output_dir / "05_confirmacao_institucional.csv",
        list(confirmation_rows[0].keys()),
        confirmation_rows,
    )

    manifest = deepcopy(package)

    manifest["schema"] = (
        "SIGESC_DVD_38H_C9_OPERATIONAL_INTAKE_V1"
    )

    manifest["mode"] = (
        "INSTITUTIONAL_COLLECTION"
    )

    manifest["database_writes"] = False

    manifest["source_c4_sha256"] = (
        source_sha256
    )

    manifest["c9_structure_checks"] = (
        checks
    )

    for entry in manifest.get("classes") or []:
        entry["institutional_input"] = {
            "slots_per_day_confirmed": None,
            "slot_times_confirmed": {},
            "schedule_slots_confirmed": [],
            "institutional_source": "",
            "confirmed_by": "",
            "confirmation_date": "",
            "notes": "",
        }

    manifest_path = (
        output_dir
        / "00_manifesto_institucional.json"
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    base_manifest_sha256 = sha256_file(
        manifest_path
    )

    summary = {
        "schema": (
            "SIGESC_DVD_38H_C9_OPERATIONAL_INTAKE_V1"
        ),
        "source_c4_sha256": source_sha256,
        "base_manifest_sha256": (
            base_manifest_sha256
        ),
        "database_writes": False,
        "classes": len(class_rows),
        "components": len(component_rows),
        "slot_time_rows": len(slot_time_rows),
        "weekly_grid_rows": len(weekly_rows),
        "confirmation_rows": len(
            confirmation_rows
        ),
        "days": list(DAYS),
        "max_slots_per_day": (
            MAX_SLOTS_PER_DAY
        ),
    }

    with (
        output_dir / "06_resumo.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    readme = """SIGESC — DVD 38H-C9
COLETA INSTITUCIONAL DE HORARIOS

OBJETIVO
Este pacote serve exclusivamente para a confirmacao institucional dos
horarios das turmas que ainda nao possuem evidencia segura suficiente
no SIGESC.

REGRAS DE SEGURANCA
1. Nao inferir horarios.
2. Nao copiar horario de outra turma sem confirmacao institucional.
3. Nao criar professores, componentes ou identificadores.
4. Nao alterar class_id, school_id, course_id ou outros identificadores.
5. Dados existentes marcados como referencia NAO constituem confirmacao.
6. Este pacote nao grava MongoDB, class_schedules ou DVD.

ARQUIVOS

00_manifesto_institucional.json
- Arquivo-base canonico.
- NAO EDITAR.
- Sua integridade e protegida por SHA-256 registrado em 06_resumo.json.
- O compilador recusara o pacote se este arquivo for alterado.

01_turmas_para_confirmacao.csv
- Catalogo das 78 turmas.
- Somente referencia.
- NAO EDITAR.

02_componentes_por_turma.csv
- Catalogo canonico dos componentes de cada turma.
- Use o nome exatamente como apresentado neste arquivo.
- NAO EDITAR.

03_horarios_de_aula_para_confirmacao.csv
- Uma turma possui 12 linhas, uma para cada numero de aula possivel.
- Preencher start_confirmed e end_confirmed somente para as aulas
  efetivamente usadas, de 1 ate slots_per_day_confirmed.
- Formato obrigatorio: HH:MM.
- O horario final deve ser posterior ao inicial.
- reference_start e reference_end sao apenas referencias.
- Nunca copiar automaticamente referencia para confirmacao.

04_distribuicao_semanal_para_confirmacao.csv
- Grade estrutural de segunda a sexta, com slots de 1 a 12.
- Preencher somente course_name_confirmed.
- Deixar course_id_resolved SEMPRE vazio.
- O compilador resolve course_id_resolved de forma deterministica usando
  o catalogo canonico da propria turma.
- Utilizar apenas slots menores ou iguais a slots_per_day_confirmed.
- Um componente pode aparecer mais de uma vez na semana.
- Para uma turma ficar pronta, todo componente ativo deve aparecer pelo
  menos uma vez na distribuicao semanal.
- Celulas sem aula podem permanecer vazias.

05_confirmacao_institucional.csv
Para cada turma confirmada, preencher:
- slots_per_day_confirmed: inteiro de 1 a 12;
- institutional_source: fonte institucional da informacao;
- confirmed_by: responsavel pela confirmacao;
- confirmation_date: data no formato YYYY-MM-DD;
- notes: observacoes, quando necessarias.

06_resumo.json
- Metadados e controles de integridade do pacote.
- NAO EDITAR.
- Contem base_manifest_sha256.

FLUXO CORRETO
1. Identificar a turma em 01_turmas_para_confirmacao.csv.
2. Consultar seus componentes em 02_componentes_por_turma.csv.
3. Informar os horarios em 03_horarios_de_aula_para_confirmacao.csv.
4. Informar a distribuicao semanal em
   04_distribuicao_semanal_para_confirmacao.csv.
5. Registrar a confirmacao institucional em
   05_confirmacao_institucional.csv.
6. Executar o compilador C9.
7. Executar o validador operacional.
8. Somente turmas classificadas READY_FOR_DRY_RUN podem seguir para
   etapas posteriores.

IMPORTANTE
PENDING significa informacao institucional ainda incompleta.
INVALID significa inconsistencia que deve ser corrigida.
READY_FOR_DRY_RUN nao grava horarios nem cria DVD; significa apenas que
a turma passou pelas validacoes para a proxima etapa controlada.

AEE
O Atendimento Educacional Especializado (AEE) nao faz parte deste escopo.
"""

    (
        output_dir / "README.txt"
    ).write_text(
        readme,
        encoding="utf-8",
    )

    print(
        "STATUS=PASS"
    )
    print(
        f"CLASSES={len(class_rows)}"
    )
    print(
        f"COMPONENTS={len(component_rows)}"
    )
    print(
        f"SLOT_TIME_ROWS={len(slot_time_rows)}"
    )
    print(
        f"WEEKLY_GRID_ROWS={len(weekly_rows)}"
    )
    print(
        f"CONFIRMATION_ROWS={len(confirmation_rows)}"
    )
    print(
        f"SOURCE_SHA256={source_sha256}"
    )
    print(
        "DATABASE_WRITES=0"
    )


if __name__ == "__main__":
    main()
