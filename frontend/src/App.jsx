// ============================================
// frontend/src/App.jsx
// Final routes — user + admin + Footer
// + HashRouter (Shopify iframe compatible)
// + ✅ FIX: External hash + path listener
// + ✅ NAYA: RouteLoader (nprogress) — page change par loading bar
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
import NProgress from 'nprogress'   // ✅ NAYA
import Navbar from './components/Navbar'
import Footer from './components/Footer'

import ProductDetail from './pages/ProductDetail'
import ShopifyApp from './pages/ShopifyApp'
import MarkupSettings from './pages/MarkupSettings'
import PriceUpdater from './pages/PriceUpdater'
import ProductsPricing from './pages/ProductsPricing'
import PrivacyPolicy from './pages/PrivacyPolicy'
import TermsOfService from './pages/TermsOfService'

// ✅ NProgress config
NProgress.configure({
  showSpinner: false,     // Spinner band (sirf bar)
  minimum: 0.1,
  speed: 300,
  trickleSpeed: 200,
})

// ============================================
// ✅ NAYA: RouteLoader — page change par bar dikhao
// ============================================
function RouteLoader() {
  const location = useLocation()

  useEffect(() => {
    NProgress.start()

    // Chhota delay — agar route jaldi load ho to bar complete dikhe
    const timer = setTimeout(() => {
      NProgress.done()
    }, 400)

    return () => {
      clearTimeout(timer)
      NProgress.done()
    }
  }, [location.pathname])

  return null
}

// ============================================
// External navigation listener (unchanged)
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

      const hash = window.location.hash.replace(/^#/, '')
      if (hash && hash !== currentPath) {
        console.log(`🔄 Hash navigation: ${hash}`)
        navigate(hash)
        return
      }

      const fullPath = window.location.pathname

      const shopifyMatch = fullPath.match(/\/apps\/[^/]+\/(.+)$/)
      const appPath = shopifyMatch
        ? `/${shopifyMatch[1]}`
        : fullPath === '/'
          ? '/'
          : fullPath

      if (appPath && appPath !== currentPath) {
        console.log(`🔄 Path navigation: ${appPath}`)
        navigate(appPath)
      }
    }

    syncFromUrl()
    window.addEventListener('hashchange', syncFromUrl)
    window.addEventListener('popstate', syncFromUrl)
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
    '/products',
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
      <RouteLoader />         {/* ✅ NAYA: Page change par loading bar */}
      <HashChangeListener />
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/shopify-app" replace />} />
          <Route path="/markup-settings" element={<MarkupSettings />} />
          <Route path="/products" element={<ProductsPricing />} />
          <Route path="/price-updater" element={<PriceUpdater />} />
          <Route path="/product/:slug" element={<ProductDetail />} />
          <Route path="/product/id/:id" element={<ProductDetail />} />
          <Route path="/shopify-app" element={<ShopifyApp />} />
          <Route
            path="/admin/dashboard"
            element={<Navigate to="/shopify-app" replace />}
          />
          <Route path="/shopify-app/privacy" element={<PrivacyPolicy />} />
          <Route path="/shopify-app/terms" element={<TermsOfService />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/terms" element={<TermsOfService />} />

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