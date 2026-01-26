/**
 * Base API client using axios
 * Configured for UCM backend on localhost:8443
 */
import axios from 'axios';

// Base API URL - backend runs on port 8443
const API_BASE_URL = window.location.origin;

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true, // Important for session cookies
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    // Return data directly if it exists
    return response.data;
  },
  (error) => {
    // Handle authentication errors
    if (error.response?.status === 401) {
      // Only redirect to login if not already there AND not on a public endpoint
      const isPublicEndpoint = error.config?.url?.includes('/stats/overview') || 
                               error.config?.url?.includes('/auth/');
      
      if (!window.location.pathname.includes('/login') && !isPublicEndpoint) {
        // Redirect to login
        window.location.href = '/login';
      }
    }
    
    // Return formatted error
    return Promise.reject({
      message: error.response?.data?.message || error.message || 'An error occurred',
      status: error.response?.status,
      data: error.response?.data,
    });
  }
);

export default api;
