// src/pages/ShopifyApp.jsx
// ✅ SIMPLIFIED: Uses theme's container + page (no local wrapper)

import { useShopifyApp } from '../hooks/useShopifyApp'
import { usePriceUpdateStore } from '../store/priceUpdateStore'
import { styles, theme } from '../styles/theme'
import Header from '../components/Header'
import AddProductForm from '../components/AddProductForm'
import CollectionsSelector from '../components/CollectionsSelector'
import PlanCard from '../components/PlanCard'
import Loader from '../components/Loader'

function navigateTo(path) {
  const targetHash = `#${path}`
  if (window.location.hash === targetHash) return
  window.location.hash = targetHash
}

export default function ShopifyApp() {
  const {
    amazonUrl, setAmazonUrl,
    isLoading, isSubscribing, message,
    shopifyReady, shopDomain,
    subscription, plans, checkingSub,
    handleAddProduct, handleSubscribe, handleTestActivate,
    storeMarkup,
    storeMarkupLoading,
    collections, selectedCollections, collectionsLoading,
    toggleCollection, clearCollections, refreshCollections,
  } = useShopifyApp()

  const { cronRunning, cronProgress } = usePriceUpdateStore()

  if (checkingSub) {
    return <Loader text="Loading your store..." />
  }

  // Subscription required
  if (!subscription?.active) {
    return (
      <div style={styles.page}>
        <div style={styles.container}>
          <div style={localStyles.headerSection}>
            <h1 style={localStyles.mainTitle}>🛒 Amazon Product Manager</h1>
            <p style={localStyles.subtitle}>
              Choose a plan to start adding Amazon products to your Shopify store
            </p>
          </div>

          {plans.length === 0 ? (
            <div style={localStyles.alertError}>
              No plans available. Please try again later.
            </div>
          ) : (
            <div style={styles.grid}>
              {plans.map((plan) => (
                <PlanCard
                  key={plan.key}
                  plan={plan}
                  onSubscribe={handleSubscribe}
                  isSubscribing={isSubscribing}
                />
              ))}
            </div>
          )}

          {message && (
            <div style={message.type === 'success' ? localStyles.alertSuccess : localStyles.alertError}>
              {message.text}
            </div>
          )}

          <div style={localStyles.testModeContainer}>
            <button
              type="button"
              onClick={handleTestActivate}
              disabled={isSubscribing}
              style={localStyles.testBtn}
            >
              ⚡ Test Mode: Skip directly to App Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Main App
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <Header
          shopifyReady={shopifyReady}
          shopDomain={shopDomain}
          subscription={subscription}
        />

        {cronRunning && (
          <div style={localStyles.updateBanner}>
            <div style={localStyles.updateIconWrapper}>
              <span style={localStyles.updateIcon}>⏳</span>
            </div>
            <div style={localStyles.updateContent}>
              <span style={localStyles.updateText}>
                Price update is running in the background
              </span>
              <span style={localStyles.updateHint}>
                {cronProgress?.currentProduct || 'Processing products...'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => navigateTo('/price-updater')}
              style={localStyles.updateBtn}
            >
              View Progress →
            </button>
          </div>
        )}

        <StoreMarkupBanner
          storeMarkup={storeMarkup}
          loading={storeMarkupLoading}
        />

        {/* ✅ 2-column layout */}
        <div style={localStyles.twoColumnGrid}>
          <div style={localStyles.column}>
            <AddProductForm
              amazonUrl={amazonUrl}
              setAmazonUrl={setAmazonUrl}
              isLoading={isLoading}
              message={message}
              onSubmit={handleAddProduct}
            />
          </div>

          <div style={localStyles.column}>
            <CollectionsSelector
              collections={collections}
              selectedCollections={selectedCollections}
              loading={collectionsLoading}
              onToggle={toggleCollection}
              onClear={clearCollections}
              onRefresh={refreshCollections}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================
// Store Markup Banner
// ============================================
function StoreMarkupBanner({ storeMarkup, loading }) {
  if (loading) {
    return (
      <div style={localStyles.markupBanner}>
        <span style={localStyles.markupIcon}>💰</span>
        <span style={localStyles.markupText}>Loading your markup settings...</span>
      </div>
    )
  }

  const { markup, markupType, extraPercent, taxRate } = storeMarkup || {}

  let markupText = ''
  if (markupType === 'percent') markupText = `+${markup}%`
  else if (markupType === 'both') markupText = `+$${markup} + ${extraPercent}%`
  else markupText = `+$${markup}`

  const taxText = taxRate > 0 ? `+ ${taxRate}% tax` : ''

  return (
    <div style={localStyles.markupBanner}>
      <span style={localStyles.markupIcon}>💰</span>
      <div style={localStyles.markupContent}>
        <span style={localStyles.markupLabel}>Saved Markup:</span>
        <span style={localStyles.markupValue}>{markupText}</span>
        {taxText && <span style={localStyles.markupTax}>{taxText}</span>}
        <span style={localStyles.markupHint}>
          Change settings in <strong>Markup Settings</strong> from sidebar
        </span>
      </div>
    </div>
  )
}

// ============================================
// Local Styles
// ============================================
const localStyles = {
  headerSection: {
    textAlign: 'center',
    marginBottom: '32px',
  },
  mainTitle: {
    fontSize: '28px',
    fontWeight: '700',
    color: theme.colors.textPrimary || '#0f172a',
    margin: '0 0 8px 0',
    letterSpacing: '-0.5px',
  },
  subtitle: {
    fontSize: '15px',
    color: theme.colors.textSecondary || '#64748b',
    margin: 0,
  },
  alertSuccess: {
    padding: '12px 16px',
    marginTop: '16px',
    background: '#f0fdf4',
    color: '#166534',
    border: '1px solid #bbf7d0',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    textAlign: 'center',
  },
  alertError: {
    padding: '12px 16px',
    marginTop: '16px',
    background: '#fef2f2',
    color: '#991b1b',
    border: '1px solid #fecaca',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    textAlign: 'center',
  },
  testModeContainer: {
    marginTop: '32px',
    textAlign: 'center',
  },
  testBtn: {
    padding: '10px 20px',
    background: 'transparent',
    color: theme.colors.primary || '#3b82f6',
    border: `1px dashed ${theme.colors.primary || '#3b82f6'}`,
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  markupBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '14px 18px',
    marginBottom: '20px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
  },
  markupIcon: {
    fontSize: '22px',
    flexShrink: 0,
  },
  markupContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flexWrap: 'wrap',
    fontSize: '13px',
  },
  markupLabel: {
    color: '#475569',
    fontWeight: '600',
  },
  markupValue: {
    color: '#0f172a',
    fontWeight: '700',
    fontSize: '14px',
    background: 'white',
    padding: '3px 12px',
    borderRadius: '6px',
    border: '1px solid #cbd5e1',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  markupTax: {
    color: '#15803d',
    fontWeight: '700',
    fontSize: '13px',
    background: '#f0fdf4',
    padding: '3px 10px',
    borderRadius: '6px',
    border: '1px solid #86efac',
  },
  markupHint: {
    color: '#94a3b8',
    fontSize: '12px',
    marginLeft: 'auto',
    fontStyle: 'italic',
  },
  markupText: {
    color: '#64748b',
    fontSize: '13px',
    fontWeight: '500',
  },
  updateBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '14px 18px',
    marginBottom: '20px',
    background: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
    border: '1px solid #fcd34d',
    borderRadius: '10px',
    boxShadow: '0 2px 4px rgba(251, 191, 36, 0.1)',
  },
  updateIconWrapper: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '36px',
    height: '36px',
    background: 'white',
    borderRadius: '50%',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    flexShrink: 0,
  },
  updateIcon: {
    fontSize: '18px',
    animation: 'spin 1.5s linear infinite',
  },
  updateContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    flex: 1,
  },
  updateText: {
    color: '#92400e',
    fontWeight: '700',
    fontSize: '14px',
  },
  updateHint: {
    color: '#b45309',
    fontSize: '13px',
    fontWeight: '500',
  },
  updateBtn: {
    padding: '8px 16px',
    background: '#92400e',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.2s ease',
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  },
  twoColumnGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px',
    marginBottom: '24px',
    alignItems: 'stretch',
    width: '100%',
  },
  column: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
}