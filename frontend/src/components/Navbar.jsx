// ============================================
// frontend/src/components/Navbar.jsx
// Amazon-style Navbar — working search bar + cart
// ============================================

import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [authenticated, setAuthenticated] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const isAdmin = location.pathname.startsWith('/admin')

  // Auth state
  useEffect(() => {
    setAuthenticated(!!localStorage.getItem('admin_token'))
  }, [location.pathname])

  // URL se search query sync karo
  useEffect(() => {
    setSearchQuery(searchParams.get('q') || '')
  }, [searchParams])

  // Logout
  const handleLogout = () => {
    localStorage.removeItem('admin_token')
    setAuthenticated(false)
    navigate('/admin/login')
  }

  // Search submit
  const handleSearch = (e) => {
    e.preventDefault()
    const query = searchQuery.trim()
    if (query) {
      navigate(`/?q=${encodeURIComponent(query)}`)
    } else {
      navigate('/')
    }
  }

  return (
    <nav className="bg-[#131921] text-white sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 sm:gap-4 h-16">
          {/* LOGO */}
          <Link
            to={isAdmin ? '/admin/dashboard' : '/'}
            className="flex items-center gap-2 hover:outline hover:outline-1 hover:outline-white rounded px-2 py-1 flex-shrink-0"
          >
            <span className="text-2xl">🛒</span>
            <div className="hidden sm:block leading-tight">
              <span className="text-lg font-bold">Amazon</span>
              <span className="text-xs text-[#ff9900] block -mt-1">
                Product Manager
              </span>
            </div>
          </Link>

          {/* SEARCH BAR (User side only) */}
          {!isAdmin && (
            <form
              onSubmit={handleSearch}
              className="flex-1 hidden md:flex max-w-2xl"
            >
              <div className="flex w-full">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search products, brands..."
                  className="flex-1 px-4 py-2 rounded-l-md text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#ff9900]"
                />
                <button
                  type="submit"
                  className="bg-[#febd69] hover:bg-[#f3a847] text-[#131921] px-5 rounded-r-md transition-colors"
                  aria-label="Search"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                </button>
              </div>
            </form>
          )}

          {/* RIGHT SIDE */}
          <div className="flex items-center gap-2 sm:gap-4 ml-auto">
            {isAdmin ? (
              authenticated ? (
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
                  to="/"
                  className="text-sm font-medium hover:text-[#ff9900] transition-colors px-2 py-1"
                >
                  ← Back to Store
                </Link>
              )
            ) : (
              <>
                {/* Account */}
                <Link
                  to="/admin/login"
                  className="hidden sm:block px-2 py-1 rounded hover:outline hover:outline-1 hover:outline-white"
                >
                  <p className="text-xs leading-tight text-gray-300">
                    Hello, sign in
                  </p>
                  <p className="text-sm font-bold leading-tight">Account</p>
                </Link>

                {/* Cart Icon */}
                <Link
                  to="/"
                  className="flex items-end gap-1 px-2 py-1 rounded hover:outline hover:outline-1 hover:outline-white relative"
                >
                  <div className="relative">
                    <svg
                      className="w-8 h-8"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.31.12-.48 0-.55-.45-1-1-1H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z" />
                    </svg>
                    <span className="absolute -top-1 right-0 bg-[#f08804] text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                      0
                    </span>
                  </div>
                  <span className="text-sm font-bold hidden sm:block">
                    Cart
                  </span>
                </Link>
              </>
            )}
          </div>
        </div>

        {/* MOBILE SEARCH BAR */}
        {!isAdmin && (
          <div className="md:hidden pb-3">
            <form onSubmit={handleSearch} className="flex w-full">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search..."
                className="flex-1 px-3 py-2 rounded-l-md text-gray-900 placeholder-gray-500 text-sm focus:outline-none"
              />
              <button
                type="submit"
                className="bg-[#febd69] text-[#131921] px-4 rounded-r-md"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </button>
            </form>
          </div>
        )}
      </div>
    </nav>
  )
}

export default Navbar