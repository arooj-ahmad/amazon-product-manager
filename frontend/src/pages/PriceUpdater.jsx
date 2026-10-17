// src/pages/PriceUpdater.jsx
// Manual Price Update page

import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles } from '../styles/theme'
import CronRunner from '../components/CronRunner'
import Loader from '../components/Loader'

function navigateTo(path) {
  const targetHash = `#${path}`
  if (window.location.hash === targetHash) return
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

  if (checkingSub) {
    return <Loader text="Loading price updater..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Back Button */}
        <div style={{ marginBottom: '16px' }}>
          <button
            type="button"
            onClick={handleBackToDashboard}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '8px 14px',
              background: 'white',
              color: '#202223',
              border: '1px solid #c9cccf',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            ← Back to Dashboard
          </button>
        </div>

        {/* Page Header */}
        <div style={{ marginBottom: '24px' }}>
          <h1 style={{ ...styles.h1, display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>⚡</span> Manual Price Update
          </h1>
          <p style={styles.subtitle}>
            Fetch latest Amazon prices and sync your Shopify products.
          </p>
        </div>

        {/* CronRunner component */}
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