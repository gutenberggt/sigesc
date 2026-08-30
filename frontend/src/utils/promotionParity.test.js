import {
  buildPromotionGradeFilters,
  buildPromotionGradesByStudentFromByClass,
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

});
