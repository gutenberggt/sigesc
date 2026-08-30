from pathlib import Path

PROMOTION = Path('frontend/src/pages/Promotion.jsx')
PARITY = Path('frontend/src/utils/promotionParity.js')
TESTS = Path('frontend/src/utils/promotionParity.test.js')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'P0_250_F2_2_REPLACE_{label}_COUNT={count}')
    return text.replace(old, new, 1)


promotion = PROMOTION.read_text(encoding='utf-8')
promotion = replace_once(
    promotion,
    """import {\n  buildPromotionGradeFilters,\n  filterPromotionGradesForClass,\n  getProfessorPromotionCourseIds,\n  resolveProfessorPromotionCourses,\n} from '@/utils/promotionParity';""",
    """import {\n  buildPromotionGradeFilters,\n  buildPromotionGradesByStudentFromByClass,\n  filterPromotionGradesForClass,\n  getProfessorPromotionCourseIds,\n  resolveProfessorPromotionCourses,\n} from '@/utils/promotionParity';""",
    'IMPORT',
)

promotion = replace_once(
    promotion,
    """      // Buscar notas de todos os alunos PRESAS à turma selecionada.\n      // O filtro class_id elimina colisão com notas do mesmo estudante/ano em outra turma.\n      const gradesPromises = studentIds.map(studentId => \n        gradesAPI.getAll(\n          buildPromotionGradeFilters(studentId, selectedClass, selectedYear)\n        )\n      );\n      const allGrades = await Promise.all(gradesPromises);\n      \n      // Processar dados de promoção""",
    """      // P0 #250 F2.2 — paridade HTTP com a tela de Notas.\n      // Professor: usa a mesma projeção canônica por turma + componente.\n      // Perfis de gestão preservam o caminho institucional existente desta tela.\n      const gradesByStudent = new Map(\n        studentIds.map(studentId => [String(studentId), []])\n      );\n\n      if (restrictToProfessor) {\n        const byClassResponses = await Promise.all(\n          orderedCourses.map(course =>\n            gradesAPI.getByClass(selectedClass, course.id, selectedYear)\n          )\n        );\n\n        const projectedByStudent = buildPromotionGradesByStudentFromByClass(\n          byClassResponses,\n          studentIds,\n          selectedClass,\n          orderedCourses\n        );\n        projectedByStudent.forEach((studentGrades, studentId) => {\n          gradesByStudent.set(String(studentId), studentGrades);\n        });\n      } else {\n        const gradesPromises = studentIds.map(studentId =>\n          gradesAPI.getAll(\n            buildPromotionGradeFilters(studentId, selectedClass, selectedYear)\n          )\n        );\n        const allGrades = await Promise.all(gradesPromises);\n        studentIds.forEach((studentId, index) => {\n          gradesByStudent.set(\n            String(studentId),\n            filterPromotionGradesForClass(\n              allGrades[index] || [],\n              selectedClass,\n              orderedCourses\n            )\n          );\n        });\n      }\n      \n      // Processar dados de promoção""",
    'GRADE_LOAD',
)

promotion = replace_once(
    promotion,
    """        // Encontrar o índice correto das notas baseado no studentId\n        const studentIdIndex = studentIds.indexOf(student.id);\n        const rawStudentGrades = studentIdIndex >= 0 ? (allGrades[studentIdIndex] || []) : [];\n        // Defesa em profundidade: mesmo que a API devolva payload mais amplo,\n        // apenas turma atual + componentes exibíveis entram na projeção.\n        const studentGrades = filterPromotionGradesForClass(\n          rawStudentGrades,\n          selectedClass,\n          orderedCourses\n        );""",
    """        // A projeção já está indexada pelo roster canônico do Livro.\n        // No perfil professor, qualquer 22º aluno retornado por /grades/by-class\n        // é descartado antes desta etapa.\n        const studentGrades = gradesByStudent.get(String(student.id)) || [];""",
    'STUDENT_PROJECTION',
)

PROMOTION.write_text(promotion, encoding='utf-8')

parity = PARITY.read_text(encoding='utf-8')
helper = """

export const buildPromotionGradesByStudentFromByClass = (
  courseResponses = [],
  studentIds = [],
  classId,
  allowedCourses = []
) => {
  const byStudent = new Map(
    (studentIds || [])
      .filter(Boolean)
      .map(studentId => [String(studentId), []])
  );

  if (!classId || byStudent.size === 0) return byStudent;

  const allowedCourseIds = new Set(
    (allowedCourses || [])
      .map(course => course?.id ?? course)
      .filter(Boolean)
      .map(String)
  );

  // Fail-closed: sem entitlement curricular explícito, nenhuma nota é projetada.
  if (allowedCourseIds.size === 0) return byStudent;

  const seenPairs = new Set();
  (courseResponses || []).forEach(rows => {
    (rows || []).forEach(row => {
      const grade = row?.grade;
      const studentId = row?.student?.id ?? grade?.student_id;
      if (!grade || !studentId) return;

      const normalizedStudentId = String(studentId);
      const normalizedCourseId = String(grade?.course_id || '');
      if (!byStudent.has(normalizedStudentId)) return;
      if (String(grade?.class_id || '') !== String(classId)) return;
      if (!allowedCourseIds.has(normalizedCourseId)) return;

      const pairKey = `${normalizedStudentId}::${normalizedCourseId}`;
      if (seenPairs.has(pairKey)) return;
      seenPairs.add(pairKey);

      byStudent.get(normalizedStudentId).push(grade);
    });
  });

  return byStudent;
};
"""
if 'export const buildPromotionGradesByStudentFromByClass' in parity:
    raise SystemExit('P0_250_F2_2_HELPER_ALREADY_PRESENT')
parity = parity.rstrip() + helper + '\n'
PARITY.write_text(parity, encoding='utf-8')

tests = TESTS.read_text(encoding='utf-8')
tests = replace_once(
    tests,
    """import {\n  buildPromotionGradeFilters,\n  filterPromotionGradesForClass,""",
    """import {\n  buildPromotionGradeFilters,\n  buildPromotionGradesByStudentFromByClass,\n  filterPromotionGradesForClass,""",
    'TEST_IMPORT',
)

new_test = r"""

  test('F2.2 projeta exatamente 21 x 9 pares do by-class e descarta o 22º aluno', () => {
    const promotionStudentIds = Array.from(
      { length: 21 },
      (_, index) => `student-${index + 1}`
    );

    const byClassResponses = allCourses.slice(0, 9).map((course, courseIndex) => [
      ...promotionStudentIds.map((currentStudentId, studentIndex) => ({
        student: { id: currentStudentId },
        grade: {
          id: `grade-${courseIndex + 1}-${studentIndex + 1}`,
          student_id: currentStudentId,
          class_id: classA,
          course_id: course.id,
          academic_year: 2026,
          b1: 8,
          b2: 9,
        },
      })),
      {
        student: { id: 'student-22' },
        grade: {
          id: `outside-${courseIndex + 1}`,
          student_id: 'student-22',
          class_id: classA,
          course_id: course.id,
          academic_year: 2026,
          b1: 10,
        },
      },
    ]);

    // Mesmo que uma resposta extra de componente não autorizado seja entregue,
    // a projeção deve permanecer fail-closed nos 9 course_id do vínculo docente.
    byClassResponses.push([
      {
        student: { id: promotionStudentIds[0] },
        grade: {
          id: 'unauthorized-course-grade',
          student_id: promotionStudentIds[0],
          class_id: classA,
          course_id: 'course-10',
          academic_year: 2026,
          b1: 10,
        },
      },
    ]);

    const projected = buildPromotionGradesByStudentFromByClass(
      byClassResponses,
      promotionStudentIds,
      classA,
      allCourses.slice(0, 9)
    );

    expect(projected.size).toBe(21);
    expect(projected.has('student-22')).toBe(false);
    expect(
      Array.from(projected.values()).reduce((total, grades) => total + grades.length, 0)
    ).toBe(189);

    promotionStudentIds.forEach(currentStudentId => {
      const studentGrades = projected.get(currentStudentId);
      expect(studentGrades).toHaveLength(9);
      expect(new Set(studentGrades.map(grade => grade.course_id)).size).toBe(9);
      expect(studentGrades.some(grade => grade.course_id === 'course-10')).toBe(false);
    });
  });
"""
closing = '\n});\n'
if not tests.endswith(closing):
    raise SystemExit('P0_250_F2_2_TEST_FILE_END_UNEXPECTED')
tests = tests[:-len(closing)] + new_test + closing
TESTS.write_text(tests, encoding='utf-8')

# Guards de wiring: a fase só é válida se o caminho do professor tiver sido trocado.
final_promotion = PROMOTION.read_text(encoding='utf-8')
required_markers = [
    'P0 #250 F2.2 — paridade HTTP com a tela de Notas.',
    'gradesAPI.getByClass(selectedClass, course.id, selectedYear)',
    'buildPromotionGradesByStudentFromByClass(',
    'const studentGrades = gradesByStudent.get(String(student.id)) || [];',
]
for marker in required_markers:
    if marker not in final_promotion:
        raise SystemExit(f'P0_250_F2_2_MARKER_MISSING:{marker}')

print('P0_250_F2_2_PATCH=PASS')
