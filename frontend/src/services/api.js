import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// G2 (Fev/2026): envia cookies HttpOnly em todas as requests.
// Indispensável para auth via cookie `sigesc_access` + CSRF double-submit.
axios.defaults.withCredentials = true;

// Configura interceptor para incluir token
export const getToken = () => localStorage.getItem('accessToken');

// Multi-tenancy: super_admin pode selecionar uma mantenedora ativa
export const getActiveTenantId = () => localStorage.getItem('activeMantenedoraId');

// Lê cookie (usado para CSRF double-submit). Não-HttpOnly por design.
function readCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

const CSRF_COOKIE_NAME = 'sigesc_csrf';
const CSRF_STORAGE_KEY = 'sigesc_csrf_token';
const CSRF_WRITE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

// G2 fix Mai/2026: em deploys cross-domain (frontend ≠ backend) o cookie CSRF
// fica vinculado ao domínio do backend e o JS não consegue lê-lo via
// document.cookie. O backend retorna o csrf_token no body do /login e /refresh.
// Jun/2026: passamos a guardar em localStorage (e não sessionStorage) para que o
// token CSRF seja COMPARTILHADO ENTRE ABAS. sessionStorage é isolado por aba, o
// que fazia POSTs de uma aba recém-aberta irem SEM CSRF → 403 "CSRF inválido".
export function setCsrfToken(token) {
  if (token) {
    try { localStorage.setItem(CSRF_STORAGE_KEY, token); } catch { /* ignore */ }
    // Limpa resíduo antigo em sessionStorage para evitar divergência entre abas.
    try { sessionStorage.removeItem(CSRF_STORAGE_KEY); } catch { /* ignore */ }
  }
}
export function clearCsrfToken() {
  try { localStorage.removeItem(CSRF_STORAGE_KEY); } catch { /* ignore */ }
  try { sessionStorage.removeItem(CSRF_STORAGE_KEY); } catch { /* ignore */ }
}
export function getCsrfToken() {
  try {
    const stored = localStorage.getItem(CSRF_STORAGE_KEY);
    if (stored) return stored;
  } catch { /* ignore */ }
  // Fallbacks: sessionStorage (sessões antigas nesta aba) e cookie (mesmo domínio).
  try {
    const legacy = sessionStorage.getItem(CSRF_STORAGE_KEY);
    if (legacy) return legacy;
  } catch { /* ignore */ }
  return readCookie(CSRF_COOKIE_NAME);
}

// P1 (Jun/2026) — LOGIN UNIVERSAL. Endpoints de autenticação NUNCA podem
// carregar estado anterior (token antigo, tenant anterior, CSRF). Isso evita:
//  - preflight CORS quebrado quando `X-Mantenedora-Id` obsoleto é injetado;
//  - contaminação de contexto entre usuários/mantenedoras.
// O backend isenta esses endpoints de CSRF e não exige Authorization.
const PRISTINE_AUTH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh'];
function isPristineAuthRequest(config) {
  const url = config.url || '';
  return PRISTINE_AUTH_PATHS.some((p) => url.includes(p));
}

// P1 (Jun/2026) — Reset total do estado local da aplicação ("primeira visita").
// Executar em: logout, erro de autenticação e troca de usuário.
// Limpa tokens, tenant ativo, contexto selecionado, CSRF e quaisquer caches locais.
export function clearApplicationState() {
  try { localStorage.clear(); } catch { /* ignore */ }
  try { sessionStorage.clear(); } catch { /* ignore */ }
}

axios.interceptors.request.use(
  (config) => {
    // Requests de autenticação são pristinas: sem token/tenant/CSRF herdados.
    if (isPristineAuthRequest(config)) {
      return config;
    }
    // Retrocompat: continua enviando Bearer se token em localStorage.
    // Backend lê cookie primeiro, fallback Bearer — migração gradual.
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Injeta X-Mantenedora-Id para super_admin com tenant ativo
    const tenantId = getActiveTenantId();
    if (tenantId) {
      config.headers['X-Mantenedora-Id'] = tenantId;
    }
    // CSRF: envia header em requests de escrita.
    // Prioridade: sessionStorage (cross-domain) → cookie (mesmo domínio).
    const method = (config.method || 'get').toLowerCase();
    if (CSRF_WRITE_METHODS.has(method)) {
      const csrf = getCsrfToken();
      if (csrf) {
        config.headers['X-CSRF-Token'] = csrf;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ============= AUTH & PERMISSIONS =============
export const authAPI = {
  getPermissions: async () => {
    const response = await axios.get(`${API}/auth/permissions`);
    return response.data;
  },
  
  getMe: async () => {
    const response = await axios.get(`${API}/auth/me`);
    return response.data;
  }
};

// ============= SCHOOLS =============
export const schoolsAPI = {
  list: async () => {
    const response = await axios.get(`${API}/schools`);
    return response.data;
  },
  
  getAll: async () => {
    const response = await axios.get(`${API}/schools`);
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/schools/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/schools`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/schools/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/schools/${id}`);
  },
  
  migrateBercario: async () => {
    const response = await axios.post(`${API}/schools/migrate-bercario`);
    return response.data;
  }
};

// ============= USERS =============
export const usersAPI = {
  getAll: async () => {
    const response = await axios.get(`${API}/users`);
    return response.data;
  },

  count: async () => {
    const response = await axios.get(`${API}/users/count`);
    return response.data; // { total, total_active }
  },

  getById: async (id) => {
    const response = await axios.get(`${API}/users/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/auth/register`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/users/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/users/${id}`);
  }
};

// ============= CLASSES (TURMAS) =============
export const classesAPI = {
  list: async (schoolId = null) => {
    const params = schoolId ? { school_id: schoolId, _t: Date.now() } : { _t: Date.now() };
    const response = await axios.get(`${API}/classes`, { params });
    return response.data;
  },
  
  getAll: async (schoolId = null) => {
    const params = schoolId ? { school_id: schoolId, _t: Date.now() } : { _t: Date.now() };
    const response = await axios.get(`${API}/classes`, { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/classes/${id}`);
    return response.data;
  },
  
  getDetails: async (id) => {
    const response = await axios.get(`${API}/classes/${id}/details`);
    return response.data;
  },

  getCancelledEnrollments: async (id) => {
    const response = await axios.get(`${API}/classes/${id}/cancelled-enrollments`);
    return response.data;
  },

  getCurriculum: async (id) => {
    const response = await axios.get(`${API}/classes/${id}/curriculum`);
    return response.data;
  },
  
  getDetailsPdf: async (id) => {
    const response = await axios.get(`${API}/classes/${id}/details/pdf`, {
      responseType: 'blob'
    });
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/classes`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/classes/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/classes/${id}`);
  }
};

// ============= COURSES (COMPONENTES CURRICULARES) =============
export const coursesAPI = {
  list: async (nivelEnsino = null) => {
    const params = nivelEnsino ? { nivel_ensino: nivelEnsino } : {};
    const response = await axios.get(`${API}/courses`, { params });
    return response.data;
  },
  
  getAll: async (nivelEnsino = null) => {
    const params = nivelEnsino ? { nivel_ensino: nivelEnsino } : {};
    const response = await axios.get(`${API}/courses`, { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/courses/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/courses`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/courses/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/courses/${id}`);
  }
};

// ============= CPF VALIDATION =============
export const cpfAPI = {
  validate: async (cpf) => {
    // Endpoint vive sob o router /students no backend (prefix="/students").
    const response = await axios.get(`${API}/students/validate-cpf/${cpf}`);
    return response.data;
  },
  
  checkDuplicate: async (cpf, context = 'student', excludeId = null) => {
    const params = { context };
    if (excludeId) params.exclude_id = excludeId;
    // Endpoint vive sob o router /students no backend (prefix="/students").
    const response = await axios.get(`${API}/students/check-cpf-duplicate/${cpf}`, { params });
    return response.data;
  }
};

// ============= STUDENTS (ALUNOS) =============
export const studentsAPI = {
  getAll: async (params = {}) => {
    const response = await axios.get(`${API}/students`, { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/students/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/students`, data);
    return response.data;
  },
  
  update: async (id, data, opts = {}) => {
    const headers = {};
    // [Fev/2026] Confirma cancelamento de dependências ativas ao mudar para 'none'.
    if (opts.confirmCancelDependencies) {
      headers['X-Confirm-Cancel-Dependencies'] = 'yes';
    }
    const response = await axios.put(`${API}/students/${id}`, data, { headers });
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/students/${id}`);
  },
  
  getHistory: async (id) => {
    const response = await axios.get(`${API}/students/${id}/history`);
    return response.data;
  },
  
  transfer: async (id, data) => {
    const response = await axios.post(`${API}/students/${id}/transfer`, data);
    return response.data;
  },

  cancelTransfer: async (id, classId) => {
    const response = await axios.post(
      `${API}/students/${id}/cancel-transfer`,
      classId ? { class_id: classId } : {}
    );
    return response.data;
  },

  repairEnrollment: async () => {
    const response = await axios.post(`${API}/students/enrollment-audit/repair`, {});
    return response.data;
  },

  auditSeriesSync: async () => {
    const response = await axios.get(`${API}/students/series-sync/audit`);
    return response.data;
  },

  repairSeriesSync: async () => {
    const response = await axios.post(`${API}/students/series-sync/repair`, {});
    return response.data;
  }
};

// ============= GUARDIANS (RESPONSÁVEIS) =============
export const guardiansAPI = {
  getAll: async () => {
    const response = await axios.get(`${API}/guardians`);
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/guardians/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/guardians`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/guardians/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/guardians/${id}`);
  }
};

// ============= ENROLLMENTS (MATRÍCULAS) =============
export const enrollmentsAPI = {
  getAll: async (studentId = null, classId = null) => {
    const params = {};
    if (studentId) params.student_id = studentId;
    if (classId) params.class_id = classId;
    const response = await axios.get(`${API}/enrollments`, { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/enrollments/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/enrollments`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/enrollments/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/enrollments/${id}`);
  },

  /**
   * Feb 2026: Cancela uma matrícula ativa (desvincula aluno da turma).
   * Centraliza chamada antes espalhada como `fetch()` em StudentsComplete.
   * @param {object} payload - { student_id, class_id, reason }
   */
  cancel: async (payload) => {
    const response = await axios.post(`${API}/enrollments/cancel-enrollment`, payload);
    return response.data;
  },

  /**
   * Feb 2026: Copia notas/frequência do aluno para nova turma após remanejamento,
   * progressão ou reclassificação (congelamento + cópia para turma destino).
   * @param {string} studentId
   * @param {object} payload - { source_class_id, target_class_id, copy_type, academic_year }
   */
  copyData: async (studentId, payload) => {
    const response = await axios.post(`${API}/students/${studentId}/copy-data`, payload);
    return response.data;
  }
};

// ============= GRADES =============
export const gradesAPI = {
  getAll: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.student_id) params.append('student_id', filters.student_id);
    if (filters.class_id) params.append('class_id', filters.class_id);
    if (filters.course_id) params.append('course_id', filters.course_id);
    if (filters.academic_year) params.append('academic_year', filters.academic_year);
    const response = await axios.get(`${API}/grades?${params.toString()}`);
    return response.data;
  },
  
  getByClass: async (classId, courseId, academicYear = null) => {
    let url = `${API}/grades/by-class/${classId}/${courseId}`;
    if (academicYear) url += `?academic_year=${academicYear}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  getByStudent: async (studentId, academicYear = null) => {
    let url = `${API}/grades/by-student/${studentId}`;
    if (academicYear) url += `?academic_year=${academicYear}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/grades`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/grades/${id}`, data);
    return response.data;
  },
  
  updateBatch: async (grades) => {
    const response = await axios.post(`${API}/grades/batch`, grades);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/grades/${id}`);
  },

  getPdfBlob: async (classId, courseId, bimestres, academicYear, studentSeries = null) => {
    const bimestresParam = [...bimestres].sort().join(',');
    let url = `${API}/grades/pdf/${classId}/${courseId}?bimestres=${bimestresParam}&academic_year=${academicYear}`;
    if (studentSeries) url += `&student_series=${encodeURIComponent(studentSeries)}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  }
};

// ============= FILE UPLOAD =============
export const uploadAPI = {
  upload: async (file, fileType = 'default') => {
    const formData = new FormData();
    formData.append('file', file);
    // Envia file_type como query parameter para garantir que seja interpretado corretamente
    const response = await axios.post(`${API}/upload?file_type=${fileType}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return response.data;
  },
  
  delete: async (filename) => {
    await axios.delete(`${API}/upload/${filename}`);
  },
  
  getUrl: (url) => {
    if (!url) return null;
    // Se já é uma URL completa, retorna como está
    if (url.startsWith('http')) return url;
    // Se é um caminho antigo /uploads/, converte para /api/uploads/
    if (url.startsWith('/uploads/')) {
      return `${BACKEND_URL}/api${url}`;
    }
    // Se é um caminho relativo, adiciona a URL do backend
    return `${BACKEND_URL}${url}`;
  }
};

// ============= CALENDAR EVENTS =============
export const calendarAPI = {
  getEvents: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.academic_year) queryParams.append('academic_year', params.academic_year);
    if (params.start_date) queryParams.append('start_date', params.start_date);
    if (params.end_date) queryParams.append('end_date', params.end_date);
    if (params.event_type) queryParams.append('event_type', params.event_type);
    
    const url = `${API}/calendar/events${queryParams.toString() ? '?' + queryParams.toString() : ''}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/calendar/events/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/calendar/events`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/calendar/events/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/calendar/events/${id}`);
  },
  
  checkDate: async (date) => {
    const response = await axios.get(`${API}/calendar/check-date/${date}`);
    return response.data;
  },
  
  getSummary: async (academicYear) => {
    const response = await axios.get(`${API}/calendar/summary/${academicYear}`);
    return response.data;
  },
  
  // ===== CALENDÁRIO LETIVO - PERÍODOS BIMESTRAIS =====
  getCalendarioLetivo: async (anoLetivo, schoolId = null) => {
    const params = schoolId ? `?school_id=${schoolId}` : '';
    const response = await axios.get(`${API}/calendario-letivo/${anoLetivo}${params}`);
    return response.data;
  },
  
  updateCalendarioLetivo: async (anoLetivo, data, schoolId = null) => {
    const params = schoolId ? `?school_id=${schoolId}` : '';
    const response = await axios.put(`${API}/calendario-letivo/${anoLetivo}${params}`, data);
    return response.data;
  },
  
  getDiasLetivos: async (anoLetivo, schoolId = null) => {
    const params = schoolId ? `?school_id=${schoolId}` : '';
    const response = await axios.get(`${API}/calendario-letivo/${anoLetivo}/dias-letivos${params}`);
    return response.data;
  },
  
  getPeriodosBimestrais: async (anoLetivo, schoolId = null) => {
    const params = schoolId ? `?school_id=${schoolId}` : '';
    const response = await axios.get(`${API}/calendario-letivo/${anoLetivo}/periodos${params}`);
    return response.data;
  },
  
  getEditStatus: async (anoLetivo, bimestre = null) => {
    const params = bimestre ? `?bimestre=${bimestre}` : '';
    const response = await axios.get(`${API}/calendario-letivo/${anoLetivo}/status-edicao${params}`);
    return response.data;
  }
};

// ============= ATTENDANCE (FREQUÊNCIA) =============
export const attendanceAPI = {
  getSettings: async (academicYear) => {
    const response = await axios.get(`${API}/attendance/settings/${academicYear}`);
    return response.data;
  },
  
  updateSettings: async (academicYear, allowFutureDates) => {
    const response = await axios.put(`${API}/attendance/settings/${academicYear}?allow_future_dates=${allowFutureDates}`);
    return response.data;
  },
  
  checkDate: async (date) => {
    const response = await axios.get(`${API}/attendance/check-date/${date}`);
    return response.data;
  },
  
  getByClass: async (classId, date, courseId = null, period = 'regular') => {
    let url = `${API}/attendance/by-class/${classId}/${date}?period=${period}`;
    if (courseId) url += `&course_id=${courseId}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  save: async (data) => {
    const response = await axios.post(`${API}/attendance`, data);
    return response.data;
  },
  
  delete: async (attendanceId) => {
    const response = await axios.delete(`${API}/attendance/${attendanceId}`);
    return response.data;
  },
  
  getStudentReport: async (studentId, academicYear) => {
    const response = await axios.get(`${API}/attendance/report/student/${studentId}?academic_year=${academicYear}`);
    return response.data;
  },
  
  // Frequência calculada para Assistência Social
  // Fórmula: ((Dias Letivos até hoje - Faltas) / Dias Letivos até hoje) × 100
  getStudentFrequency: async (studentId, academicYear) => {
    const response = await axios.get(`${API}/attendance/frequency/student/${studentId}?academic_year=${academicYear}`);
    return response.data;
  },
  
  getClassReport: async (classId, academicYear, courseId = null, bimestre = null) => {
    let url = `${API}/attendance/report/class/${classId}?academic_year=${academicYear}`;
    if (courseId) url += `&course_id=${courseId}`;
    if (bimestre) url += `&bimestre=${bimestre}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  getAlerts: async (schoolId = null, academicYear = null) => {
    let url = `${API}/attendance/alerts?`;
    if (schoolId) url += `school_id=${schoolId}&`;
    if (academicYear) url += `academic_year=${academicYear}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  getAttendanceSummary: async (classId, academicYear, courseId = null) => {
    let url = `${API}/attendance/attendance-summary/${classId}?academic_year=${academicYear}`;
    if (courseId) url += `&course_id=${courseId}`;
    const response = await axios.get(url);
    return response.data;
  },

  getScheduleClassesCount: async (classId, courseId, date, academicYear) => {
    const response = await axios.get(`${API}/attendance/schedule-classes-count?class_id=${classId}&course_id=${courseId}&date=${date}&academic_year=${academicYear}`);
    return response.data;
  },

  getDatesWithRecords: async (classId, academicYear, courseId = null) => {
    let url = `${API}/attendance/dates-with-records?class_id=${classId}&academic_year=${academicYear}`;
    if (courseId) url += `&course_id=${courseId}`;
    const response = await axios.get(url);
    return response.data;
  },

  getBimestreSummary: async (classId, academicYear, courseId = null) => {
    let url = `${API}/attendance/bimestre-summary?class_id=${classId}&academic_year=${academicYear}`;
    if (courseId) url += `&course_id=${courseId}`;
    const response = await axios.get(url);
    return response.data;
  },

  getClassStudentsInfo: async (classId, academicYear) => {
    const response = await axios.get(`${API}/attendance/class-students-info/${classId}?academic_year=${academicYear}`);
    return response.data;
  },

  getBimestrePdfBlob: async (classId, bimestre, academicYear, courseId = null) => {
    let url = `${API}/attendance/pdf/bimestre/${classId}?bimestre=${bimestre}&academic_year=${academicYear}`;
    if (courseId) url += `&course_id=${courseId}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  }
};

// ============= VACCINES =============
export const vaccinesAPI = {
  getStatusBatch: async (studentIds, academicYear) => {
    const ids = Array.isArray(studentIds) ? studentIds.join(',') : studentIds;
    const response = await axios.get(`${API}/vaccines/status/batch?student_ids=${ids}&academic_year=${academicYear}`);
    return response.data;
  }
};

// ============= STAFF (SERVIDORES) =============
export const staffAPI = {
  list: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.school_id) queryParams.append('school_id', params.school_id);
    if (params.cargo) queryParams.append('cargo', params.cargo);
    if (params.status) queryParams.append('status', params.status);
    const response = await axios.get(`${API}/staff?${queryParams}`);
    return response.data;
  },
  
  get: async (id) => {
    const response = await axios.get(`${API}/staff/${id}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/staff`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/staff/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await axios.delete(`${API}/staff/${id}`);
    return response.data;
  },
  
  uploadPhoto: async (staffId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axios.post(`${API}/staff/${staffId}/photo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }
};

// ============= SCHOOL ASSIGNMENTS (LOTAÇÕES) =============
export const schoolAssignmentAPI = {
  list: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.school_id) queryParams.append('school_id', params.school_id);
    if (params.staff_id) queryParams.append('staff_id', params.staff_id);
    if (params.status) queryParams.append('status', params.status);
    if (params.academic_year) queryParams.append('academic_year', params.academic_year);
    const response = await axios.get(`${API}/school-assignments?${queryParams}`);
    return response.data;
  },
  
  getStaffSchools: async (staffId, academicYear = null) => {
    let url = `${API}/school-assignments/staff/${staffId}/schools`;
    if (academicYear) url += `?academic_year=${academicYear}`;
    const response = await axios.get(url);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/school-assignments`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/school-assignments/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await axios.delete(`${API}/school-assignments/${id}`);
    return response.data;
  }
};

// ============= TEACHER ASSIGNMENTS (ALOCAÇÃO DE PROFESSORES) =============
export const teacherAssignmentAPI = {
  list: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.school_id) queryParams.append('school_id', params.school_id);
    if (params.staff_id) queryParams.append('staff_id', params.staff_id);
    if (params.class_id) queryParams.append('class_id', params.class_id);
    if (params.course_id) queryParams.append('course_id', params.course_id);
    if (params.academic_year) queryParams.append('academic_year', params.academic_year);
    if (params.status) queryParams.append('status', params.status);
    const response = await axios.get(`${API}/teacher-assignments?${queryParams}`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await axios.post(`${API}/teacher-assignments`, data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/teacher-assignments/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await axios.delete(`${API}/teacher-assignments/${id}`);
    return response.data;
  },

  createSubstitution: async (data) => {
    const response = await axios.post(`${API}/teacher-assignments/substitutions`, data);
    return response.data;
  }
};

// ============= PROFESSOR API =============
export const professorAPI = {
  // Retorna o perfil do professor logado
  getProfile: async () => {
    const response = await axios.get(`${API}/professor/me`);
    return response.data;
  },
  
  // Retorna as turmas do professor logado
  getTurmas: async (academicYear = null) => {
    const params = academicYear ? { academic_year: academicYear } : {};
    const response = await axios.get(`${API}/professor/turmas`, { params });
    return response.data;
  },
  
  // Retorna os alunos de uma turma
  getTurmaAlunos: async (classId) => {
    const response = await axios.get(`${API}/professor/turmas/${classId}/alunos`);
    return response.data;
  },
  
  // Retorna as notas de uma turma/componente
  getTurmaNotas: async (classId, courseId, bimestre = null) => {
    const params = bimestre ? { bimestre } : {};
    const response = await axios.get(`${API}/professor/turmas/${classId}/componentes/${courseId}/notas`, { params });
    return response.data;
  },
  
  // Retorna a frequência de uma turma/componente
  getTurmaFrequencia: async (classId, courseId, month = null, year = null) => {
    const params = {};
    if (month) params.month = month;
    if (year) params.year = year;
    const response = await axios.get(`${API}/professor/turmas/${classId}/componentes/${courseId}/frequencia`, { params });
    return response.data;
  }
};

// ============= LEARNING OBJECTS API (Objetos de Conhecimento) =============
export const learningObjectsAPI = {
  // Lista objetos de conhecimento com filtros
  list: async (filters = {}) => {
    const response = await axios.get(`${API}/learning-objects`, { params: filters });
    return response.data;
  },
  
  // Busca um objeto específico
  get: async (id) => {
    const response = await axios.get(`${API}/learning-objects/${id}`);
    return response.data;
  },
  
  // Cria um novo registro
  create: async (data) => {
    const response = await axios.post(`${API}/learning-objects`, data);
    return response.data;
  },
  
  // Atualiza um registro
  update: async (id, data) => {
    const response = await axios.put(`${API}/learning-objects/${id}`, data);
    return response.data;
  },
  
  // Exclui um registro
  delete: async (id) => {
    const response = await axios.delete(`${API}/learning-objects/${id}`);
    return response.data;
  },
  
  // Adiciona método de cópia ao learningObjectsAPI ao final
  copyToClass: async (id, payload) => {
    const response = await axios.post(`${API}/learning-objects/${id}/copy-to-class`, payload);
    return response.data;
  },

  // Verifica se existe registro para uma data
  checkDate: async (classId, courseId, date) => {
    const response = await axios.get(`${API}/learning-objects/check-date/${classId}/${courseId}/${date}`);
    return response.data;
  }
};

// ============= PROFILES API =============
export const profilesAPI = {
  // Obter meu perfil
  getMyProfile: async () => {
    const response = await axios.get(`${API}/profiles/me`);
    return response.data;
  },
  
  // Obter perfil por ID do usuário
  getByUserId: async (userId) => {
    const response = await axios.get(`${API}/profiles/${userId}`);
    return response.data;
  },
  
  // Atualizar meu perfil
  updateMyProfile: async (data) => {
    const response = await axios.put(`${API}/profiles/me`, data);
    return response.data;
  },
  
  // Admin: Atualizar perfil de outro usuário
  updateProfile: async (userId, data) => {
    const response = await axios.put(`${API}/profiles/${userId}`, data);
    return response.data;
  },
  
  // Buscar perfis públicos por nome (mínimo 3 caracteres)
  search: async (query) => {
    const response = await axios.get(`${API}/profiles/search`, { params: { q: query } });
    return response.data;
  }
};

// ============= CONNECTIONS API =============
export const connectionsAPI = {
  // Listar conexões aceitas
  list: async () => {
    const response = await axios.get(`${API}/connections`);
    return response.data;
  },
  
  // Listar convites pendentes recebidos
  listPending: async () => {
    const response = await axios.get(`${API}/connections/pending`);
    return response.data;
  },
  
  // Listar convites enviados pendentes
  listSent: async () => {
    const response = await axios.get(`${API}/connections/sent`);
    return response.data;
  },
  
  // Verificar status de conexão com um usuário
  getStatus: async (userId) => {
    const response = await axios.get(`${API}/connections/status/${userId}`);
    return response.data;
  },
  
  // Enviar convite de conexão
  invite: async (receiverId, message = null) => {
    const response = await axios.post(`${API}/connections/invite`, { 
      receiver_id: receiverId, 
      message 
    });
    return response.data;
  },
  
  // Aceitar convite
  accept: async (connectionId) => {
    const response = await axios.post(`${API}/connections/${connectionId}/accept`);
    return response.data;
  },
  
  // Rejeitar convite
  reject: async (connectionId) => {
    const response = await axios.post(`${API}/connections/${connectionId}/reject`);
    return response.data;
  },
  
  // Remover conexão
  remove: async (connectionId) => {
    await axios.delete(`${API}/connections/${connectionId}`);
  },

  // Criar conexão direta (admin <-> qualquer usuário)
  createDirect: async (userId) => {
    const response = await axios.post(`${API}/connections/direct/${userId}`);
    return response.data;
  }
};

// ============= MESSAGES API =============
export const messagesAPI = {
  // Enviar mensagem
  send: async (receiverId, content, attachments = []) => {
    const response = await axios.post(`${API}/messages`, {
      receiver_id: receiverId,
      content,
      attachments
    });
    return response.data;
  },
  
  // Listar mensagens de uma conexão
  getMessages: async (connectionId, limit = 50, before = null) => {
    const params = { limit };
    if (before) params.before = before;
    const response = await axios.get(`${API}/messages/${connectionId}`, { params });
    return response.data;
  },
  
  // Listar todas as conversas
  listConversations: async () => {
    const response = await axios.get(`${API}/messages/conversations/list`);
    return response.data;
  },
  
  // Marcar mensagem como lida
  markAsRead: async (messageId) => {
    const response = await axios.post(`${API}/messages/${messageId}/read`);
    return response.data;
  },
  
  // Obter contagem de não lidas
  getUnreadCount: async () => {
    const response = await axios.get(`${API}/messages/unread/count`);
    return response.data;
  },
  
  // Excluir uma mensagem
  deleteMessage: async (messageId) => {
    const response = await axios.delete(`${API}/messages/${messageId}`);
    return response.data;
  },
  
  // Excluir toda a conversa
  deleteConversation: async (connectionId) => {
    const response = await axios.delete(`${API}/messages/conversation/${connectionId}`);
    return response.data;
  }
};

// ============= MESSAGE LOGS API (ADMIN) =============
export const messageLogsAPI = {
  // Listar usuários com logs
  listUsers: async () => {
    const response = await axios.get(`${API}/admin/message-logs/users`);
    return response.data;
  },
  
  // Obter logs de um usuário específico
  getUserLogs: async (userId) => {
    const response = await axios.get(`${API}/admin/message-logs/user/${userId}`);
    return response.data;
  },
  
  // Listar todos os logs (com filtro opcional)
  list: async (userId = null, limit = 100) => {
    const params = { limit };
    if (userId) params.user_id = userId;
    const response = await axios.get(`${API}/admin/message-logs`, { params });
    return response.data;
  },
  
  // Limpar logs expirados
  cleanupExpired: async () => {
    const response = await axios.delete(`${API}/admin/message-logs/expired`);
    return response.data;
  }
};

// ============= ANNOUNCEMENTS API =============
export const announcementsAPI = {
  // Criar aviso
  create: async (data) => {
    const response = await axios.post(`${API}/announcements`, data);
    return response.data;
  },
  
  // Listar avisos
  list: async (skip = 0, limit = 50) => {
    const response = await axios.get(`${API}/announcements`, {
      params: { skip, limit }
    });
    return response.data;
  },
  
  // Obter aviso específico
  get: async (id) => {
    const response = await axios.get(`${API}/announcements/${id}`);
    return response.data;
  },
  
  // Atualizar aviso
  update: async (id, data) => {
    const response = await axios.put(`${API}/announcements/${id}`, data);
    return response.data;
  },
  
  // Excluir aviso
  delete: async (id) => {
    const response = await axios.delete(`${API}/announcements/${id}`);
    return response.data;
  },
  
  // Marcar como lido
  markAsRead: async (id) => {
    const response = await axios.post(`${API}/announcements/${id}/read`);
    return response.data;
  }
};

// ============= NOTIFICATIONS API =============
export const notificationsAPI = {
  // Obter contagem de não lidas
  getUnreadCount: async () => {
    const response = await axios.get(`${API}/notifications/unread-count`);
    return response.data;
  }
};

// ============= DOCUMENTS API =============
export const documentsAPI = {
  // Gerar Boletim Escolar (retorna URL do PDF)
  getBoletimUrl: (studentId, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/boletim/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Declaração de Matrícula (retorna URL do PDF)
  getDeclaracaoMatriculaUrl: (studentId, academicYear = new Date().getFullYear().toString(), purpose = 'fins comprobatórios') => {
    return `${BACKEND_URL}/api/documents/declaracao-matricula/${studentId}?academic_year=${academicYear}&purpose=${encodeURIComponent(purpose)}`;
  },
  
  // Gerar Declaração de Frequência (retorna URL do PDF)
  getDeclaracaoFrequenciaUrl: (studentId, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/declaracao-frequencia/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Ficha Individual (retorna URL do PDF)
  getFichaIndividualUrl: (studentId, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/ficha-individual/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Certificado (retorna URL do PDF)
  getCertificadoUrl: (studentId, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/certificado/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Declaração de Transferência (retorna URL do PDF)
  getDeclaracaoTransferenciaUrl: (studentId, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/declaracao-transferencia/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar documentos em lote (PDF consolidado da turma)
  getBatchDocumentsUrl: (classId, documentType, academicYear = new Date().getFullYear().toString()) => {
    return `${BACKEND_URL}/api/documents/batch/${classId}/${documentType}?academic_year=${academicYear}`;
  },
  
  // Baixar documento com autenticação
  downloadDocument: async (url) => {
    const response = await axios.get(url, {
      responseType: 'blob'
    });
    return response.data;
  },
  
  // Baixar Boletim (retorna blob)
  getBoletim: async (studentId, academicYear = String(new Date().getFullYear())) => {
    const url = `${BACKEND_URL}/api/documents/boletim/${studentId}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  },
  
  // Baixar Ficha Individual (retorna blob)
  getFichaIndividual: async (studentId, academicYear = String(new Date().getFullYear())) => {
    const url = `${BACKEND_URL}/api/documents/ficha-individual/${studentId}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  },
  
  // Baixar Certificado (retorna blob)
  getCertificado: async (studentId, academicYear = String(new Date().getFullYear())) => {
    const url = `${BACKEND_URL}/api/documents/certificado/${studentId}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  },
  
  // Baixar documentos em lote (retorna blob)
  getBatchDocuments: async (classId, documentType, academicYear = String(new Date().getFullYear())) => {
    const url = `${BACKEND_URL}/api/documents/batch/${classId}/${documentType}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  }
};

// ============= MANTENEDORA =============
export const mantenedoraAPI = {
  get: async () => {
    const response = await axios.get(`${API}/mantenedora`);
    return response.data;
  },
  
  update: async (data) => {
    const response = await axios.put(`${API}/mantenedora`, data);
    return response.data;
  }
};

// WebSocket URL
export const getWebSocketUrl = () => {
  const token = getToken();
  if (!token) return null;
  // Determinar protocolo WebSocket baseado no BACKEND_URL
  const backendUrl = new URL(BACKEND_URL);
  const wsProtocol = backendUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${backendUrl.host}/api/ws/${token}`;
};


// ============= ATESTADOS MÉDICOS =============
export const medicalCertificatesAPI = {
  // Criar atestado médico
  create: async (data) => {
    const response = await axios.post(`${API}/medical-certificates`, data);
    return response.data;
  },
  // Listar atestados de um aluno
  getByStudent: async (studentId) => {
    const response = await axios.get(`${API}/medical-certificates/student/${studentId}`);
    return response.data;
  },
  
  // Verificar se há atestado para uma data
  checkForDate: async (studentId, date) => {
    const response = await axios.get(`${API}/medical-certificates/check/${studentId}/${date}`);
    return response.data;
  },
  
  // Verificar atestados para múltiplos alunos em uma data
  checkBulk: async (date, studentIds) => {
    const idsParam = studentIds.join(',');
    const response = await axios.get(`${API}/medical-certificates/check-bulk/${date}?student_ids=${idsParam}`);
    return response.data;
  },
  
  // Obter detalhes de um atestado
  getById: async (id) => {
    const response = await axios.get(`${API}/medical-certificates/${id}`);
    return response.data;
  },
  
  // Atualizar atestado
  update: async (id, data) => {
    const response = await axios.put(`${API}/medical-certificates/${id}`, data);
    return response.data;
  },
  
  // Excluir atestado (apenas admin)
  delete: async (id) => {
    const response = await axios.delete(`${API}/medical-certificates/${id}`);
    return response.data;
  },
  
  // Listar todos os atestados com filtros
  getAll: async (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const response = await axios.get(`${API}/medical-certificates?${params}`);
    return response.data;
  }
};

// ============= HORÁRIO DE AULAS =============
export const classScheduleAPI = {
  // Listar horários com filtros
  getAll: async (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const response = await axios.get(`${API}/class-schedules?${params}`);
    return response.data;
  },
  
  // Buscar horário de uma turma específica
  getByClass: async (classId, academicYear = null) => {
    const params = academicYear ? `?academic_year=${academicYear}` : '';
    const response = await axios.get(`${API}/class-schedules/by-class/${classId}${params}`);
    return response.data;
  },
  
  // Buscar visualização semanal (inclui sábados letivos)
  getWeekView: async (classId, weekStart, academicYear) => {
    const params = new URLSearchParams({
      class_id: classId,
      week_start: weekStart,
      academic_year: academicYear
    }).toString();
    const response = await axios.get(`${API}/class-schedules/week-view?${params}`);
    return response.data;
  },
  
  // Buscar horário do sábado letivo
  getSaturdaySchedule: async (classId, saturdayDate, academicYear) => {
    const params = new URLSearchParams({
      class_id: classId,
      saturday_date: saturdayDate,
      academic_year: academicYear
    }).toString();
    const response = await axios.get(`${API}/class-schedules/saturday-schedule?${params}`);
    return response.data;
  },
  
  // Criar horário
  create: async (data) => {
    const response = await axios.post(`${API}/class-schedules`, data);
    return response.data;
  },
  
  // Atualizar horário
  update: async (id, data) => {
    const response = await axios.put(`${API}/class-schedules/${id}`, data);
    return response.data;
  },
  
  // Excluir horário
  delete: async (id) => {
    const response = await axios.delete(`${API}/class-schedules/${id}`);
    return response.data;
  },
  
  // Validar conflitos de professor
  validateConflicts: async (classId, day, slotNumber, courseId, academicYear) => {
    const params = new URLSearchParams({
      class_id: classId,
      day,
      slot_number: slotNumber,
      course_id: courseId,
      academic_year: academicYear
    }).toString();
    const response = await axios.get(`${API}/class-schedules/validate-conflicts?${params}`);
    return response.data;
  },
  
  // Buscar todos os conflitos da rede
  getAllConflicts: async (academicYear, schoolId = null) => {
    const params = new URLSearchParams({ academic_year: academicYear });
    if (schoolId) params.append('school_id', schoolId);
    const response = await axios.get(`${API}/class-schedules/all-conflicts?${params}`);
    return response.data;
  }
};


// ============= ANALYTICS =============
export const analyticsAPI = {
  getOverview: async (params = {}) => {
    const response = await axios.get(`${API}/analytics/overview`, { params });
    return response.data;
  }
};


// ============= PMPI-GE (Monitoramento / Painel SEMED) =============
export const pmpiAPI = {
  getOverview: async () => {
    const response = await axios.get(`${API}/pmpi/overview`);
    return response.data;
  },
  getSchoolKpis: async (schoolId, days = 30) => {
    const response = await axios.get(`${API}/pmpi/kpis/${schoolId}`, { params: { days } });
    return response.data;
  },
  getThresholds: async () => {
    const response = await axios.get(`${API}/pmpi/thresholds`);
    return response.data;
  }
};

// ============= Permission Overrides (Matriz de Permissões) =============
export const permissionOverridesAPI = {
  list: async () => {
    const response = await axios.get(`${API}/admin/permissions/overrides`);
    return response.data;
  },
  set: async (item_key, role, visible) => {
    const response = await axios.put(`${API}/admin/permissions/override`, {
      item_key, role, visible,
    });
    return response.data;
  },
  remove: async (item_key, role) => {
    const response = await axios.delete(`${API}/admin/permissions/override`, {
      params: { item_key, role },
    });
    return response.data;
  },
};

// ============= ACTION PLANS =============
export const actionPlansAPI = {
  list: async (filters = {}) => {
    const response = await axios.get(`${API}/action-plans`, { params: filters });
    return response.data;
  },
  get: async (id) => {
    const response = await axios.get(`${API}/action-plans/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await axios.post(`${API}/action-plans`, data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await axios.put(`${API}/action-plans/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    const response = await axios.delete(`${API}/action-plans/${id}`);
    return response.data;
  }
};


// =================== Currículo (BNCC/DCM) — May 2026 ===================
export const curriculumAPI = {
  components: async (params = {}) => {
    const response = await axios.get(`${API}/curriculum/components`, { params });
    return response.data;
  },
  skills: async (params = {}) => {
    const response = await axios.get(`${API}/curriculum/skills`, { params });
    return response.data;
  },
  skillByCodigo: async (codigo) => {
    const response = await axios.get(`${API}/curriculum/skills/${encodeURIComponent(codigo)}`);
    return response.data;
  },
  methods: async (params = {}) => {
    const response = await axios.get(`${API}/curriculum/methods`, { params });
    return response.data;
  },
  stats: async () => {
    const response = await axios.get(`${API}/curriculum/stats`);
    return response.data;
  },
  createComponent: async (data) => (await axios.post(`${API}/curriculum/components`, data)).data,
  updateComponent: async (id, data) => (await axios.put(`${API}/curriculum/components/${id}`, data)).data,
  deleteComponent: async (id) => (await axios.delete(`${API}/curriculum/components/${id}`)).data,
  createSkill: async (data) => (await axios.post(`${API}/curriculum/skills`, data)).data,
  updateSkill: async (id, data) => (await axios.put(`${API}/curriculum/skills/${id}`, data)).data,
  deleteSkill: async (id) => (await axios.delete(`${API}/curriculum/skills/${id}`)).data,

  // =================== v2 Multi-camadas ===================
  bncc: async (params = {}) => (await axios.get(`${API}/curriculum/bncc`, { params })).data,
  adaptations: async (params = {}) => (await axios.get(`${API}/curriculum/adaptations`, { params })).data,
  adaptationById: async (id) => (await axios.get(`${API}/curriculum/adaptations/${id}`)).data,
  adaptationAvailability: async (params = {}) =>
    (await axios.get(`${API}/curriculum/adaptations/availability`, { params })).data,
  createAdaptation: async (data) => (await axios.post(`${API}/curriculum/adaptations`, data)).data,
  updateAdaptation: async (id, data) => (await axios.put(`${API}/curriculum/adaptations/${id}`, data)).data,
  deleteAdaptation: async (id) => (await axios.delete(`${API}/curriculum/adaptations/${id}`)).data,
  runMigration: async () => (await axios.post(`${API}/curriculum/v2/migrate`)).data,
  coverage: async (params = {}) => (await axios.get(`${API}/curriculum/coverage`, { params })).data,
};

// ============= STUDENT DEPENDENCIES (Dependência de Estudos) =============
// Fase 1 [Fev/2026] — ver /app/docs/STUDENT_DEPENDENCY.md
export const studentDependenciesAPI = {
  listByStudent: async (studentId) =>
    (await axios.get(`${API}/student-dependencies/student/${studentId}`)).data,
  summary: async (studentId) =>
    (await axios.get(`${API}/student-dependencies/student/${studentId}/summary`)).data,
  listByClassCourse: async (classId, courseId) =>
    (await axios.get(`${API}/student-dependencies/class/${classId}/course/${courseId}`)).data,
  create: async (data) =>
    (await axios.post(`${API}/student-dependencies`, data)).data,
  update: async (id, data) =>
    (await axios.put(`${API}/student-dependencies/${id}`, data)).data,
  delete: async (id) =>
    (await axios.delete(`${API}/student-dependencies/${id}`)).data,
};
