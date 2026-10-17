// src/pages/ShopifyApp.jsx
// ✅ REDESIGNED: Professional Logo, Header & Clean Layout

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
          <div style={localStyles.heroSection}>
            <div style={localStyles.heroLogoBox}>
              <span style={localStyles.heroLogoIcon}>🛒</span>
            </div>
            <h1 style={localStyles.heroTitle}>Amazon Product Manager</h1>
            <p style={localStyles.heroSubtitle}>
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

  // Main App Dashboard
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        
        {/* ✅ NEW: Professional Hero Header (Logo + Title) */}
        <div style={localStyles.appHeader}>
          <div style={localStyles.brandSection}>
            <div style={localStyles.logoWrapper}>
              {/* Modern SVG Logo */}
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M6 2L3 6V20C3 21.1 3.9 22 5 22H19C20.1 22 21 21.1 21 20V6L18 2H6Z" fill="white" fillOpacity="0.2" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M3 6H21" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M16 10C16 12.2091 14.2091 14 12 14C9.79086 14 8 12.2091 8 10" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <h1 style={localStyles.brandTitle}>Amazon Product Manager</h1>
              <p style={localStyles.brandSubtitle}>Add Amazon products directly to your Shopify store</p>
            </div>
          </div>
          <Header
            shopifyReady={shopifyReady}
            shopDomain={shopDomain}
            subscription={subscription}
          />
        </div>

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

        {/* 2-column layout */}
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

  const { markup, markupType, extraPercent, taxRate, countryName } = storeMarkup || {}

  let markupText = ''
  if (markupType === 'percent') markupText = `+${markup}%`
  else if (markupType === 'both') markupText = `+$${markup} + ${extraPercent}%`
  else markupText = `+$${markup}`

  const taxText = taxRate > 0 ? `+ ${taxRate}% tax` : ''

  return (
    <div style={localStyles.markupBanner}>
      <div style={localStyles.markupIconBox}>
        <span style={{ fontSize: '20px' }}>💰</span>
      </div>
      <div style={localStyles.markupContent}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={localStyles.markupLabel}>Saved Markup:</span>
          <span style={localStyles.markupValue}>{markupText}</span>
          {taxText && <span style={localStyles.markupTax}>{taxText}</span>}
          {countryName && <span style={localStyles.markupCountry}>({countryName})</span>}
        </div>
        <span style={localStyles.markupHint}>
          Change settings in <strong>Markup Settings</strong> from the sidebar
        </span>
      </div>
    </div>
  )
}

// ============================================
// Local Styles
// ============================================
const localStyles = {
  // ✅ NEW: Hero Header & Logo Styles
  appHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    gap: '20px',
    marginBottom: '28px',
    paddingBottom: '24px',
    borderBottom: '1px solid #e2e8f0',
  },
  brandSection: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  logoWrapper: {
    width: '56px',
    height: '56px',
    borderRadius: '14px',
    background: 'linear-gradient(135deg, #008060 0%, #004c3f 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(0, 128, 96, 0.25)',
    flexShrink: 0,
  },
  brandTitle: {
    fontSize: '22px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 4px 0',
    letterSpacing: '-0.5px',
  },
  brandSubtitle: {
    fontSize: '14px',
    color: '#64748b',
    margin: 0,
    fontWeight: '500',
  },

  // Pricing / Hero Section (for Subscribe page)
  heroSection: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
    marginBottom: '40px',
  },
  heroLogoBox: {
    width: '64px',
    height: '64px',
    borderRadius: '16px',
    background: 'linear-gradient(135deg, #008060 0%, #004c3f 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
    boxShadow: '0 4px 12px rgba(0, 128, 96, 0.25)',
  },
  heroLogoIcon: {
    fontSize: '28px',
  },
  heroTitle: {
    fontSize: '28px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 8px 0',
    letterSpacing: '-0.5px',
  },
  heroSubtitle: {
    fontSize: '15px',
    color: '#64748b',
    margin: 0,
    maxWidth: '400px',
    lineHeight: '1.5',
  },

  // Alerts & Messages
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

  // Test Mode Button
  testModeContainer: {
    marginTop: '32px',
    textAlign: 'center',
  },
  testBtn: {
    padding: '10px 20px',
    background: 'transparent',
    color: '#3b82f6',
    border: '1px dashed #3b82f6',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },

  // ✅ NEW: Markup Banner (Cleaner)
  markupBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '16px 20px',
    marginBottom: '24px',
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  },
  markupIconBox: {
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    background: '#fef3c7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  markupIcon: {
    fontSize: '22px',
    flexShrink: 0,
  },
  markupContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    flex: 1,
  },
  markupLabel: {
    color: '#475569',
    fontWeight: '600',
    fontSize: '14px',
  },
  markupValue: {
    color: '#0f172a',
    fontWeight: '700',
    fontSize: '14px',
    background: '#f8fafc',
    padding: '4px 12px',
    borderRadius: '6px',
    border: '1px solid #cbd5e1',
  },
  markupTax: {
    color: '#15803d',
    fontWeight: '700',
    fontSize: '13px',
    background: '#f0fdf4',
    padding: '4px 10px',
    borderRadius: '6px',
    border: '1px solid #86efac',
  },
  markupCountry: {
    color: '#64748b',
    fontWeight: '500',
    fontSize: '13px',
    fontStyle: 'italic',
  },
  markupHint: {
    color: '#94a3b8',
    fontSize: '13px',
    marginTop: '2px',
  },
  markupText: {
    color: '#64748b',
    fontSize: '13px',
    fontWeight: '500',
  },

  // Update Banner
  updateBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '16px 20px',
    marginBottom: '24px',
    background: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
    border: '1px solid #fcd34d',
    borderRadius: '12px',
    boxShadow: '0 2px 4px rgba(251, 191, 36, 0.1)',
  },
  updateIconWrapper: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '40px',
    height: '40px',
    background: 'white',
    borderRadius: '50%',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    flexShrink: 0,
  },
  updateIcon: {
    fontSize: '20px',
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
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  },

  // Grid
  twoColumnGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '24px',
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