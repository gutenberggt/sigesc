import axios from 'axios';

const BRIDGE_FLAG = '__sigescGradesDvdBridgeInstalled';
const gradeAssignmentById = new Map();
const gradeAssignmentByScope = new Map();
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

const scopeKey = (studentId, classId, courseId) => (
  `${studentId || ''}|${classId || ''}|${courseId || ''}`
);

const rememberStudentAssignments = (payload) => {
  const grades = payload?.grades || [];
  grades.forEach((grade) => {
    const assignmentId = grade?.dvd_assignment_id;
    if (!assignmentId) return;
    if (grade.id) gradeAssignmentById.set(String(grade.id), assignmentId);
    gradeAssignmentByScope.set(
      scopeKey(grade.student_id, grade.class_id, grade.course_id),
      assignmentId,
    );
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

    // Grades.js legado pede todos os estudantes. No portal do professor essa
    // chamada é substituída pelo roster canônico dos vínculos avaliativos.
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

    // Leituras agregadas resolvem vários vínculos no backend; nunca devem ser
    // presas ao assignment da URL raiz do diário.
    if (isAggregateStudentRead(url)) return config;

    const method = (config?.method || 'get').toLowerCase();

    // Edição da aba Por Estudante: vínculo da própria linha, não o da página.
    if (method === 'put') {
      const match = url.match(/\/grades\/([^/?]+)(?:\?|$)/);
      const gradeId = match?.[1];
      const rowAssignment = gradeId ? gradeAssignmentById.get(String(gradeId)) : null;
      if (rowAssignment) {
        config.url = appendAssignmentId(url, rowAssignment);
        return config;
      }
    }

    // Mantém suporte defensivo para criação individual futura na aba agregada.
    if (method === 'post' && !url.includes('/grades/batch')) {
      const payload = parseData(config.data);
      if (payload?.student_id && payload?.class_id && payload?.course_id) {
        const rowAssignment = gradeAssignmentByScope.get(
          scopeKey(payload.student_id, payload.class_id, payload.course_id),
        );
        if (rowAssignment) {
          config.url = appendAssignmentId(url, rowAssignment);
          return config;
        }
      }
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
