// src/pages/ShopifyApp.jsx
import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles, theme } from '../styles/theme'
import Header from '../components/Header'
import AddProductForm from '../components/AddProductForm'
import CollectionsSelector from '../components/CollectionsSelector'
import CronRunner from '../components/CronRunner'
import InfoBox from '../components/InfoBox'
import PlanCard from '../components/PlanCard'
// ❌ MarkupSettings import HATAO — ab sidebar se khulega

export default function ShopifyApp() {
  const {
    amazonUrl, setAmazonUrl,
    markup, setMarkup,
    markupType, setMarkupType,
    extraPercent, setExtraPercent,
    isLoading, isSubscribing, message,
    shopifyReady, shopDomain,
    subscription, plans, checkingSub,
    handleAddProduct, handleSubscribe, handleTestActivate,

    collections, selectedCollections, collectionsLoading,
    toggleCollection, clearCollections, refreshCollections,

    cronRunning, cronMessage, handleRunCron,
  } = useShopifyApp()

  // ❌ showMarkupSettings state HATAO
  // ❌ if (showMarkupSettings) block HATAO

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

        <AddProductForm
          amazonUrl={amazonUrl}
          setAmazonUrl={setAmazonUrl}
          markup={markup}
          setMarkup={setMarkup}
          markupType={markupType}
          setMarkupType={setMarkupType}
          extraPercent={extraPercent}
          setExtraPercent={setExtraPercent}
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

        <CronRunner
          cronRunning={cronRunning}
          cronMessage={cronMessage}
          onRunCron={handleRunCron}
        />

        <InfoBox />
      </div>
    </div>
  )
}