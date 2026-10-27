// src/pages/PriceUpdater.jsx
// Manual Price & Inventory Update page

import { useState } from 'react'
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
    cronMessage,              // ✅ Status message (hook se)
  } = useShopifyApp()

  // ✅ 2 Alag loading states
  const [priceLoading, setPriceLoading] = useState(false)
  const [inventoryLoading, setInventoryLoading] = useState(false)

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  // ✅ 1. Price Button Handler
  const onPriceClick = async () => {
    setPriceLoading(true)
    try {
      await handleRunCron()
    } finally {
      setPriceLoading(false)
    }
  }

  // ✅ 2. Inventory Button Handler
  const onInventoryClick = async () => {
    setInventoryLoading(true)
    try {
      await handleRunInventoryUpdate()
    } finally {
      setInventoryLoading(false)
    }
  }

  if (checkingSub) {
    return <Loader text="Loading price updater..." />
  }

  // ✅ Status message format helper
  const renderMessage = () => {
    if (!cronMessage) return null;
    
    // Agar message ke andar "Skipped" ya "Errors" ka zikr ho, to usko highlight karein
    const isSuccess = cronMessage.type === 'success';
    
    return (
      <div
        style={{
          padding: '14px 16px',
          backgroundColor: isSuccess ? '#ecfdf5' : '#fef2f2',
          borderRadius: '8px',
          fontSize: '14px',
          color: isSuccess ? '#065f46' : '#991b1b',
          borderLeft: `4px solid ${isSuccess ? '#10b981' : '#ef4444'}`,
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}
      >
        {/* Agar message string hai to seedha dikhao */}
        <span style={{ fontWeight: '500' }}>{cronMessage.text}</span>
      </div>
    )
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
            onClick={onPriceClick}
            disabled={priceLoading || inventoryLoading} // ✅ Dono loading par disable taake user double click na kare
            style={{
              flex: 1,
              minWidth: '200px',
              padding: '14px 20px',
              backgroundColor: priceLoading ? '#9ca3af' : '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              cursor: priceLoading ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              fontSize: '15px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              opacity: priceLoading ? 0.7 : 1,
              transition: 'all 0.2s ease',
            }}
          >
            {priceLoading ? '⏳ Processing Price...' : '💰 Run Price Update'}
          </button>

          {/* Inventory Update Button */}
          <button
            type="button"
            onClick={onInventoryClick}
            disabled={inventoryLoading || priceLoading} // ✅ Dono loading par disable
            style={{
              flex: 1,
              minWidth: '200px',
              padding: '14px 20px',
              backgroundColor: inventoryLoading ? '#9ca3af' : '#16a34a',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              cursor: inventoryLoading ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              fontSize: '15px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              opacity: inventoryLoading ? 0.7 : 1,
              transition: 'all 0.2s ease',
            }}
          >
            {inventoryLoading ? '⏳ Processing Inventory...' : '📦 Run Inventory Update'}
          </button>
        </div>

        {/* Status Message (Updated) */}
        {renderMessage()}
        
      </div>
    </div>
  )
}