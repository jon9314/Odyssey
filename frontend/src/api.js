/**
 * API service for interacting with the Odyssey backend.
 */
import axios from 'axios';

// Determine the base URL for the API.
// If running in development and REACT_APP_API_BASE_URL is set, use that.
// Otherwise, default to the current host (which works well for Docker Compose setups
// where the frontend is served and makes API calls to the backend on the same host,
// potentially via a reverse proxy or direct port mapping).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptors can be added here for global error handling or request modification
apiClient.interceptors.response.use(
  response => response,
  error => {
    // Log detailed error information for debugging
    console.error('API call error:', error.response || error.message || error);
    // You might want to transform the error into a more user-friendly format
    // or handle specific error codes globally here.
    return Promise.reject(error);
  }
);


// Task related API calls
export const getTasks = (status = null, limit = 50) => {
  return apiClient.get('/tasks', { params: { status, limit } });
};

export const addTask = (description) => {
  return apiClient.post('/tasks', { description });
};

export const updateTask = (taskId, status, description = null) => {
    const payload = {};
    if (status) payload.status = status;
    if (description) payload.description = description;
    return apiClient.put(`/tasks/${taskId}`, payload);
};


// Log related API calls
export const getLogs = (level = null, limit = 100) => {
  return apiClient.get('/logs', { params: { level, limit } });
};

// LLM related API calls
export const askLLM = (prompt, model = 'auto', safe = true, system_prompt = null, options = null) => {
  const payload = { prompt, model, safe };
  if (system_prompt) payload.system_prompt = system_prompt;
  if (options) payload.options = options;
  return apiClient.post('/llm/ask', payload);
};


// Celery Async Task related API calls
export const submitAddNumbersTask = (a, b) => {
  return apiClient.post('/tasks/add_numbers', { a, b });
};

export const submitSimulateLongTask = (duration_seconds, message) => {
    return apiClient.post('/tasks/simulate_long', { duration_seconds, message });
};

export const getAsyncTaskStatus = (taskId) => {
  return apiClient.get(`/tasks/status/${taskId}`);
};


export default apiClient;
