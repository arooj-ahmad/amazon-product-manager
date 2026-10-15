// src/pages/PriceUpdater.jsx
// Manual Price Update page
// + ✅ FIXED: Navigation via window.location.hash (iframe compatible)
// + ✅ NAYA: Circle spinner loader
// + ✅ NAYA v2: cronProgress pass karo (progress bar + summary)
// + ✅ FIXED: JSX comment syntax error hataya
// + ✅ FIXED v3: Duplicate navigation avoid karo
// + ✅ FIXED v3: Error boundary safety

import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles } from '../styles/theme'
import CronRunner from '../components/CronRunner'
import Loader from '../components/Loader'

// ============================================
// ✅ Shopify iframe-compatible navigation
// ============================================
function navigateTo(path) {
  const targetHash = `#${path}`

  // ✅ Agar already us page pe ho toh kuch mat karo
  if (window.location.hash === targetHash) {
    console.log(`🧭 Already on ${targetHash}`)
    return
  }

  console.log(`🧭 Navigating to: ${targetHash}`)
  window.location.hash = targetHash
}

export default function PriceUpdater() {
  const {
    cronRunning,
    cronMessage,
    cronProgress,
    handleRunCron,
    checkingSub,
  } = useShopifyApp()

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  // Loading spinner jab tak subscription check ho
  if (checkingSub) {
    return <Loader text="Loading price updater..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Back Button */}
        <button
          type="button"
          onClick={handleBackToDashboard}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            marginBottom: '16px',
            background: 'white',
            color: '#202223',
            border: '1px solid #e1e3e5',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#f6f6f7'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'white'
          }}
        >
          ← Back to Dashboard
        </button>

        {/* Page Header */}
        <h1 style={styles.h1}>💹 Manual Price Update</h1>
        <p style={styles.subtitle}>
          Fetch latest Amazon prices and sync your Shopify products.
        </p>

        {/* CronRunner with progress + summary */}
        <CronRunner
          cronRunning={cronRunning}
          cronMessage={cronMessage}
          cronProgress={cronProgress}
          onRunCron={handleRunCron}
        />
      </div>
    </div>
  )
}