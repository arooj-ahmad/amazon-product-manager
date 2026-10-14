// src/pages/PriceUpdater.jsx
// Manual Price Update page
// + ✅ FIXED: Navigation via window.location.hash (iframe compatible)
// + ✅ NAYA: Circle spinner loader

import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles } from '../styles/theme'
import CronRunner from '../components/CronRunner'
import Loader from '../components/Loader'   // ✅ NAYA

// ============================================
// ✅ Shopify iframe-compatible navigation
// ============================================
function navigateTo(path) {
  const targetHash = `#${path}`
  console.log(`🧭 Navigating to: ${targetHash}`)

  if (window.location.hash === targetHash) {
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = targetHash
  }
}

export default function PriceUpdater() {
  const {
    cronRunning,
    cronMessage,
    handleRunCron,
    checkingSub,       // ✅ NAYA: loading state
  } = useShopifyApp()

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  // ✅ NAYA: Loading spinner jab tak subscription check ho
  if (checkingSub) {
    return <Loader text="Loading price updater..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
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
          }}
        >
          ← Back to Dashboard
        </button>

        <h1 style={styles.h1}>💹 Manual Price Update</h1>
        <p style={styles.subtitle}>
          Fetch latest Amazon prices and sync your Shopify products.
        </p>

        <CronRunner
          cronRunning={cronRunning}
          cronMessage={cronMessage}
          onRunCron={handleRunCron}
        />
      </div>
    </div>
  )
}