import {
  buildPromotionGradeFilters,
  filterPromotionGradesForClass,
  getProfessorPromotionCourseIds,
  resolveProfessorPromotionCourses,
} from './promotionParity';

describe('Issue #250 - paridade Notas x Livro de Promoção', () => {
  const classA = 'class-5a';
  const classB = 'class-5b';
  const studentId = 'student-1';

  const allCourses = Array.from({ length: 10 }, (_, index) => ({
    id: `course-${index + 1}`,
    name: `Componente ${index + 1}`,
  }));

  const professorTurmas = [
    {
      id: classA,
      componentes: allCourses.slice(0, 9).map(course => ({
        id: course.id,
        name: course.name,
      })),
    },
  ];

  test('mantém exatamente os 9 componentes autorizados e não amplia para o 10º', () => {
    const ids = getProfessorPromotionCourseIds(professorTurmas, classA);
    const visible = resolveProfessorPromotionCourses(allCourses, professorTurmas, classA);

    expect(ids).toHaveLength(9);
    expect(visible.map(course => course.id)).toEqual(
      allCourses.slice(0, 9).map(course => course.id)
    );
    expect(visible.some(course => course.id === 'course-10')).toBe(false);
  });

  test('falha fechado quando a turma não possui componentes no vínculo docente', () => {
    expect(getProfessorPromotionCourseIds(professorTurmas, classB)).toEqual([]);
    expect(resolveProfessorPromotionCourses(allCourses, professorTurmas, classB)).toEqual([]);
  });

  test('a consulta de notas fica presa a estudante + turma + ano letivo', () => {
    expect(buildPromotionGradeFilters(studentId, classA, 2026)).toEqual({
      student_id: studentId,
      class_id: classA,
      academic_year: 2026,
    });
  });

  test('nota da mesma pessoa/ano em outra turma não contamina a promoção', () => {
    const grades = [
      {
        id: 'grade-current',
        student_id: studentId,
        class_id: classA,
        course_id: 'course-1',
        academic_year: 2026,
        b1: 9,
        b2: 9,
      },
      {
        id: 'grade-other-class',
        student_id: studentId,
        class_id: classB,
        course_id: 'course-1',
        academic_year: 2026,
        b1: null,
        b2: null,
      },
      {
        id: 'grade-unauthorized-course',
        student_id: studentId,
        class_id: classA,
        course_id: 'course-10',
        academic_year: 2026,
        b1: 10,
        b2: 10,
      },
    ];

    const visibleCourses = resolveProfessorPromotionCourses(
      allCourses,
      professorTurmas,
      classA
    );
    const projected = filterPromotionGradesForClass(
      grades,
      classA,
      visibleCourses
    );

    expect(projected).toEqual([grades[0]]);
    expect(projected[0].b1).toBe(9);
    expect(projected[0].b2).toBe(9);
  });
});
