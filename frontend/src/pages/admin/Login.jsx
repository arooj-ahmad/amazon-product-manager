// ============================================
// frontend/src/pages/admin/Login.jsx
// Amazon-style admin login
// ============================================

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    const result = await login(username, password)

    if (result.success) {
      navigate('/admin/dashboard')
    } else {
      setError(result.error)
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#232f3e] via-[#37475a] to-[#eaeded] py-8 sm:py-12 px-4">
      <div className="max-w-md mx-auto">
        {/* Amazon Logo */}
        <div className="text-center mb-6">
          <Link to="/" className="inline-flex items-center gap-2">
            <span className="text-4xl">🛒</span>
            <div className="leading-tight text-left">
              <span className="text-2xl font-bold text-white">Amazon</span>
              <span className="text-xs text-[#ff9900] block -mt-1">
                Product Manager
              </span>
            </div>
          </Link>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-lg shadow-lg p-6 sm:p-8">
          <h1 className="text-2xl font-bold text-[#0f1111] mb-2">
            Admin Sign In
          </h1>
          <p className="text-sm text-gray-600 mb-6">
            Admin access only — no user login required
          </p>

          {/* Error */}
          {error && (
            <div className="bg-red-50 border border-red-300 text-red-700 text-sm px-4 py-3 rounded mb-4">
              <p className="font-medium">⚠️ {error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-bold text-[#0f1111] mb-1">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                placeholder="admin"
                className="w-full px-3 py-2 border border-gray-400 rounded focus:border-[#ff9900] focus:ring-2 focus:ring-[#ff9900]/30 focus:outline-none transition-all text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-bold text-[#0f1111] mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full px-3 py-2 border border-gray-400 rounded focus:border-[#ff9900] focus:ring-2 focus:ring-[#ff9900]/30 focus:outline-none transition-all text-sm"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[#ffd814] hover:bg-[#f7ca00] disabled:bg-gray-300 disabled:cursor-not-allowed text-[#0f1111] font-medium py-2.5 rounded-full transition-colors text-sm"
            >
              {isSubmitting ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          {/* Divider */}
          <div className="mt-6 border-t border-gray-200 pt-4">
            <Link
              to="/"
              className="text-sm text-[#007185] hover:text-[#c7511f] hover:underline"
            >
              ← Back to store
            </Link>
          </div>
        </div>

        {/* Footer note */}
        <p className="text-xs text-center text-gray-500 mt-6">
          © 2026 Amazon Product Manager. All rights reserved.
        </p>
      </div>
    </div>
  )
}

export default Login