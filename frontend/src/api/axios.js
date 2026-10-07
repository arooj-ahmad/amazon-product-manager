// ============================================
// frontend/src/api/axios.js
// Axios instance — backend se baat karne ke liye
// ============================================

import axios from 'axios'

// ----------------------------------------
// Backend URL (Vite env variable se aayega)
// ----------------------------------------
const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ----------------------------------------
// Axios instance banao
// ----------------------------------------
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ============================================
// REQUEST INTERCEPTOR
// Har request mein JWT token automatically add karo
// ============================================
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('admin_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// ============================================
// RESPONSE INTERCEPTOR
// 401 (Unauthorized) aane par auto logout
// ============================================
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token')
      if (window.location.pathname.startsWith('/admin')) {
        window.location.href = '/admin/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api