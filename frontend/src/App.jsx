// ============================================
// frontend/src/App.jsx
// Final routes — user + admin + Footer
// + HashRouter (Shopify iframe compatible)
// + ✅ FIX: External hash change listener (sidebar navigation)
// ============================================

import { HashRouter, Routes, Route, useLocation, Navigate, Link, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'

import ProductDetail from './pages/ProductDetail'
import ShopifyApp from './pages/ShopifyApp'
import MarkupSettings from './pages/MarkupSettings'
import PrivacyPolicy from './pages/PrivacyPolicy'
import TermsOfService from './pages/TermsOfService'

// ============================================
// ✅ NAYA: External hash change sun-ne wala component
// Shopify sidebar se click hone par hash badalta hai,
// lekin HashRouter khud detect nahi karta — isliye manual sync.
// ============================================
function HashChangeListener() {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const syncFromHash = () => {
      const rawHash = window.location.hash.replace(/^#/, '') || '/shopify-app'
      const currentPath = location.pathname

      if (rawHash !== currentPath) {
        console.log(`🔄 External hash change detected: ${rawHash}`)
        navigate(rawHash)
      }
    }

    // Initial sync (page load pe)
    syncFromHash()

    // Listen for changes
    window.addEventListener('hashchange', syncFromHash)
    window.addEventListener('popstate', syncFromHash)

    return () => {
      window.removeEventListener('hashchange', syncFromHash)
      window.removeEventListener('popstate', syncFromHash)
    }
  }, [navigate, location.pathname])

  return null
}

// ============================================
// Layout wrapper — full screen vs normal
// ============================================
function Layout({ children }) {
  const location = useLocation()

  const FULL_SCREEN_ROUTES = ['/markup-settings', '/shopify-app']
  const isFullScreen = FULL_SCREEN_ROUTES.some((path) =>
    location.pathname.startsWith(path)
  )

  if (isFullScreen) {
    return <>{children}</>
  }

  return (
    <div className="flex flex-col min-h-screen">
      <Navbar />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  )
}

function App() {
  return (
    <HashRouter>
      <HashChangeListener />   {/* ✅ Ye add karo */}
      <Layout>
        <Routes>
          {/* USER ROUTES */}
          <Route path="/" element={<Navigate to="/shopify-app" replace />} />

          {/* MARKUP SETTINGS — full screen */}
          <Route path="/markup-settings" element={<MarkupSettings />} />

          {/* Product by slug */}
          <Route path="/product/:slug" element={<ProductDetail />} />

          {/* Product by ID (fallback) */}
          <Route path="/product/id/:id" element={<ProductDetail />} />

          {/* APP ROUTES */}
          <Route path="/shopify-app" element={<ShopifyApp />} />
          <Route path="/admin/dashboard" element={<Navigate to="/shopify-app" replace />} />

          <Route path="/shopify-app/privacy" element={<PrivacyPolicy />} />
          <Route path="/shopify-app/terms" element={<TermsOfService />} />

          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/terms" element={<TermsOfService />} />

          {/* 404 */}
          <Route
            path="*"
            element={
              <div className="min-h-[60vh] flex items-center justify-center px-4">
                <div className="text-center">
                  <p className="text-6xl mb-4">404</p>
                  <h1 className="text-3xl font-bold text-gray-800 mb-2">
                    Page not found
                  </h1>
                  <p className="text-gray-600 mb-6">
                    Jo page aap dhundh rahe hain woh exist nahi karta.
                  </p>
                  <Link
                    to="/shopify-app"
                    className="inline-block bg-[#ff9900] hover:bg-[#e88b00] text-[#0f1111] font-medium px-6 py-3 rounded-lg transition-colors"
                  >
                    ← Back to App
                  </Link>
                </div>
              </div>
            }
          />
        </Routes>
      </Layout>
    </HashRouter>
  )
}

export default App