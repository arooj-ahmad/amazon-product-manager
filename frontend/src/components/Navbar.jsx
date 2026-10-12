// ============================================
// frontend/src/components/Navbar.jsx
// Amazon-style Navbar
// ============================================

import { Link } from 'react-router-dom'

function Navbar() {
  return (
    <nav className="bg-[#131921] text-white sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* LOGO */}
          <Link
            to="/shopify-app"
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
        </div>
      </div>
    </nav>
  )
}

export default Navbar