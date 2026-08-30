// Contrato de paridade do Livro de Promoção para o perfil professor.
// Issue #250: a autorização curricular nasce exclusivamente de /professor/turmas
// e toda projeção de notas permanece presa à turma selecionada.

export const getProfessorPromotionCourseIds = (professorTurmas = [], classId) => {
  if (!classId) return [];

  const turma = (professorTurmas || []).find(
    item => String(item?.id || '') === String(classId)
  );

  return [...new Set(
    (turma?.componentes || [])
      .map(component => component?.id)
      .filter(Boolean)
      .map(String)
  )];
};

export const resolveProfessorPromotionCourses = (
  allCourses = [],
  professorTurmas = [],
  classId
) => {
  const authorizedIds = new Set(
    getProfessorPromotionCourseIds(professorTurmas, classId)
  );

  // Fail-closed: ausência de vínculo explícito significa ausência de componentes.
  if (authorizedIds.size === 0) return [];

  return (allCourses || []).filter(
    course => course?.id && authorizedIds.has(String(course.id))
  );
};

export const buildPromotionGradeFilters = (studentId, classId, academicYear) => ({
  student_id: studentId,
  class_id: classId,
  academic_year: academicYear,
});

export const filterPromotionGradesForClass = (
  grades = [],
  classId,
  allowedCourses = []
) => {
  if (!classId) return [];

  const allowedCourseIds = new Set(
    (allowedCourses || [])
      .map(course => course?.id ?? course)
      .filter(Boolean)
      .map(String)
  );

  // Fail-closed também na projeção de notas: sem componente exibível,
  // nenhum registro acadêmico é reaproveitado por nome ou por fallback.
  if (allowedCourseIds.size === 0) return [];

  return (grades || []).filter(grade =>
    String(grade?.class_id || '') === String(classId) &&
    allowedCourseIds.has(String(grade?.course_id || ''))
  );
};

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

