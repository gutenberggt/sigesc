import axios from 'axios';
import { getActiveTenantId } from './api';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const teacherDiariesAPI = {
  listMine: async (academicYear = null) => {
    const params = academicYear ? { academic_year: academicYear } : {};
    const tenantId = getActiveTenantId();
    const headers = tenantId ? { 'X-Mantenedora-Id': tenantId } : {};
    const response = await axios.get(`${API}/professor/diarios`, { params, headers });
    return response.data;
  },
};
