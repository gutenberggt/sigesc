import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const curriculumCoverageV2API = {
  get: async (params = {}) => (
    await axios.get(`${API}/curriculum/coverage-v2`, { params })
  ).data,
};

export default curriculumCoverageV2API;
