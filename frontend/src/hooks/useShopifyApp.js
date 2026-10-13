// src/hooks/useShopifyApp.js
import { useState, useEffect, useCallback, useRef } from 'react'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ✅ Hardcoded fallback domain (testing ke liye)
const FALLBACK_SHOP_DOMAIN = 'test-store-ispfraip.myshopify.com'

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
// Helper: Domain determine karo (multiple fallbacks)
// ============================================
function resolveShopDomain(currentDomain) {
  if (currentDomain) return currentDomain

  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search)
    const urlShop = params.get('shop')
    if (urlShop) return urlShop
  }

  return FALLBACK_SHOP_DOMAIN
}

// ============================================
// Main Hook
// ============================================
export function useShopifyApp() {
  const [amazonUrl, setAmazonUrl] = useState('')

  // ✅ FIXED: markup default '2.00' → '' (user khud set karega)
  const [markup, setMarkup] = useState('')
  const [markupType, setMarkupType] = useState('fixed')

  // ✅ FIXED: extraPercent default '10' → '' (user khud set karega)
  const [extraPercent, setExtraPercent] = useState('')

  const [isLoading, setIsLoading] = useState(false)
  const [isSubscribing, setIsSubscribing] = useState(false)
  const [message, setMessage] = useState(null)

  const [shopifyReady, setShopifyReady] = useState(false)
  const [shopDomain, setShopDomain] = useState('')

  const [subscription, setSubscription] = useState(null)
  const [plans, setPlans] = useState([])
  const [checkingSub, setCheckingSub] = useState(true)

  // ✅ Collections state
  const [collections, setCollections] = useState([])
  const [selectedCollections, setSelectedCollections] = useState(new Set())
  const [collectionsLoading, setCollectionsLoading] = useState(false)

  // ✅ Cron job state
  const [cronRunning, setCronRunning] = useState(false)
  const [cronMessage, setCronMessage] = useState(null)

  const bridgeCheckRef = useRef(null)

  // ========================================
  // 1. Load billing data
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
  // ✅ Load Collections (with domain fallback)
  // ========================================
  const loadCollections = useCallback(async (domain) => {
    const actualDomain = resolveShopDomain(domain)

    console.log('📁 Fetching collections for:', actualDomain)

    setCollectionsLoading(true)
    try {
      const res = await safeFetch(
        `${API_URL}/api/shopify/collections?shop_domain=${encodeURIComponent(actualDomain)}`
      )

      if (!res.ok) {
        throw new Error(res.data.detail || `HTTP ${res.status}`)
      }

      if (res.data.success) {
        setCollections(res.data.collections || [])
        console.log(`✅ Loaded ${res.data.collections?.length || 0} collections`)
      } else {
        console.warn('⚠️ Collections fetch failed:', res.data)
        setCollections([])
      }
    } catch (err) {
      console.error('❌ Load collections error:', err)
      setCollections([])
    } finally {
      setCollectionsLoading(false)
    }
  }, [])

  // ========================================
  // ✅ Auto-load collections
  // ========================================
  useEffect(() => {
    const domain = resolveShopDomain(shopDomain)

    if (domain && subscription?.active) {
      console.log('📁 Auto-loading collections for:', domain)
      loadCollections(domain)
    }
  }, [shopDomain, subscription?.active, loadCollections])

  // ========================================
  // ✅ Toggle Collection Selection
  // ========================================
  const toggleCollection = useCallback((collectionId) => {
    setSelectedCollections((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(collectionId)) {
        newSet.delete(collectionId)
      } else {
        newSet.add(collectionId)
      }
      return newSet
    })
  }, [])

  // ========================================
  // ✅ Clear All Selections
  // ========================================
  const clearCollections = useCallback(() => {
    setSelectedCollections(new Set())
  }, [])

  // ========================================
  // ✅ Manual Refresh Collections
  // ========================================
  const refreshCollections = useCallback(() => {
    const domain = resolveShopDomain(shopDomain)
    return loadCollections(domain)
  }, [shopDomain, loadCollections])

  // ========================================
  // ✅ Trigger Cron Job Manually
  // ========================================
  const handleRunCron = useCallback(async () => {
    if (cronRunning) return

    setCronRunning(true)
    setCronMessage(null)

    try {
      const idToken = await getIdToken()

      console.log('🚀 Triggering price update cron...')

      const res = await safeFetch(
        `${API_URL}/api/shopify/trigger-price-update`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${idToken}`,
          },
        }
      )

      if (!res.ok) {
        throw new Error(res.data.detail || `HTTP ${res.status}`)
      }

      console.log('✅ Cron job completed:', res.data)

      setCronMessage({
        type: 'success',
        text: `✅ ${res.data.message || 'Price update completed!'}`,
      })

      showToast('Price update completed!')

      setTimeout(() => setCronMessage(null), 5000)

    } catch (err) {
      console.error('❌ Cron trigger failed:', err)

      setCronMessage({
        type: 'error',
        text: `❌ ${err.message}`,
      })

      showToast('Price update failed!', true)
    } finally {
      setCronRunning(false)
    }
  }, [cronRunning])

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
  // Auto-redirect after billing success
  // ========================================
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const isSuccess = params.get('subscription') === 'success'
    const queryShop =
      params.get('shop') || shopDomain || FALLBACK_SHOP_DOMAIN

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
      const targetShop = resolveShopDomain(shopDomain)
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

        if (targetShop) {
          loadCollections(targetShop)
        }
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
  // + ✅ NAYA: extra_percent bhejo
  // + ✅ FIXED: markup validate karo (blank allow nahi)
  // ========================================
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim() || isLoading) return

    // ✅ FIXED: Markup validation
    if (!markup || parseFloat(markup) <= 0) {
      setMessage({
        type: 'error',
        text: '❌ Please enter a markup value (greater than 0)',
      })
      return
    }

    setIsLoading(true)
    setMessage(null)

    try {
      const idToken = await getIdToken()

      const collectionIdsArray = Array.from(selectedCollections)

      console.log('📤 Sending product with collections:', collectionIdsArray)
      console.log('📤 Markup:', markup, markupType, 'extra:', extraPercent)

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
            markup: parseFloat(markup),   // ✅ FIXED: no fallback 2.0
            markup_type: markupType,
            extra_percent: parseFloat(extraPercent) || 0,
            collection_ids: collectionIdsArray,
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

      const collectionsAdded = res.data.collections_added || 0
      const successMsg = res.data.message || 'Product added successfully!'

      setMessage({
        type: 'success',
        text: `✅ ${successMsg}${collectionsAdded > 0 ? ` (+${collectionsAdded} collections)` : ''}`,
      })

      // ✅ FIXED: Reset to empty
      setAmazonUrl('')
      setMarkup('')
      setExtraPercent('')
      clearCollections()

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
    extraPercent,
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
    setExtraPercent,

    handleAddProduct,
    handleSubscribe,
    handleTestActivate,

    // ✅ Collections
    collections,
    selectedCollections,
    collectionsLoading,
    toggleCollection,
    clearCollections,
    loadCollections,
    refreshCollections,

    // ✅ Cron job
    cronRunning,
    cronMessage,
    handleRunCron,
  }
}