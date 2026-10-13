// src/pages/ShopifyApp.jsx
import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles, theme } from '../styles/theme'
import Header from '../components/Header'
import AddProductForm from '../components/AddProductForm'
import CollectionsSelector from '../components/CollectionsSelector'
import InfoBox from '../components/InfoBox'
import PlanCard from '../components/PlanCard'

export default function ShopifyApp() {
  const {
    amazonUrl,
    setAmazonUrl,
    markup,
    setMarkup,
    markupType,
    setMarkupType,
    isLoading,
    isSubscribing,
    message,
    shopifyReady,
    shopDomain,
    subscription,
    plans,
    checkingSub,
    handleAddProduct,
    handleSubscribe,
    handleTestActivate,

    // ✅ Collections
    collections,
    selectedCollections,
    collectionsLoading,
    toggleCollection,
    clearCollections,
    refreshCollections,

    // ✅ NAYA: Cron job
    cronRunning,
    cronMessage,
    handleRunCron,
  } = useShopifyApp()

  // ========================================
  // Loading State
  // ========================================
  if (checkingSub) {
    return (
      <div style={styles.centerBox}>
        <p style={{ color: theme.colors.textSecondary, fontSize: '16px' }}>
          ⏳ Loading your store...
        </p>
      </div>
    )
  }

  // ========================================
  // Subscription Required — Show Plans
  // ========================================
  if (!subscription?.active) {
    return (
      <div style={styles.page}>
        <div style={styles.container}>
          <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
          <p style={styles.subtitle}>
            Choose a plan to start adding Amazon products
          </p>

          {plans.length === 0 ? (
            <div
              style={{
                ...styles.messageBox,
                background: theme.colors.errorBg,
                color: theme.colors.errorText,
                border: `1px solid ${theme.colors.errorBorder}`,
              }}
            >
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
            <div
              style={{
                ...styles.messageBox,
                background: message.type === 'success' ? '#eefbf4' : theme.colors.errorBg,
                color: message.type === 'success' ? '#008060' : theme.colors.errorText,
                border: `1px solid ${message.type === 'success' ? '#aee9d1' : theme.colors.errorBorder}`,
              }}
            >
              {message.text}
            </div>
          )}

          <div style={{ marginTop: '24px', textAlign: 'center' }}>
            <button
              type="button"
              onClick={handleTestActivate}
              disabled={isSubscribing}
              style={{
                background: 'transparent',
                border: '1px dashed #c9cccf',
                color: '#6d7175',
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              ⚡ Test Mode: Skip directly to App Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ========================================
  // Main App — Subscription Active
  // ========================================
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <Header
          shopifyReady={shopifyReady}
          shopDomain={shopDomain}
          subscription={subscription}
        />

        <AddProductForm
          amazonUrl={amazonUrl}
          setAmazonUrl={setAmazonUrl}
          markup={markup}
          setMarkup={setMarkup}
          markupType={markupType}
          setMarkupType={setMarkupType}
          isLoading={isLoading}
          message={message}
          onSubmit={handleAddProduct}
        />

        {/* ✅ Collections Selector */}
        <CollectionsSelector
          collections={collections}
          selectedCollections={selectedCollections}
          loading={collectionsLoading}
          onToggle={toggleCollection}
          onClear={clearCollections}
          onRefresh={refreshCollections}
        />

        {/* ✅ NAYA: Manual Price Update */}
        <div
          style={{
            marginTop: '20px',
            marginBottom: '20px',
            padding: '20px',
            border: '1px solid #e1e3e5',
            borderRadius: '8px',
            background: '#fafbfc',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '8px',
            }}
          >
            <span
              style={{
                fontSize: '14px',
                fontWeight: '600',
                color: '#202223',
              }}
            >
              ⚡ Manual Price Update
            </span>
          </div>

          <p
            style={{
              fontSize: '13px',
              color: '#6d7175',
              marginBottom: '16px',
              lineHeight: '1.5',
            }}
          >
            Trigger the price update cron job manually. It will fetch the
            latest Amazon prices and update your Shopify products.
          </p>

          <button
            type="button"
            onClick={handleRunCron}
            disabled={cronRunning}
            style={{
              width: '100%',
              padding: '12px 20px',
              background: cronRunning ? '#b5b5b5' : '#008060',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '600',
              cursor: cronRunning ? 'not-allowed' : 'pointer',
              opacity: cronRunning ? 0.7 : 1,
              transition: 'background 0.15s',
            }}
          >
            {cronRunning
              ? '⏳ Running Price Update...'
              : '🚀 Run Price Update Now'}
          </button>

          {cronMessage && (
            <div
              style={{
                marginTop: '12px',
                padding: '12px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: '500',
                background:
                  cronMessage.type === 'success' ? '#eefbf4' : '#fff4f4',
                color:
                  cronMessage.type === 'success' ? '#008060' : '#d32f2f',
                border: `1px solid ${
                  cronMessage.type === 'success' ? '#aee9d1' : '#ffd6d6'
                }`,
              }}
            >
              {cronMessage.text}
            </div>
          )}
        </div>

        <InfoBox />
      </div>
    </div>
  )
}