// ============================================
// frontend/src/hooks/useAuth.js
// Admin authentication state manage karne ke liye hook
// ============================================

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminLogin } from '../api/products'

// LocalStorage key
const TOKEN_KEY = 'admin_token'

/**
 * useAuth hook — admin login/logout state manage karta hai
 *
 * Returns:
 *   - isAuthenticated: boolean (admin logged in hai ya nahi)
 *   - isLoading: boolean (initial check ho raha hai)
 *   - login(username, password): function
 *   - logout(): function
 *   - error: string ya null
 */
export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  // ----------------------------------------
  // Initial check: localStorage mein token hai?
  // ----------------------------------------
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    setIsAuthenticated(!!token)
    setIsLoading(false)
  }, [])

  // ----------------------------------------
  // Login function
  // ----------------------------------------
  const login = async (username, password) => {
    try {
      setError(null)
      const data = await adminLogin(username, password)

      // Token localStorage mein save karo
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setIsAuthenticated(true)

      return { success: true }
    } catch (err) {
      const message =
        err.response?.data?.detail || 'Login fail. Dobara koshish karein.'
      setError(message)
      return { success: false, error: message }
    }
  }

  // ----------------------------------------
  // Logout function
  // ----------------------------------------
  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setIsAuthenticated(false)
    navigate('/admin/login')
  }

  return {
    isAuthenticated,
    isLoading,
    login,
    logout,
    error,
  }
}

/**
 * Simple helper — token check karne ke liye (hooks ke bahar use ke liye)
 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function isLoggedIn() {
  return !!localStorage.getItem(TOKEN_KEY)
}