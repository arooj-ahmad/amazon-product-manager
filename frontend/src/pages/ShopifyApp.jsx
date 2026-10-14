// src/pages/ShopifyApp.jsx
// ✅ SIMPLIFIED: Markup props removed
// ✅ NAYA: Store saved markup info banner
import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles, theme } from '../styles/theme'
import Header from '../components/Header'
import AddProductForm from '../components/AddProductForm'
import CollectionsSelector from '../components/CollectionsSelector'
import InfoBox from '../components/InfoBox'
import PlanCard from '../components/PlanCard'

export default function ShopifyApp() {
  const {
    amazonUrl, setAmazonUrl,
    isLoading, isSubscribing, message,
    shopifyReady, shopDomain,
    subscription, plans, checkingSub,
    handleAddProduct, handleSubscribe, handleTestActivate,

    // ✅ NAYA: Store ka saved markup
    storeMarkup,
    storeMarkupLoading,

    collections, selectedCollections, collectionsLoading,
    toggleCollection, clearCollections, refreshCollections,
  } = useShopifyApp()

  // Loading
  if (checkingSub) {
    return (
      <div style={styles.centerBox}>
        <div style={{ textAlign: 'center' }}>
          <div style={styles.bigSpinner} />
          <p style={{ color: theme.colors.textSecondary, fontSize: '14px', marginTop: '16px' }}>
            Loading your store...
          </p>
        </div>
      </div>
    )
  }

  // Subscription required
  if (!subscription?.active) {
    return (
      <div style={styles.page}>
        <div style={styles.container}>
          <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
          <p style={styles.subtitle}>
            Choose a plan to start adding Amazon products
          </p>
          {plans.length === 0 ? (
            <div style={{ ...styles.messageBox, background: theme.colors.errorBg, color: theme.colors.errorText, border: `1px solid ${theme.colors.errorBorder}` }}>
              No plans available. Please try again later.
            </div>
          ) : (
            <div style={styles.grid}>
              {plans.map((plan) => (
                <PlanCard key={plan.key} plan={plan} onSubscribe={handleSubscribe} isSubscribing={isSubscribing} />
              ))}
            </div>
          )}
          {message && (
            <div style={{ ...styles.messageBox, background: message.type === 'success' ? theme.colors.successBg : theme.colors.errorBg, color: message.type === 'success' ? theme.colors.success : theme.colors.errorText, border: `1px solid ${message.type === 'success' ? theme.colors.successBorder : theme.colors.errorBorder}` }}>
              {message.text}
            </div>
          )}
          <div style={{ marginTop: '24px', textAlign: 'center' }}>
            <button type="button" onClick={handleTestActivate} disabled={isSubscribing} style={styles.testBtn}>
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

        {/* ✅ NAYA: Store saved markup info banner */}
        <StoreMarkupBanner
          storeMarkup={storeMarkup}
          loading={storeMarkupLoading}
        />

        <AddProductForm
          amazonUrl={amazonUrl}
          setAmazonUrl={setAmazonUrl}
          isLoading={isLoading}
          message={message}
          onSubmit={handleAddProduct}
        />

        <CollectionsSelector
          collections={collections}
          selectedCollections={selectedCollections}
          loading={collectionsLoading}
          onToggle={toggleCollection}
          onClear={clearCollections}
          onRefresh={refreshCollections}
        />

        <InfoBox />
      </div>
    </div>
  )
}

// ============================================
// ✅ NAYA: Store Markup Banner
// Dikhaata hai ki kaunsa markup apply hoga
// ============================================
function StoreMarkupBanner({ storeMarkup, loading }) {
  if (loading) {
    return (
      <div style={styles2.banner}>
        <span style={styles2.icon}>💰</span>
        <span style={styles2.text}>Loading your markup settings...</span>
      </div>
    )
  }

  const { markup, markupType, extraPercent } = storeMarkup

  // Markup text banao
  let markupText = ''
  if (markupType === 'percent') {
    markupText = `+${markup}%`
  } else if (markupType === 'both') {
    markupText = `+$${markup} + ${extraPercent}%`
  } else {
    markupText = `+$${markup}`
  }

  return (
    <div style={styles2.banner}>
      <span style={styles2.icon}>💰</span>
      <div style={styles2.content}>
        <span style={styles2.label}>Saved Markup:</span>
        <span style={styles2.value}>{markupText}</span>
        <span style={styles2.hint}>
          Change karne ke liye sidebar me <strong>Markup Settings</strong> kholein
        </span>
      </div>
    </div>
  )
}

// ============================================
// Banner Styles
// ============================================
const styles2 = {
  banner: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 16px',
    marginBottom: '16px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: '8px',
  },
  icon: {
    fontSize: '20px',
    flexShrink: 0,
  },
  content: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
    fontSize: '13px',
  },
  label: {
    color: '#1e40af',
    fontWeight: '500',
  },
  value: {
    color: '#1e3a8a',
    fontWeight: '700',
    fontSize: '14px',
    background: 'white',
    padding: '2px 10px',
    borderRadius: '4px',
    border: '1px solid #bfdbfe',
  },
  hint: {
    color: '#64748b',
    fontSize: '12px',
    marginLeft: '4px',
  },
  text: {
    color: '#64748b',
    fontSize: '13px',
  },
}