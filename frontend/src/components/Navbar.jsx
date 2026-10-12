// ============================================
// frontend/src/components/Navbar.jsx
// Amazon-style Navbar — Admin dashboard & Auth
// ============================================

import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [authenticated, setAuthenticated] = useState(false)

  // Auth state
  useEffect(() => {
    setAuthenticated(!!localStorage.getItem('admin_token'))
  }, [location.pathname])

  // Logout
  const handleLogout = () => {
    localStorage.removeItem('admin_token')
    setAuthenticated(false)
    navigate('/admin/login')
  }

  return (
    <nav className="bg-[#131921] text-white sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* LOGO */}
          <Link
            to="/admin/dashboard"
            className="flex items-center gap-2 hover:outline hover:outline-1 hover:outline-white rounded px-2 py-1 flex-shrink-0"
          >
            <span className="text-2xl">🛒</span>
            <div className="leading-tight">
              <span className="text-lg font-bold">Amazon</span>
              <span className="text-xs text-[#ff9900] block -mt-1">
                Product Manager
              </span>
            </div>
          </Link>

          {/* RIGHT SIDE */}
          <div className="flex items-center gap-3 sm:gap-4">
            {authenticated ? (
              <>
                <Link
                  to="/admin/dashboard"
                  className="text-sm font-medium hover:text-[#ff9900] transition-colors px-2 py-1"
                >
                  Dashboard
                </Link>
                <button
                  onClick={handleLogout}
                  className="text-sm font-medium bg-[#ff9900] hover:bg-[#e88b00] text-[#131921] px-4 py-2 rounded-md transition-colors"
                >
                  Logout
                </button>
              </>
            ) : (
              <Link
                to="/admin/login"
                className="text-sm font-medium bg-[#ff9900] hover:bg-[#e88b00] text-[#131921] px-4 py-2 rounded-md transition-colors"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navbar