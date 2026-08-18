import { createContext, useContext } from 'react';
import { useDiaryPrefill } from '@/hooks/useDiaryPrefill';
import '@/services/gradesDvdBridge';

export const GradesContext = createContext(null);

export const useGrades = () => {
  const ctx = useContext(GradesContext);
  if (!ctx) {
    throw new Error('useGrades must be used inside <GradesContext.Provider>');
  }

  useDiaryPrefill({
    schools: ctx.schools,
    selectedSchool: ctx.selectedSchool,
    setSelectedSchool: ctx.setSelectedSchool,
    classes: ctx.filteredClasses,
    selectedClass: ctx.selectedClass,
    setSelectedClass: ctx.setSelectedClass,
    courses: ctx.filteredCourses,
    selectedCourse: ctx.selectedCourse,
    setSelectedCourse: ctx.setSelectedCourse,
  });

  return ctx;
};
