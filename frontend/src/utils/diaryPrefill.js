const safeYear = (value) => {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 2000 || parsed > 2100) return null;
  return parsed;
};

export const getDiaryPrefill = () => {
  if (typeof window === 'undefined') {
    return {
      academicYear: null,
      schoolId: '',
      classId: '',
      courseId: '',
      assignmentId: '',
    };
  }

  const params = new URLSearchParams(window.location.search || '');
  return {
    academicYear: safeYear(params.get('academic_year')),
    schoolId: params.get('school_id') || '',
    classId: params.get('class_id') || '',
    courseId: params.get('course_id') || '',
    assignmentId: params.get('assignment_id') || '',
  };
};

export const buildDiaryActionUrl = (path, context = {}) => {
  const params = new URLSearchParams();
  const append = (key, value) => {
    if (value !== null && value !== undefined && value !== '') {
      params.set(key, String(value));
    }
  };

  append('academic_year', context.academicYear);
  append('school_id', context.schoolId);
  append('class_id', context.classId);
  append('course_id', context.courseId);
  append('assignment_id', context.assignmentId);

  const query = params.toString();
  return query ? `${path}?${query}` : path;
};
