import axios from 'axios';

const BRIDGE_FLAG = '__sigescGradesDvdBridgeInstalled';
const gradeAssignmentById = new Map();
const gradeAssignmentByScope = new Map();
const gradeCreationByStudentCourse = new Map();
let currentAcademicYear = new Date().getFullYear();

const getAssignmentId = () => {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search || '').get('assignment_id') || '';
};

const isProfessorGradesPage = () => (
  typeof window !== 'undefined'
  && window.location.pathname === '/professor/notas'
);

const appendAssignmentId = (url, assignmentId) => {
  if (!url || !assignmentId) return url;
  if (/(?:[?&])assignment_id=/.test(url)) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}assignment_id=${encodeURIComponent(assignmentId)}`;
};

const parseData = (data) => {
  if (!data) return null;
  if (typeof data === 'object') return data;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
};

const replaceData = (config, original, payload) => {
  config.data = typeof original === 'string' ? JSON.stringify(payload) : payload;
};

const scopeKey = (studentId, classId, courseId) => (
  `${studentId || ''}|${classId || ''}|${courseId || ''}`
);
const studentCourseKey = (studentId, courseId) => (
  `${studentId || ''}|${courseId || ''}`
);

const rememberStudentAssignments = (payload) => {
  gradeAssignmentById.clear();
  gradeAssignmentByScope.clear();
  gradeCreationByStudentCourse.clear();

  const grades = payload?.grades || [];
  grades.forEach((grade) => {
    const assignmentId = grade?.dvd_assignment_id;
    const studentId = grade?.student_id;
    const classId = grade?.class_id;
    const courseId = grade?.course_id;
    if (!assignmentId || !studentId || !classId || !courseId) return;

    if (grade.id) gradeAssignmentById.set(String(grade.id), assignmentId);
    gradeAssignmentByScope.set(
      scopeKey(studentId, classId, courseId),
      assignmentId,
    );

    // Grades.js legado cria a primeira nota usando selectedStudent.class_id.
    // Guardamos a linha canônica para poder corrigir o class_id antes do POST.
    const simpleKey = studentCourseKey(studentId, courseId);
    const existing = gradeCreationByStudentCourse.get(simpleKey);
    const candidate = { assignmentId, classId };
    if (existing === undefined) {
      gradeCreationByStudentCourse.set(simpleKey, candidate);
    } else if (
      existing !== null
      && (existing.assignmentId !== assignmentId || existing.classId !== classId)
    ) {
      // Mesmo estudante/componente em mais de uma turma: não arbitramos.
      gradeCreationByStudentCourse.set(simpleKey, null);
    }
  });
};

const isAggregateStudentRead = (url = '') => (
  url.includes('/grades/by-student/')
  || url.includes('/grades/dvd/teacher-students')
);

/**
 * Preserva o vínculo do diário para a visão Por Turma e, na visão Por
 * Estudante, usa o assignment específico devolvido pelo backend para cada
 * linha/componente. Também troca a listagem ampla de /students pelo roster
 * avaliativo do professor enquanto a página /professor/notas estiver aberta.
 */
export const installGradesDvdAxiosBridge = () => {
  if (typeof window === 'undefined' || window[BRIDGE_FLAG]) return;
  window[BRIDGE_FLAG] = true;

  axios.interceptors.request.use((config) => {
    const url = config?.url || '';

    if (isProfessorGradesPage() && url.includes('/professor/turmas')) {
      const requestedYear = Number(config?.params?.academic_year);
      if (Number.isFinite(requestedYear) && requestedYear > 1900) {
        currentAcademicYear = requestedYear;
      }
    }

    if (
      isProfessorGradesPage()
      && (config?.method || 'get').toLowerCase() === 'get'
      && /\/students(?:\?.*)?$/.test(url)
    ) {
      config.url = url.replace(
        /\/students(?:\?.*)?$/,
        '/grades/dvd/teacher-students',
      );
      config.params = { academic_year: currentAcademicYear };
      return config;
    }

    if (!url.includes('/grades')) return config;
    if (isAggregateStudentRead(url)) return config;

    const method = (config?.method || 'get').toLowerCase();

    // PUT individual é exclusivo da visão Por Estudante na tela atual.
    if (isProfessorGradesPage() && method === 'put') {
      const match = url.match(/\/grades\/([^/?]+)(?:\?|$)/);
      const gradeId = match?.[1];
      const rowAssignment = gradeId ? gradeAssignmentById.get(String(gradeId)) : null;
      if (rowAssignment) {
        config.url = appendAssignmentId(url, rowAssignment);
      }
      // Sem mapa, deixa o backend resolver/falhar fechado; nunca reutiliza o
      // assignment raiz de outro componente para uma edição agregada.
      return config;
    }

    if (
      isProfessorGradesPage()
      && method === 'post'
      && !url.includes('/grades/batch')
    ) {
      const originalData = config.data;
      const payload = parseData(originalData);
      if (payload?.student_id && payload?.course_id) {
        let assignmentId = null;

        if (payload.class_id) {
          assignmentId = gradeAssignmentByScope.get(
            scopeKey(payload.student_id, payload.class_id, payload.course_id),
          ) || null;
        }

        if (!assignmentId) {
          const creationScope = gradeCreationByStudentCourse.get(
            studentCourseKey(payload.student_id, payload.course_id),
          );
          if (creationScope) {
            payload.class_id = creationScope.classId;
            assignmentId = creationScope.assignmentId;
            replaceData(config, originalData, payload);
          }
        }

        if (assignmentId) {
          config.url = appendAssignmentId(url, assignmentId);
        }
      }
      // Sem resolução unívoca, backend recebe a requisição sem spoof de vínculo
      // e decide fail-closed pelo class/course informado.
      return config;
    }

    const assignmentId = getAssignmentId();
    if (!assignmentId) return config;
    config.url = appendAssignmentId(config.url, assignmentId);
    return config;
  });

  axios.interceptors.response.use((response) => {
    const url = response?.config?.url || '';
    if (url.includes('/grades/by-student/')) {
      rememberStudentAssignments(response.data);
    }
    return response;
  });
};

installGradesDvdAxiosBridge();
