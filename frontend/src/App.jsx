// ============================================
// frontend/src/App.jsx
// Final routes — user + admin + Footer
// + HashRouter (Shopify iframe compatible)
// + ✅ FIX: External hash + path listener (sidebar navigation)
// + ✅ NAYA: PriceUpdater page (Manual Price Update)
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
import PriceUpdater from './pages/PriceUpdater'
import PrivacyPolicy from './pages/PrivacyPolicy'
import TermsOfService from './pages/TermsOfService'

// ============================================
// ✅ FIXED: External navigation listener
// Shopify iframe me 2 tarah ke URL changes hote hain:
//   1. HashRouter ke through: URL me # aata hai
//   2. Shopify App Bridge ke through: URL path badalta hai (bina #)
// Dono ko handle karta hai + polling backup.
// ============================================
function HashChangeListener() {
  const navigate = useNavigate()
  const location = useLocation()
  const lastUrlRef = useRef('')

  useEffect(() => {
    const syncFromUrl = () => {
      const currentUrl = window.location.href
      if (currentUrl === lastUrlRef.current) return
      lastUrlRef.current = currentUrl

      const currentPath = location.pathname

      // ─────────────────────────────────
      // A) Pehle HASH check karo (HashRouter ka standard)
      // ─────────────────────────────────
      const hash = window.location.hash.replace(/^#/, '')
      if (hash && hash !== currentPath) {
        console.log(`🔄 Hash navigation: ${hash}`)
        navigate(hash)
        return
      }

      // ─────────────────────────────────
      // B) Agar hash nahi hai, to PATH check karo
      //    Shopify App Bridge ke ui-nav-menu se aata hai
      //    Example: /store/xxx/apps/amzscout-2/markup-settings
      //    → app route: /markup-settings
      // ─────────────────────────────────
      const fullPath = window.location.pathname

      // Shopify embedded URL se app path nikaalo
      const shopifyMatch = fullPath.match(/\/apps\/[^/]+\/(.+)$/)
      const appPath = shopifyMatch
        ? `/${shopifyMatch[1]}`
        : fullPath === '/'
          ? '/'
          : fullPath

      // Sirf tab navigate karo jab app path current route se different ho
      if (appPath && appPath !== currentPath) {
        console.log(`🔄 Path navigation: ${appPath}`)
        navigate(appPath)
      }
    }

    // Initial sync
    syncFromUrl()

    // Event-based (fast)
    window.addEventListener('hashchange', syncFromUrl)
    window.addEventListener('popstate', syncFromUrl)

    // ✅ Polling backup (Shopify iframe ke liye ZAROORI)
    const intervalId = setInterval(syncFromUrl, 300)

    return () => {
      window.removeEventListener('hashchange', syncFromUrl)
      window.removeEventListener('popstate', syncFromUrl)
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

  const FULL_SCREEN_ROUTES = [
    '/markup-settings',
    '/shopify-app',
    '/price-updater',
  ]
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

          {/* MANUAL PRICE UPDATE — full screen */}
          <Route path="/price-updater" element={<PriceUpdater />} />

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