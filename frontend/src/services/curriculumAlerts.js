import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const curriculumAlertsAPI = {
  list: async (limit = 30) => {
    const response = await axios.get(`${API}/intervencoes/notifications`, { params: { limit } });
    return response.data;
  },
  markAsRead: async (id) => {
    const response = await axios.post(`${API}/intervencoes/notifications/${id}/read`);
    return response.data;
  },
  markAllAsRead: async () => {
    const response = await axios.post(`${API}/intervencoes/notifications/read-all`);
    return response.data;
  },
};

export default curriculumAlertsAPI;
