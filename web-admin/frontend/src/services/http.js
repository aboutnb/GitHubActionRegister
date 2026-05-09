import axios from 'axios';

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  withCredentials: true,
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 403 && error?.response?.data?.detail === 'Password change required') {
      if (window.location.pathname !== '/force-change-password') {
        window.location.href = '/force-change-password';
      }
    }
    return Promise.reject(error);
  },
);

export default http;
