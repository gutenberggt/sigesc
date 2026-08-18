import { useEffect, useMemo, useRef } from 'react';
import { getDiaryPrefill } from '@/utils/diaryPrefill';

/**
 * Aplica uma única vez o contexto vindo do dashboard somente quando cada valor
 * existe nas listas já autorizadas pela própria tela. Query string é contexto
 * de UX, nunca fonte de autorização.
 *
 * As listas de escola/turma/componente são assíncronas. Por isso uma dimensão
 * só é marcada como aplicada depois que o ID alvo realmente aparece na lista
 * autorizada; uma lista intermediária não pode consumir o prefill cedo demais.
 */
export const useDiaryPrefill = ({
  schools = [],
  selectedSchool,
  setSelectedSchool,
  classes = [],
  selectedClass,
  setSelectedClass,
  courses = [],
  selectedCourse,
  setSelectedCourse,
  enabled = true,
  onCourseApplied,
} = {}) => {
  const prefill = useMemo(() => getDiaryPrefill(), []);
  const applied = useRef({ school: false, class: false, course: false });

  useEffect(() => {
    if (!enabled || applied.current.school || !prefill.schoolId || !setSelectedSchool) return;
    if (!Array.isArray(schools) || schools.length === 0) return;
    const authorized = schools.some((item) => item?.id === prefill.schoolId);
    if (!authorized) return;
    applied.current.school = true;
    if (!selectedSchool) {
      setSelectedSchool(prefill.schoolId);
    }
  }, [enabled, prefill.schoolId, schools, selectedSchool, setSelectedSchool]);

  useEffect(() => {
    if (!enabled || applied.current.class || !prefill.classId || !setSelectedClass) return;
    if (!selectedSchool || !Array.isArray(classes) || classes.length === 0) return;
    const authorized = classes.some((item) => item?.id === prefill.classId);
    if (!authorized) return;
    applied.current.class = true;
    if (!selectedClass) {
      setSelectedClass(prefill.classId);
    }
  }, [enabled, prefill.classId, classes, selectedSchool, selectedClass, setSelectedClass]);

  useEffect(() => {
    if (!enabled || applied.current.course || !prefill.courseId || !setSelectedCourse) return;
    if (!selectedClass || !Array.isArray(courses) || courses.length === 0) return;
    const authorized = courses.some((item) => item?.id === prefill.courseId);
    if (!authorized) return;
    applied.current.course = true;
    if (!selectedCourse) {
      setSelectedCourse(prefill.courseId);
      onCourseApplied?.(prefill.courseId);
    }
  }, [
    enabled,
    prefill.courseId,
    courses,
    selectedClass,
    selectedCourse,
    setSelectedCourse,
    onCourseApplied,
  ]);

  return prefill;
};
