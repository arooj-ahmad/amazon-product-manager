// src/pages/ShopifyApp.jsx
import { useShopifyApp } from '../hooks/useShopifyApp'
import { styles, theme } from '../styles/theme'
import Header from '../components/Header'
import AddProductForm from '../components/AddProductForm'
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
  // (Uncomment agar billing chahiye)
  // ========================================
  // if (!subscription?.active) {
  //   return (
  //     <div style={styles.page}>
  //       <div style={styles.container}>
  //         <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
  //         <p style={styles.subtitle}>
  //           Choose a plan to start adding Amazon products
  //         </p>
  //
  //         {plans.length === 0 ? (
  //           <div
  //             style={{
  //               ...styles.messageBox,
  //               background: theme.colors.errorBg,
  //               color: theme.colors.errorText,
  //               border: `1px solid ${theme.colors.errorBorder}`,
  //             }}
  //           >
  //             No plans available. Please try again later.
  //           </div>
  //         ) : (
  //           <div style={styles.grid}>
  //             {plans.map((plan) => (
  //               <PlanCard
  //                 key={plan.key}
  //                 plan={plan}
  //                 onSubscribe={handleSubscribe}
  //                 isSubscribing={isSubscribing}
  //               />
  //             ))}
  //           </div>
  //         )}
  //
  //         {message && (
  //           <div
  //             style={{
  //               ...styles.messageBox,
  //               background: theme.colors.errorBg,
  //               color: theme.colors.errorText,
  //               border: `1px solid ${theme.colors.errorBorder}`,
  //             }}
  //           >
  //             {message.text}
  //           </div>
  //         )}
  //       </div>
  //     </div>
  //   )
  // }

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

        <InfoBox />
      </div>
    </div>
  )
}