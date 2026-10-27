// src/pages/PriceUpdater.jsx
// Manual Price & Inventory Update page

import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles } from '../styles/theme'
import Loader from '../components/Loader'

function navigateTo(path) {
  const targetHash = `#${path}`
  if (window.location.hash === targetHash) return
  window.location.hash = targetHash
}

export default function PriceUpdater() {
  const {
    checkingSub,
    handleRunCron,            // ✅ Price update function (hook se)
    handleRunInventoryUpdate, // ✅ Inventory update function (hook se)
    cronRunning,              // ✅ Loading state (hook se)
    cronMessage,              // ✅ Status message (hook se)
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
            <span>⚡</span> Manual Updates
          </h1>
          <p style={styles.subtitle}>
            Update Amazon prices and inventory separately for your Shopify store.
          </p>
        </div>

        {/* ✅ 2 Buttons Side-by-Side */}
        <div
          style={{
            display: 'flex',
            gap: '15px',
            marginBottom: '20px',
            flexWrap: 'wrap',
          }}
        >
          {/* Price Update Button */}
          <button
            type="button"
            onClick={handleRunCron}
            disabled={cronRunning}
            style={{
              flex: 1,
              minWidth: '200px',
              padding: '14px 20px',
              backgroundColor: cronRunning ? '#9ca3af' : '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              cursor: cronRunning ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              fontSize: '15px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              opacity: cronRunning ? 0.7 : 1,
            }}
          >
            {cronRunning ? '⏳ Processing...' : '💰 Run Price Update'}
          </button>

          {/* Inventory Update Button */}
          <button
            type="button"
            onClick={handleRunInventoryUpdate}
            disabled={cronRunning}
            style={{
              flex: 1,
              minWidth: '200px',
              padding: '14px 20px',
              backgroundColor: cronRunning ? '#9ca3af' : '#16a34a',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              cursor: cronRunning ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              fontSize: '15px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              opacity: cronRunning ? 0.7 : 1,
            }}
          >
            {cronRunning ? '⏳ Processing...' : '📦 Run Inventory Update'}
          </button>
        </div>

        {/* Status Message */}
        {cronMessage && (
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: cronMessage.type === 'success' ? '#ecfdf5' : '#fef2f2',
              borderRadius: '8px',
              fontSize: '14px',
              color: cronMessage.type === 'success' ? '#065f46' : '#991b1b',
              borderLeft: `4px solid ${cronMessage.type === 'success' ? '#10b981' : '#ef4444'}`,
            }}
          >
            {cronMessage.text}
          </div>
        )}
      </div>
    </div>
  )
}