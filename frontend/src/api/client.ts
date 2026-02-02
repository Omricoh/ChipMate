import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15_000,
});

// ── Request Interceptor: Attach auth tokens ────────────────────────────────

apiClient.interceptors.request.use((config) => {
  // Admin JWT takes priority
  const adminToken = localStorage.getItem('chipmate_admin_token');
  if (adminToken) {
    config.headers.Authorization = `Bearer ${adminToken}`;
    return config;
  }

  // Player token
  const playerToken = localStorage.getItem('chipmate_player_token');
  if (playerToken) {
    config.headers.Authorization = `Bearer ${playerToken}`;
  }

  return config;
});

// ── Response Interceptor: Handle 401 ───────────────────────────────────────

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      // Clear stored auth on unauthorized response
      localStorage.removeItem('chipmate_admin_token');
      localStorage.removeItem('chipmate_player_token');
      localStorage.removeItem('chipmate_auth');

      // Redirect to home unless already there
      if (window.location.pathname !== '/') {
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
