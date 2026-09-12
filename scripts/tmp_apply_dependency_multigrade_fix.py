from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Frontend: canonical series equivalence.
utils_path = Path("frontend/src/features/dependency/dependency.utils.js")
utils_text = utils_path.read_text(encoding="utf-8")
if "export function seriesTokens(" not in utils_text:
    utils_text += r'''

/**
 * Converte rótulos de série/etapa em tokens semânticos estáveis.
 * Exemplos: "6º ANO", "6º Ano", "6° ano" -> {"ano:6"};
 * "6º/7º/9º Ano" -> {"ano:6", "ano:7", "ano:9"};
 * "3ª ETAPA" -> {"eja:3"}.
 */
export function seriesTokens(value) {
  const values = Array.isArray(value) ? value : [value];
  const tokens = new Set();

  values.forEach((raw) => {
    if (raw === null || raw === undefined) return;
    const text = String(raw)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
    const prefix = (text.includes('eja') || text.includes('etapa')) ? 'eja' : 'ano';
    const numericGroups = text
      .replace(/[º°ª]/g, ' ')
      .split(/[^0-9]+/)
      .filter(Boolean);

    numericGroups.forEach((group) => {
      if (/^[1-9]$/.test(group)) tokens.add(`${prefix}:${group}`);
    });
  });

  return tokens;
}

/**
 * True quando dois rótulos representam pelo menos a mesma série/etapa,
 * independentemente de caixa, espaços ou símbolo ordinal.
 */
export function seriesMatches(left, right) {
  const a = seriesTokens(left);
  const b = seriesTokens(right);
  if (a.size === 0 || b.size === 0) return false;
  for (const token of a) {
    if (b.has(token)) return true;
  }
  return false;
}
'''
    utils_path.write_text(utils_text, encoding="utf-8")

replace_once(
    "frontend/src/components/StudentDependencySection.jsx",
    "import { studentDependenciesAPI, classesAPI, schoolsAPI } from '@/services/api';\n",
    "import { studentDependenciesAPI, classesAPI, schoolsAPI } from '@/services/api';\n"
    "import { seriesMatches } from '@/features/dependency/dependency.utils';\n",
)
replace_once(
    "frontend/src/components/StudentDependencySection.jsx",
    "            || c.grade_levels.includes(selectedSeries))",
    "            || c.grade_levels.some((gradeLevel) => seriesMatches(gradeLevel, selectedSeries)))",
)
replace_once(
    "frontend/src/components/StudentDependencySection.jsx",
    '  //   - componente com grade_levels = ["6º Ano",...] → mostra só se inclui a série escolhida\n',
    '  //   - componente com grade_levels = ["6º Ano",...] → compara a série por equivalência canônica\n',
)

# Backend: validate destination class + course + target series during creation.
replace_once(
    "backend/utils/dependency_validator.py",
    "from fastapi import HTTPException\n",
    "from fastapi import HTTPException\n\nfrom utils.curriculum_resolver import _series_tokens\n",
)

validator_path = Path("backend/utils/dependency_validator.py")
validator_text = validator_path.read_text(encoding="utf-8")
if "def validate_dependency_target_values(" not in validator_text:
    validator_text += r'''


def _target_error(code: str, message: str, **extra) -> None:
    detail = {"code": code, "message": message}
    detail.update(extra)
    raise HTTPException(status_code=422, detail=detail)


def validate_dependency_target_values(
    *,
    class_doc: dict,
    course_doc: dict,
    effective_course_ids,
    school_id: str,
    course_id: str,
    target_series: Optional[str],
) -> dict:
    """Valida, sem I/O, a coerência curricular do destino da dependência.

    A matrícula regular atual do estudante não participa desta decisão. O vínculo
    é determinado pela turma de destino, sua série efetiva e pelo componente
    efetivamente oferecido nela.
    """
    if class_doc.get("school_id") != school_id:
        _target_error(
            "DEPENDENCY_TARGET_SCHOOL_MISMATCH",
            "A turma selecionada não pertence à escola de destino informada.",
            class_school_id=class_doc.get("school_id"),
            requested_school_id=school_id,
        )

    effective_ids = {str(value) for value in (effective_course_ids or []) if value}
    if course_id not in effective_ids:
        _target_error(
            "DEPENDENCY_TARGET_COURSE_NOT_IN_CLASS",
            "O componente selecionado não integra a matriz/vínculos ativos da turma de destino.",
            class_id=class_doc.get("id"),
            course_id=course_id,
        )

    class_tokens = _series_tokens(class_doc.get("series") or class_doc.get("grade_level"))
    target_tokens = _series_tokens(target_series)
    is_multi_with_choice = bool(class_doc.get("is_multi_grade")) and len(class_tokens) >= 2

    if is_multi_with_choice:
        if not target_tokens:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_REQUIRED",
                "Turma multisseriada exige a série da dependência.",
                class_id=class_doc.get("id"),
            )
        if len(target_tokens) != 1:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_AMBIGUOUS",
                "Selecione uma única série para a dependência.",
                target_series=target_series,
            )
        if not target_tokens.issubset(class_tokens):
            _target_error(
                "DEPENDENCY_TARGET_SERIES_NOT_IN_CLASS",
                "A série selecionada não é atendida pela turma multisseriada de destino.",
                target_series=target_series,
                class_series=class_doc.get("series") or class_doc.get("grade_level"),
            )
        effective_series_tokens = target_tokens
    else:
        regular_tokens = _series_tokens(class_doc.get("grade_level"))
        if target_tokens and regular_tokens and not (target_tokens & regular_tokens):
            _target_error(
                "DEPENDENCY_TARGET_SERIES_NOT_IN_CLASS",
                "A série informada não corresponde à turma de destino.",
                target_series=target_series,
                class_grade_level=class_doc.get("grade_level"),
            )
        effective_series_tokens = target_tokens or regular_tokens or class_tokens

    grade_levels = course_doc.get("grade_levels") or []
    if grade_levels:
        course_tokens = _series_tokens(grade_levels)
        if not course_tokens:
            _target_error(
                "DEPENDENCY_TARGET_COURSE_SERIES_UNVERIFIABLE",
                "O componente possui escopo de série cadastrado, mas ele não pôde ser interpretado com segurança.",
                course_id=course_id,
                grade_levels=grade_levels,
            )
        if not effective_series_tokens:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_CONTEXT_MISSING",
                "Não foi possível determinar a série efetiva da dependência.",
                class_id=class_doc.get("id"),
            )
        if not (course_tokens & effective_series_tokens):
            _target_error(
                "DEPENDENCY_TARGET_COURSE_SERIES_MISMATCH",
                "O componente selecionado não se aplica à série escolhida para a dependência.",
                course_id=course_id,
                target_series=target_series or class_doc.get("grade_level"),
                grade_levels=grade_levels,
            )

    return {
        "class_id": class_doc.get("id"),
        "course_id": course_id,
        "target_series": target_series or class_doc.get("grade_level"),
        "is_multi_grade": bool(class_doc.get("is_multi_grade")),
    }


async def validate_dependency_target(
    *,
    db,
    class_id: str,
    school_id: str,
    course_id: str,
    target_series: Optional[str],
    tenant_id: Optional[str],
) -> dict:
    """Valida criação contra a matriz efetiva da turma de destino.

    Replica o contrato do endpoint `/classes/{id}/curriculum`:
    `class.course_ids ∪ teacher_assignments ativos`.
    """
    cls = await db.classes.find_one(
        {"id": class_id},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "course_ids": 1,
            "is_multi_grade": 1,
            "series": 1,
            "grade_level": 1,
        },
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Turma de destino não encontrada.")
    if tenant_id and cls.get("mantenedora_id") and cls.get("mantenedora_id") != tenant_id:
        _target_error(
            "DEPENDENCY_TARGET_CLASS_TENANT_MISMATCH",
            "A turma de destino pertence a outra mantenedora.",
        )

    effective_ids = []
    seen = set()
    for cid in (cls.get("course_ids") or []):
        if cid and cid not in seen:
            seen.add(cid)
            effective_ids.append(cid)

    async for assignment in db.teacher_assignments.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo", "ativo"]}},
        {"_id": 0, "course_id": 1},
    ):
        cid = assignment.get("course_id")
        if cid and cid not in seen:
            seen.add(cid)
            effective_ids.append(cid)

    course = await db.courses.find_one(
        {"id": course_id},
        {"_id": 0, "id": 1, "mantenedora_id": 1, "grade_levels": 1},
    )
    if not course:
        raise HTTPException(status_code=404, detail="Componente curricular não encontrado.")
    if tenant_id and course.get("mantenedora_id") and course.get("mantenedora_id") != tenant_id:
        _target_error(
            "DEPENDENCY_TARGET_COURSE_TENANT_MISMATCH",
            "O componente selecionado pertence a outra mantenedora.",
        )

    return validate_dependency_target_values(
        class_doc=cls,
        course_doc=course,
        effective_course_ids=effective_ids,
        school_id=school_id,
        course_id=course_id,
        target_series=target_series,
    )
'''
    validator_path.write_text(validator_text, encoding="utf-8")

replace_once(
    "backend/routers/student_dependencies.py",
    "from models import StudentDependency, StudentDependencyCreate, StudentDependencyUpdate\n",
    "from models import StudentDependency, StudentDependencyCreate, StudentDependencyUpdate\n"
    "from utils.dependency_validator import validate_dependency_target\n",
)
replace_once(
    "backend/routers/student_dependencies.py",
    "        await _validate_dependency_limit(payload.student_id, mantenedora_id, request)\n"
    "        await _check_duplicate(payload.student_id, payload.course_id, payload.origin_academic_year)\n",
    "        await _validate_dependency_limit(payload.student_id, mantenedora_id, request)\n"
    "        await validate_dependency_target(\n"
    "            db=db,\n"
    "            class_id=payload.class_id,\n"
    "            school_id=payload.school_id,\n"
    "            course_id=payload.course_id,\n"
    "            target_series=payload.target_series,\n"
    "            tenant_id=mantenedora_id,\n"
    "        )\n"
    "        await _check_duplicate(payload.student_id, payload.course_id, payload.origin_academic_year)\n",
)

# Regression tests.
Path("frontend/src/features/dependency/dependency.utils.test.js").write_text(
    r'''import { seriesMatches, seriesTokens } from './dependency.utils';

describe('dependency series canonicalization', () => {
  test('normalizes case and ordinal variants', () => {
    expect(seriesMatches('6º ANO', '6º Ano')).toBe(true);
    expect(seriesMatches('6° ano', '6º ANO')).toBe(true);
    expect(seriesMatches('6 ANO', '6º ANO')).toBe(true);
  });

  test('matches a selected series inside a multiseries component scope', () => {
    expect(seriesMatches('6º/7º/9º Ano', '6º ANO')).toBe(true);
    expect(seriesMatches('6º/7º/9º Ano', '8º ANO')).toBe(false);
  });

  test('keeps EJA stages distinct from regular years', () => {
    expect(Array.from(seriesTokens('3ª ETAPA'))).toEqual(['eja:3']);
    expect(seriesMatches('3ª ETAPA', '3º ANO')).toBe(false);
  });
});
''',
    encoding="utf-8",
)

Path("backend/tests/test_dependency_target_curriculum.py").write_text(
    r'''import pytest
from fastapi import HTTPException

from utils.dependency_validator import validate_dependency_target_values


def _class(**overrides):
    doc = {
        "id": "class-67",
        "school_id": "school-sao-bras",
        "is_multi_grade": True,
        "series": ["6º ANO", "7º ANO"],
        "grade_level": "6º E 7º ANO",
    }
    doc.update(overrides)
    return doc


def _course(**overrides):
    doc = {"id": "course-lp", "grade_levels": ["6º Ano"]}
    doc.update(overrides)
    return doc


def test_accepts_equivalent_series_spelling_for_multigrade_target():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(),
        effective_course_ids=["course-lp", "course-mat"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6º ANO",
    )
    assert result["target_series"] == "6º ANO"


def test_accepts_component_scope_that_contains_selected_series():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(grade_levels=["6º/7º/9º Ano"]),
        effective_course_ids=["course-lp"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6° ano",
    )
    assert result["course_id"] == "course-lp"


def test_rejects_component_from_other_series():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(grade_levels=["7º ANO"]),
            effective_course_ids=["course-lp"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series="6º ANO",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_COURSE_SERIES_MISMATCH"


def test_rejects_course_not_offered_by_destination_class():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(),
            effective_course_ids=["course-mat"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series="6º ANO",
        )
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_COURSE_NOT_IN_CLASS"


def test_requires_series_for_real_multigrade_class():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(),
            effective_course_ids=["course-lp"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series=None,
        )
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_SERIES_REQUIRED"


def test_course_without_grade_levels_applies_to_selected_series():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(grade_levels=[]),
        effective_course_ids=["course-lp"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6º ANO",
    )
    assert result["class_id"] == "class-67"
''',
    encoding="utf-8",
)

print("DEPENDENCY_MULTIGRADE_FIX_APPLIED")
