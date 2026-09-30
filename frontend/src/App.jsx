// ============================================
// frontend/src/App.jsx
// Final routes — user + admin + Footer
// ============================================

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import ProtectedRoute from './components/ProtectedRoute'

// User pages
import Home from './pages/Home'
import ProductDetail from './pages/ProductDetail'

// Admin pages
import Login from './pages/admin/Login'
import Dashboard from './pages/admin/Dashboard'
import ProductEdit from './pages/admin/ProductEdit'

import ShopifyApp from './pages/ShopifyApp'

function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col min-h-screen">
        <Navbar />

        <main className="flex-1">
          <Routes>
            {/* USER ROUTES */}
            <Route path="/" element={<Home />} />

            {/* Product by slug */}
            <Route path="/product/:slug" element={<ProductDetail />} />

            {/* Product by ID (fallback) */}
            <Route path="/product/id/:id" element={<ProductDetail />} />

            {/* ADMIN ROUTES */}
            <Route path="/admin/login" element={<Login />} />
            <Route path="/shopify-app" element={<ShopifyApp />} />

            <Route
              path="/admin/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />

            <Route
              path="/admin/edit/:id"
              element={
                <ProtectedRoute>
                  <ProductEdit />
                </ProtectedRoute>
              }
            />

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
                    <a
                      href="/"
                      className="inline-block bg-[#ff9900] hover:bg-[#e88b00] text-[#0f1111] font-medium px-6 py-3 rounded-lg transition-colors"
                    >
                      ← Back to Home
                    </a>
                  </div>
                </div>
              }
            />
          </Routes>
        </main>

        <Footer />
      </div>
    </BrowserRouter>
  )
}

export default App