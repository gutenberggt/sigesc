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

// ============= COURSES (DISCIPLINAS) =============
export const coursesAPI = {
  getAll: async (schoolId = null) => {
    const params = schoolId ? { school_id: schoolId } : {};
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
