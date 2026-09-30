// ============================================
// frontend/src/components/ProtectedRoute.jsx
// Admin routes ko protect karta hai
// Agar admin logged in nahi → /admin/login par redirect
// ============================================

import { Navigate } from 'react-router-dom'
import { isLoggedIn } from '../hooks/useAuth'

function ProtectedRoute({ children }) {
  const authenticated = isLoggedIn()

  // Agar login nahi → login page par redirect
  if (!authenticated) {
    return <Navigate to="/admin/login" replace />
  }

  // Agar login hai → children render karo
  return children
}

export default ProtectedRoute