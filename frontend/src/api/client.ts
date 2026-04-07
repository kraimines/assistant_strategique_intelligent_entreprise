import axios from 'axios';
import { useAuthStore } from '../stores/authStore';

// Base URL de l'API, configurable via les variables d'environnement Vite.
// Fallback sur http://localhost:8000 pour le mode développement local.
export const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL ?? '';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
  withCredentials: false,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

// Auth endpoints
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (data: { email: string; password: string; first_name: string; last_name: string; role: string }) =>
    api.post('/auth/register', {
      email: data.email,
      password: data.password,
      full_name: `${data.first_name} ${data.last_name}`.trim(),
      role: data.role,
    }),
  me: () => api.get('/auth/me'),
};

// Chat endpoint
export const chatApi = {
  send: (message: string, conversationId?: string) =>
    api.post('/chat', { message, conversation_id: conversationId }),
};

// Stats endpoint
export const statsApi = {
  getHRStats: () => api.get('/stats/hr'),
  getCRMStats: () => api.get('/stats/crm'),
  getERPStats: () => api.get('/stats/erp'),
  getOverview: () => api.get('/stats/overview'),
};

// Digital Twin
export const digitalTwinApi = {
  getGraph: () => api.get('/digital-twin/graph'),
  getInsights: () => api.get('/digital-twin/insights'),
  getNodeInsights: (nodeId: string) => api.post(`/digital-twin/insights/${nodeId}`),
};
