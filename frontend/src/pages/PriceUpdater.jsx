// src/pages/PriceUpdater.jsx
// Manual Price Update page
// + ✅ FIXED: Navigation via window.location.hash (iframe compatible)

import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles } from '../styles/theme'
import CronRunner from '../components/CronRunner'

// ============================================
// ✅ NAYA: Shopify iframe-compatible navigation
// HashRouter + iframe me navigate() unreliable hai,
// isliye window.location.hash use karo.
// ============================================
function navigateTo(path) {
  const targetHash = `#${path}`
  console.log(`🧭 Navigating to: ${targetHash}`)

  if (window.location.hash === targetHash) {
    // Force re-dispatch
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = targetHash
  }
}

export default function PriceUpdater() {
  // Sirf jo zaroori hai wahi destructure karo
  const {
    cronRunning,
    cronMessage,
    handleRunCron,
  } = useShopifyApp()

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Back button */}
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