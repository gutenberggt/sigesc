import { useEffect, useMemo, useRef } from 'react';
import { getDiaryPrefill } from '@/utils/diaryPrefill';

/**
 * Aplica uma única vez o contexto vindo do dashboard somente quando cada valor
 * existe nas listas já autorizadas pela própria tela. Query string é contexto
 * de UX, nunca fonte de autorização.
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
    applied.current.school = true;
    if (!selectedSchool && schools.some((item) => item?.id === prefill.schoolId)) {
      setSelectedSchool(prefill.schoolId);
    }
  }, [enabled, prefill.schoolId, schools, selectedSchool, setSelectedSchool]);

  useEffect(() => {
    if (!enabled || applied.current.class || !prefill.classId || !setSelectedClass) return;
    if (!selectedSchool || !Array.isArray(classes) || classes.length === 0) return;
    applied.current.class = true;
    if (!selectedClass && classes.some((item) => item?.id === prefill.classId)) {
      setSelectedClass(prefill.classId);
    }
  }, [enabled, prefill.classId, classes, selectedSchool, selectedClass, setSelectedClass]);

  useEffect(() => {
    if (!enabled || applied.current.course || !prefill.courseId || !setSelectedCourse) return;
    if (!selectedClass || !Array.isArray(courses) || courses.length === 0) return;
    applied.current.course = true;
    if (!selectedCourse && courses.some((item) => item?.id === prefill.courseId)) {
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
