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
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axios.post(`${API}/upload`, formData, {
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
