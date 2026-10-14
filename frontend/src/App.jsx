// ============================================
// frontend/src/App.jsx
// Final routes — user + admin + Footer
// + HashRouter (Shopify iframe compatible)
// + ✅ FIX: External hash change listener (event + polling)
// ============================================

import {
  HashRouter,
  Routes,
  Route,
  useLocation,
  Navigate,
  Link,
  useNavigate,
} from 'react-router-dom'
import { useEffect, useRef } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'

import ProductDetail from './pages/ProductDetail'
import ShopifyApp from './pages/ShopifyApp'
import MarkupSettings from './pages/MarkupSettings'
import PrivacyPolicy from './pages/PrivacyPolicy'
import TermsOfService from './pages/TermsOfService'

// ============================================
// ✅ FIXED: External hash change listener
// Shopify iframe me `hashchange` event reliably fire nahi hota,
// isliye event + polling dono use kar rahe hain.
// lastHashRef se infinite loop bhi rok diya.
// ============================================
function HashChangeListener() {
  const navigate = useNavigate()
  const location = useLocation()
  const lastHashRef = useRef(window.location.hash)

  useEffect(() => {
    const syncFromHash = () => {
      const currentHash = window.location.hash
      const rawHash = currentHash.replace(/^#/, '') || '/shopify-app'
      const currentPath = location.pathname

      // ✅ Sirf tab navigate karo jab:
      //   1. External hash change hua ho (lastHashRef se different)
      //   2. Aur current route se different ho
      if (
        currentHash !== lastHashRef.current &&
        rawHash !== currentPath
      ) {
        console.log(`🔄 External hash change detected: ${rawHash}`)
        lastHashRef.current = currentHash
        navigate(rawHash)
      }
    }

    // Initial sync
    syncFromHash()

    // Event-based (fast path)
    window.addEventListener('hashchange', syncFromHash)
    window.addEventListener('popstate', syncFromHash)

    // ✅ Polling backup — Shopify iframe ke liye ZAROORI
    const intervalId = setInterval(syncFromHash, 300)

    return () => {
      window.removeEventListener('hashchange', syncFromHash)
      window.removeEventListener('popstate', syncFromHash)
      clearInterval(intervalId)
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
      <HashChangeListener />
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
          <Route
            path="/admin/dashboard"
            element={<Navigate to="/shopify-app" replace />}
          />

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