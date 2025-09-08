// src/services/http.js
import axios from "axios";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://localhost:3000",
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // logs, toast genérico, refresh token se aplicável
    return Promise.reject(error);
  }
);

export default api;
