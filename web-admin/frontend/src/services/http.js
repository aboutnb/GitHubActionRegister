import axios from 'axios';

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  withCredentials: true,
});

export default http;
