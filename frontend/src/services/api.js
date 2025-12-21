import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Configura interceptor para incluir token
const getToken = () => localStorage.getItem('accessToken');

axios.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

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
  }
};

// ============= USERS =============
export const usersAPI = {
  getAll: async () => {
    const response = await axios.get(`${API}/users`);
    return response.data;
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
    const params = schoolId ? { school_id: schoolId } : {};
    const response = await axios.get(`${API}/classes`, { params });
    return response.data;
  },
  
  getAll: async (schoolId = null) => {
    const params = schoolId ? { school_id: schoolId } : {};
    const response = await axios.get(`${API}/classes`, { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await axios.get(`${API}/classes/${id}`);
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

// ============= STUDENTS (ALUNOS) =============
export const studentsAPI = {
  getAll: async (schoolId = null, classId = null) => {
    const params = {};
    if (schoolId) params.school_id = schoolId;
    if (classId) params.class_id = classId;
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
  
  update: async (id, data) => {
    const response = await axios.put(`${API}/students/${id}`, data);
    return response.data;
  },
  
  delete: async (id) => {
    await axios.delete(`${API}/students/${id}`);
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
  
  getClassReport: async (classId, academicYear) => {
    const response = await axios.get(`${API}/attendance/report/class/${classId}?academic_year=${academicYear}`);
    return response.data;
  },
  
  getAlerts: async (schoolId = null, academicYear = null) => {
    let url = `${API}/attendance/alerts?`;
    if (schoolId) url += `school_id=${schoolId}&`;
    if (academicYear) url += `academic_year=${academicYear}`;
    const response = await axios.get(url);
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
  getBoletimUrl: (studentId, academicYear = '2025') => {
    return `${BACKEND_URL}/api/documents/boletim/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Declaração de Matrícula (retorna URL do PDF)
  getDeclaracaoMatriculaUrl: (studentId, academicYear = '2025', purpose = 'fins comprobatórios') => {
    return `${BACKEND_URL}/api/documents/declaracao-matricula/${studentId}?academic_year=${academicYear}&purpose=${encodeURIComponent(purpose)}`;
  },
  
  // Gerar Declaração de Frequência (retorna URL do PDF)
  getDeclaracaoFrequenciaUrl: (studentId, academicYear = '2025') => {
    return `${BACKEND_URL}/api/documents/declaracao-frequencia/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Ficha Individual (retorna URL do PDF)
  getFichaIndividualUrl: (studentId, academicYear = '2025') => {
    return `${BACKEND_URL}/api/documents/ficha-individual/${studentId}?academic_year=${academicYear}`;
  },
  
  // Gerar Certificado (retorna URL do PDF)
  getCertificadoUrl: (studentId, academicYear = '2025') => {
    return `${BACKEND_URL}/api/documents/certificado/${studentId}?academic_year=${academicYear}`;
  },
  
  // Baixar documento com autenticação
  downloadDocument: async (url) => {
    const response = await axios.get(url, {
      responseType: 'blob'
    });
    return response.data;
  },
  
  // Baixar Boletim (retorna blob)
  getBoletim: async (studentId, academicYear = '2025') => {
    const url = `${BACKEND_URL}/api/documents/boletim/${studentId}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  },
  
  // Baixar Ficha Individual (retorna blob)
  getFichaIndividual: async (studentId, academicYear = '2025') => {
    const url = `${BACKEND_URL}/api/documents/ficha-individual/${studentId}?academic_year=${academicYear}`;
    const response = await axios.get(url, { responseType: 'blob' });
    return response.data;
  },
  
  // Baixar Certificado (retorna blob)
  getCertificado: async (studentId, academicYear = '2025') => {
    const url = `${BACKEND_URL}/api/documents/certificado/${studentId}?academic_year=${academicYear}`;
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

