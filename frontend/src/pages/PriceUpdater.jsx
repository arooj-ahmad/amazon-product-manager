// src/pages/PriceUpdater.jsx
// Manual Price Update page
import { useNavigate } from 'react-router-dom'
import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles, theme } from '../styles/theme'
import CronRunner from '../components/CronRunner'

export default function PriceUpdater() {
  const navigate = useNavigate()

  // Sirf jo zaroori hai wahi destructure karo
  const {
    cronRunning,
    cronMessage,
    handleRunCron,
  } = useShopifyApp()

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Back button */}
        <button
          type="button"
          onClick={() => navigate('/shopify-app')}
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