// src/hooks/useShopifyApp.js
import { useState, useEffect, useCallback, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ============================================
// App Bridge helper — v3 & v4 dono support
// ============================================
function getAppBridge() {
  if (typeof window === 'undefined') return null
  if (window.shopify) return window.shopify
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
// Main Hook
// ============================================
export function useShopifyApp() {
  const [amazonUrl, setAmazonUrl] = useState('')
  const [markup, setMarkup] = useState('2.00')
  const [markupType, setMarkupType] = useState('fixed')
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
  // 1. Load billing data (plans + subscription)
  // ========================================
  const loadBillingData = useCallback(async () => {
    setCheckingSub(true)
    try {
      const plansRes = await safeFetch(`${API_URL}/api/billing/plans`)
      if (plansRes.ok) {
        setPlans(plansRes.data.plans || [])
      } else {
        console.warn('Plans fetch failed:', plansRes.data)
      }

      try {
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
          setSubscription({ active: false })
        }
      } catch (tokenErr) {
        console.warn('Token unavailable (testing mode):', tokenErr.message)
        setSubscription({ active: false })
      }
    } catch (err) {
      console.error('Billing load failed:', err)
      setSubscription({ active: false })
    } finally {
      setCheckingSub(false)
    }
  }, [])

  // ========================================
  // 2. App Bridge ready + shop domain
  // ========================================
  useEffect(() => {
    let attempts = 0
    const MAX_ATTEMPTS = 20

    bridgeCheckRef.current = setInterval(() => {
      attempts++
      const bridge = getAppBridge()

      if (bridge) {
        setShopifyReady(true)
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null

        const shop = bridge.config?.shop || bridge.shop
        if (shop) {
          setShopDomain(shop)
        } else {
          const params = new URLSearchParams(window.location.search)
          const urlShop = params.get('shop')
          if (urlShop) setShopDomain(urlShop)
        }

        showToast('Amazon Product Manager loaded!')
        loadBillingData()
        return
      }

      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null
        setMessage({
          type: 'error',
          text: '⚠️ Shopify Admin se app kholein. Filhal testing mode active hai.',
        })
        loadBillingData()
      }
    }, 500)

    return () => {
      if (bridgeCheckRef.current) clearInterval(bridgeCheckRef.current)
    }
  }, [loadBillingData])

  // ========================================
  // 3. Subscribe handler
  // ========================================
  const handleSubscribe = async (planKey) => {
    if (isSubscribing) return
    setIsSubscribing(true)
    setMessage(null)

    try {
      const bridge = getAppBridge()
      if (!bridge) {
        await new Promise((r) => setTimeout(r, 800))
        const planName = plans.find((p) => p.key === planKey)?.name || planKey
        setMessage({
          type: 'success',
          text: `🧪 TEST MODE: Aapne "${planName}" plan select kiya. Real subscription ke liye Shopify Admin se app kholein.`,
        })
        setIsSubscribing(false)
        return
      }

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

      if (window.shopify?.navigation?.navigate) {
        window.shopify.navigation.navigate(confirmationUrl)
      } else if (window.top) {
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
  // Auto-redirect to Shopify Admin after billing success
  // ========================================
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const isSuccess = params.get('subscription') === 'success'
    const queryShop =
      params.get('shop') || shopDomain || 'amazon-product-manager.myshopify.com'

    if (
      isSuccess &&
      typeof window !== 'undefined' &&
      window.top === window.self &&
      queryShop
    ) {
      const shopSlug = queryShop.replace('.myshopify.com', '')
      const adminUrl = `https://admin.shopify.com/store/${shopSlug}/apps/stock-sync-partner`
      setMessage({
        type: 'success',
        text: '✅ Subscription approved! Redirecting you into Shopify Admin...',
      })
      setTimeout(() => {
        window.location.href = adminUrl
      }, 1200)
    }
  }, [shopDomain])

  // ========================================
  // Dev / Test activation helper
  // ========================================
  const handleTestActivate = async () => {
    setIsSubscribing(true)
    try {
      const targetShop = shopDomain || 'amazon-product-manager.myshopify.com'
      const res = await safeFetch(`${API_URL}/api/billing/activate-test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shop_domain: targetShop,
          plan_name: 'Basic Plan (Test)',
        }),
      })
      if (res.ok) {
        setSubscription({
          active: true,
          shop_domain: targetShop,
          subscription: { name: 'Basic Plan (Test)', status: 'ACTIVE' },
        })
        showToast('Active Test Mode enabled!')
      } else {
        throw new Error(res.data.detail || 'Test activation failed')
      }
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setIsSubscribing(false)
    }
  }

  // ========================================
  // 4. Add product handler
  // ✅ FIXED: /api prefix added
  // ========================================
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim() || isLoading) return

    setIsLoading(true)
    setMessage(null)

    try {
      const idToken = await getIdToken()

      // ✅ YAHAN /api ADD KIYA HAI
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
            markup: parseFloat(markup) || 2.0,
            markup_type: markupType,
          }),
        }
      )

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('Session expired. Please reload the app.')
        }
        if (res.status === 402) {
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
      setMarkup('2.00')
      showToast('Product added!')
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setIsLoading(false)
    }
  }

  return {
    amazonUrl,
    markup,
    markupType,
    isLoading,
    isSubscribing,
    message,
    shopifyReady,
    shopDomain,
    subscription,
    plans,
    checkingSub,

    setAmazonUrl,
    setMarkup,
    setMarkupType,

    handleAddProduct,
    handleSubscribe,
    handleTestActivate,
  }
}