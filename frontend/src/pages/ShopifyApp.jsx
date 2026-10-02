// ============================================
// frontend/src/pages/ShopifyApp.jsx
// Shopify Admin embedded app with Billing
// Production-ready version
// ============================================

import { useState, useEffect, useCallback, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ============================================
// App Bridge helper — v3 & v4 dono support
// ============================================
function getAppBridge() {
  if (typeof window === 'undefined') return null
  // App Bridge v4 (recommended)
  if (window.shopify) return window.shopify
  // App Bridge v3 fallback (deprecated)
  if (window.appBridge) return window.appBridge
  return null
}

async function getIdToken() {
  const bridge = getAppBridge()
  if (!bridge) {
    throw new Error(
      'Shopify App Bridge not loaded. Please reload the app from Shopify Admin.'
    )
  }

  // v4: bridge.idToken() returns Promise<string>
  // v3: bridge.idToken() also returns Promise<string>
  try {
    const token = await bridge.idToken()
    if (!token) throw new Error('Empty ID token')
    return token
  } catch (err) {
    throw new Error(`Failed to get ID token: ${err.message}`)
  }
}

function showToast(message, isError = false) {
  const bridge = getAppBridge()
  if (bridge?.toast?.show) {
    bridge.toast.show(message, { isError })
  }
}

// ============================================
// Safe JSON fetch helper
// ============================================
async function safeFetch(url, options = {}) {
  const res = await fetch(url, options)

  let data = null
  const contentType = res.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    data = await res.json()
  } else {
    const text = await res.text()
    data = { detail: text || `HTTP ${res.status}` }
  }

  return { ok: res.ok, status: res.status, data }
}

// ============================================
// Main Component
// ============================================
function ShopifyApp() {
  const [amazonUrl, setAmazonUrl] = useState('')
  const [markup, setMarkup] = useState('2.00')              // ✅ NAYA
  const [markupType, setMarkupType] = useState('fixed')      // ✅ NAYA
  const [isLoading, setIsLoading] = useState(false)
  const [isSubscribing, setIsSubscribing] = useState(false)
  const [message, setMessage] = useState(null)

  const [shopifyReady, setShopifyReady] = useState(false)
  const [shopDomain, setShopDomain] = useState('')

  const [subscription, setSubscription] = useState(null)
  const [plans, setPlans] = useState([])
  const [checkingSub, setCheckingSub] = useState(true)

  const bridgeCheckRef = useRef(null)

  // ========================================
  // 1. App Bridge ready + shop domain
  // ========================================
  useEffect(() => {
    let attempts = 0
    const MAX_ATTEMPTS = 20 // 10 seconds

    bridgeCheckRef.current = setInterval(() => {
      attempts++

      const bridge = getAppBridge()
      if (bridge) {
        setShopifyReady(true)
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null

        // Shop domain from App Bridge
        const shop = bridge.config?.shop || bridge.shop
        if (shop) {
          setShopDomain(shop)
        } else {
          // Fallback: URL param
          const params = new URLSearchParams(window.location.search)
          const urlShop = params.get('shop')
          if (urlShop) setShopDomain(urlShop)
        }

        showToast('Amazon Product Manager loaded!')
        return
      }

      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null
        setCheckingSub(false)
        setMessage({
          type: 'error',
          text: '❌ Shopify App Bridge load nahi hua. Please reload from Shopify Admin.',
        })
      }
    }, 500)

    return () => {
      if (bridgeCheckRef.current) clearInterval(bridgeCheckRef.current)
    }
  }, [])

  // ========================================
  // 2. Load plans + subscription
  // ========================================
  const loadBillingData = useCallback(async () => {
    setCheckingSub(true)
    try {
      // Plans (public endpoint)
      const plansRes = await safeFetch(`${API_URL}/api/billing/plans`)
      if (plansRes.ok) {
        setPlans(plansRes.data.plans || [])
      } else {
        console.warn('Plans fetch failed:', plansRes.data)
      }

      // Subscription status (needs ID token)
      const idToken = await getIdToken()
      const subRes = await safeFetch(`${API_URL}/api/billing/status`, {
        headers: { Authorization: `Bearer ${idToken}` },
      })

      if (subRes.ok) {
        setSubscription(subRes.data)
      } else if (subRes.status === 401) {
        setMessage({
          type: 'error',
          text: '❌ Session expired. Please reload the app.',
        })
      } else {
        // Store not found / no subscription — treat as inactive
        setSubscription({ active: false })
      }
    } catch (err) {
      console.error('Billing load failed:', err)
      setSubscription({ active: false })
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setCheckingSub(false)
    }
  }, [])

  useEffect(() => {
    if (shopifyReady) loadBillingData()
  }, [shopifyReady, loadBillingData])

  // ========================================
  // 3. Subscribe handler
  // ========================================
  const handleSubscribe = async (planKey) => {
    if (isSubscribing) return

    setIsSubscribing(true)
    setMessage(null)

    try {
      const idToken = await getIdToken()

      const res = await safeFetch(
        `${API_URL}/api/billing/subscribe/${planKey}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${idToken}`,
          },
        }
      )

      if (!res.ok) {
        throw new Error(res.data.detail || 'Subscription failed')
      }

      const confirmationUrl = res.data.confirmation_url
      if (!confirmationUrl) {
        throw new Error('No confirmation URL received')
      }

      // Redirect top window (Shopify approval page)
      if (window.top) {
        window.top.location.href = confirmationUrl
      } else {
        window.location.href = confirmationUrl
      }
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
      setIsSubscribing(false)
    }
  }

  // ========================================
  // 4. Add product handler
  // ✅ NAYA: markup + markup_type bhej raha hai
  // ========================================
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim() || isLoading) return

    setIsLoading(true)
    setMessage(null)

    try {
      const idToken = await getIdToken()

      const res = await safeFetch(
        `${API_URL}/api/shopify/app/add-product`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${idToken}`,
          },
          body: JSON.stringify({
            amazon_url: amazonUrl.trim(),
            markup: parseFloat(markup) || 2.0,        // ✅ NAYA
            markup_type: markupType,                    // ✅ NAYA
          }),
        }
      )

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('Session expired. Please reload the app.')
        }
        if (res.status === 402) {
          // Subscription required — refresh state
          setMessage({
            type: 'error',
            text: '❌ Active subscription required. Please subscribe.',
          })
          setSubscription({ active: false })
          setCheckingSub(false)
          return
        }
        if (res.status === 404) {
          throw new Error(
            res.data.detail || 'Store not connected. Please reinstall.'
          )
        }
        if (res.status === 409) {
          throw new Error(res.data.detail || 'Product already exists.')
        }
        throw new Error(res.data.detail || 'Failed to add product')
      }

      setMessage({
        type: 'success',
        text: `✅ ${res.data.message || 'Product added successfully!'}`,
      })
      setAmazonUrl('')
      setMarkup('2.00')  // ✅ NAYA: default pe reset
      showToast('Product added!')
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setIsLoading(false)
    }
  }

  // ========================================
  // Loading state
  // ========================================
  if (checkingSub) {
    return (
      <div style={styles.centerBox}>
        <p style={{ color: '#637381' }}>⏳ Loading your store...</p>
      </div>
    )
  }

  // ========================================
  // Subscription required — show plans
  // ========================================
  // if (!subscription?.active) {
  //   return (
  //     <div style={styles.page}>
  //       <div style={styles.container}>
  //         <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
  //         <p style={styles.subtitle}>
  //           Choose a plan to start adding Amazon products
  //         </p>

  //         {plans.length === 0 ? (
  //           <div style={styles.errorBox}>
  //             No plans available. Please try again later.
  //           </div>
  //         ) : (
  //           <div style={styles.grid}>
  //             {plans.map((plan) => (
  //               <div key={plan.key} style={styles.planCard}>
  //                 <h3 style={styles.planName}>{plan.name}</h3>
  //                 <p style={styles.planPrice}>
  //                   ${plan.price}
  //                   <span style={styles.planPriceUnit}>/month</span>
  //                 </p>
  //                 {plan.trial_days > 0 && (
  //                   <p style={styles.trialText}>
  //                     {plan.trial_days}-day free trial
  //                   </p>
  //                 )}
  //                 <ul style={styles.featureList}>
  //                   {(plan.features || []).map((f) => (
  //                     <li key={f} style={styles.featureItem}>
  //                       ✓ {f}
  //                     </li>
  //                   ))}
  //                 </ul>
  //                 <button
  //                   onClick={() => handleSubscribe(plan.key)}
  //                   disabled={isSubscribing}
  //                   style={{
  //                     ...styles.primaryBtn,
  //                     background: isSubscribing ? '#babfc3' : '#008060',
  //                     cursor: isSubscribing ? 'not-allowed' : 'pointer',
  //                   }}
  //                 >
  //                   {isSubscribing ? '⏳ Redirecting...' : 'Start Free Trial'}
  //                 </button>
  //               </div>
  //             ))}
  //           </div>
  //         )}

  //         {message && (
  //           <div style={styles.errorBox}>{message.text}</div>
  //         )}
  //       </div>
  //     </div>
  //   )
  // }

  // ========================================
  // Main app — subscription active
  // ========================================
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
        <p style={styles.subtitle}>
          Add Amazon products directly to your Shopify store
        </p>

        <div style={styles.badgeRow}>
          {shopifyReady ? (
            <span style={styles.badgeSuccess}>● Connected</span>
          ) : (
            <span style={styles.badgeWarning}>⏳ Connecting...</span>
          )}

          {shopDomain && (
            <span style={styles.badgeInfo}>{shopDomain}</span>
          )}

          {subscription?.subscription?.name && (
            <span style={styles.badgeSuccess}>
              ● {subscription.subscription.name} Active
            </span>
          )}

          {/* ✅ NAYA — Markup Settings link */}
          <a
            href="/markup-settings"
            target="_top"
            style={{
              ...styles.badgeInfo,
              textDecoration: 'none',
              cursor: 'pointer',
            }}
          >
            ⚙️ Markup Settings
          </a>
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>➕ Add New Product</h2>

          <form onSubmit={handleAddProduct}>
            <label style={styles.label}>Amazon Product URL</label>
            <input
              type="url"
              value={amazonUrl}
              onChange={(e) => setAmazonUrl(e.target.value)}
              placeholder="https://www.amazon.com/dp/B0B2RM68G2"
              required
              disabled={isLoading}
              style={{
                ...styles.input,
                background: isLoading ? '#f6f6f7' : 'white',
              }}
            />

            {/* ✅ NAYA — Markup Input */}
            <label style={styles.label}>
              Markup — Default $2 (apni marzi se change karein)
            </label>
            <div
              style={{
                display: 'flex',
                gap: '8px',
                marginBottom: '6px',
              }}
            >
              <select
                value={markupType}
                onChange={(e) => setMarkupType(e.target.value)}
                disabled={isLoading}
                style={{
                  ...styles.input,
                  width: '130px',
                  marginBottom: 0,
                }}
              >
                <option value="fixed">$ Fixed</option>
                <option value="percent">% Percent</option>
              </select>
              <input
                type="number"
                step="0.01"
                min="0"
                value={markup}
                onChange={(e) => setMarkup(e.target.value)}
                placeholder="2.00"
                disabled={isLoading}
                style={{
                  ...styles.input,
                  flex: 1,
                  marginBottom: 0,
                }}
              />
            </div>
            <p style={styles.helpText}>
              💡 Final price = Amazon price{' '}
              {markupType === 'percent' ? '× (1 + %/100)' : '+ $'}
            </p>

            <button
              type="submit"
              disabled={isLoading}
              style={{
                ...styles.primaryBtn,
                background: isLoading ? '#babfc3' : '#008060',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                marginTop: '12px',
              }}
            >
              {isLoading
                ? '⏳ Fetching from Amazon...'
                : '🛍️ Fetch & Add to Shopify'}
            </button>
          </form>

          {isLoading && (
            <p style={styles.helpText}>
              This may take 20–40 seconds while we fetch data from Amazon...
            </p>
          )}

          {message && (
            <div
              style={{
                ...styles.messageBox,
                background:
                  message.type === 'success' ? '#e4f5e4' : '#fbeae5',
                color:
                  message.type === 'success' ? '#008060' : '#d72c0d',
                border: `1px solid ${
                  message.type === 'success' ? '#aee9ae' : '#febcb3'
                }`,
              }}
            >
              {message.text}
            </div>
          )}
        </div>

        <div style={styles.infoBox}>
          <strong style={{ color: '#202223' }}>💡 How it works:</strong>
          <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
            <li>Paste any Amazon product URL</li>
            <li>Set your markup ($ fixed or % percent)</li>
            <li>Click "Fetch &amp; Add"</li>
            <li>We fetch title, images, price, and specs from Amazon</li>
            <li>Product is added to both Supabase and your Shopify store</li>
            <li>Product appears in your Shopify Products list</li>
          </ol>
        </div>

        <div style={styles.securityBox}>
          🔒 <strong>Secure:</strong> This app uses Shopify ID tokens for
          authentication. Only users with access to this store can add products.
        </div>
      </div>
    </div>
  )
}

// ============================================
// Inline styles (extracted for readability)
// ============================================
const styles = {
  page: {
    padding: '20px',
    fontFamily: 'Inter, -apple-system, sans-serif',
    background: '#f6f6f7',
    minHeight: '100vh',
  },
  container: { maxWidth: '900px', margin: '0 auto' },
  centerBox: { padding: '60px 20px', textAlign: 'center' },
  h1: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#202223',
    marginBottom: '4px',
  },
  h2: {
    fontSize: '16px',
    fontWeight: '600',
    marginBottom: '16px',
    color: '#202223',
  },
  subtitle: { color: '#637381', fontSize: '14px', marginBottom: '16px' },

  badgeRow: {
    display: 'flex',
    gap: '8px',
    flexWrap: 'wrap',
    marginBottom: '20px',
  },
  badgeSuccess: {
    display: 'inline-block',
    padding: '4px 12px',
    background: '#d4f5d4',
    color: '#008060',
    fontSize: '12px',
    borderRadius: '12px',
    fontWeight: '500',
  },
  badgeWarning: {
    display: 'inline-block',
    padding: '4px 12px',
    background: '#fef3cd',
    color: '#8a6d3b',
    fontSize: '12px',
    borderRadius: '12px',
    fontWeight: '500',
  },
  badgeInfo: {
    display: 'inline-block',
    padding: '4px 12px',
    background: '#e1f0ff',
    color: '#005bd3',
    fontSize: '12px',
    borderRadius: '12px',
    fontWeight: '500',
    fontFamily: 'monospace',
  },

  card: {
    background: 'white',
    border: '1px solid #e1e3e5',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '20px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  label: {
    display: 'block',
    fontSize: '14px',
    fontWeight: '500',
    marginBottom: '6px',
    color: '#202223',
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #babfc3',
    borderRadius: '6px',
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box',
    marginBottom: '12px',
    color: '#202223',
  },
  primaryBtn: {
    color: 'white',
    border: 'none',
    padding: '10px 20px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    transition: 'background 0.2s',
  },
  helpText: {
    marginTop: '12px',
    fontSize: '13px',
    color: '#637381',
  },
  messageBox: {
    marginTop: '16px',
    padding: '12px 16px',
    borderRadius: '6px',
    fontSize: '14px',
  },
  errorBox: {
    marginTop: '20px',
    padding: '12px 16px',
    background: '#fbeae5',
    color: '#d72c0d',
    borderRadius: '6px',
    fontSize: '14px',
  },

  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
    gap: '20px',
  },
  planCard: {
    background: 'white',
    border: '2px solid #e1e3e5',
    borderRadius: '12px',
    padding: '24px',
  },
  planName: { fontSize: '20px', fontWeight: '600', marginBottom: '8px' },
  planPrice: { fontSize: '32px', fontWeight: 'bold', marginBottom: '8px' },
  planPriceUnit: {
    fontSize: '14px',
    fontWeight: 'normal',
    color: '#637381',
  },
  trialText: {
    fontSize: '13px',
    color: '#008060',
    marginBottom: '16px',
    fontWeight: '500',
  },
  featureList: { listStyle: 'none', padding: 0, marginBottom: '20px' },
  featureItem: { padding: '6px 0', fontSize: '14px', color: '#202223' },

  infoBox: {
    background: '#f6f6f7',
    borderRadius: '6px',
    padding: '16px',
    fontSize: '13px',
    color: '#637381',
    lineHeight: '1.6',
    marginBottom: '16px',
  },
  securityBox: {
    padding: '12px 16px',
    background: '#f0f7ff',
    border: '1px solid #c3ddf8',
    borderRadius: '6px',
    fontSize: '12px',
    color: '#005bd3',
  },
}

export default ShopifyApp