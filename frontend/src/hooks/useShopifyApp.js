// src/hooks/useShopifyApp.js
// ✅ FIXED v8: Zustand Caching + PriceUpdateStore perfectly synced

import { useState, useEffect, useCallback, useRef } from 'react'
import { usePriceUpdateStore } from '../store/priceUpdateStore'
import { useAppStore } from '../store/useAppStore'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

const FALLBACK_SHOP_DOMAIN = 'test-store-ispfraip.myshopify.com'

function getAppBridge() {
  if (typeof window === 'undefined') return null
  if (window.shopify) return window.shopify
  if (window.appBridge) return window.appBridge
  return null
}

async function getIdToken() {
  const bridge = getAppBridge()
  if (!bridge) throw new Error('Shopify App Bridge not loaded.')
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
  if (bridge?.toast?.show) bridge.toast.show(message, { isError })
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

function resolveShopDomain(currentDomain) {
  if (currentDomain) return currentDomain
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search)
    const urlShop = params.get('shop')
    if (urlShop) return urlShop
  }
  return FALLBACK_SHOP_DOMAIN
}

export function useShopifyApp() {
  const [amazonUrl, setAmazonUrl] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSubscribing, setIsSubscribing] = useState(false)
  const [message, setMessage] = useState(null)
  const [shopifyReady, setShopifyReady] = useState(false)
  const [plans, setPlans] = useState([])
  
  const [selectedCollections, setSelectedCollections] = useState(new Set())
  const [collectionsLoading, setCollectionsLoading] = useState(false)
  const [storeMarkupLoading, setStoreMarkupLoading] = useState(false)

  // ✅ GLOBAL APP STORE
  const {
    isAppInitialized, setAppInitialized,
    shopDomain, setShopDomain,
    subscription, setSubscription,
    collections, setCollections,
    storeMarkup, setStoreMarkup
  } = useAppStore()

  // ✅ GLOBAL CRON STORE
  const {
    cronRunning, cronMessage, cronProgress,
    setCronRunning, setCronMessage, setCronProgress,
    startPolling, stopPolling, checkStatusOnce,
  } = usePriceUpdateStore()

  const bridgeCheckRef = useRef(null)

  // 1. Load Billing
  const loadBillingData = useCallback(async () => {
    if (isAppInitialized && subscription) return 

    try {
      const plansRes = await safeFetch(`${API_URL}/api/billing/plans`)
      if (plansRes.ok) setPlans(plansRes.data.plans || [])

      try {
        const idToken = await getIdToken()
        const subRes = await safeFetch(`${API_URL}/api/billing/status`, {
          headers: { Authorization: `Bearer ${idToken}` },
        })
        if (subRes.ok) setSubscription(subRes.data)
        else setSubscription({ active: false })
      } catch (tokenErr) {
        setSubscription({ active: false })
      }
    } catch (err) {
      setSubscription({ active: false })
    }
  }, [isAppInitialized, subscription, setSubscription])

  // 2. App Bridge Init
  useEffect(() => {
    let attempts = 0
    const MAX_ATTEMPTS = 20

    bridgeCheckRef.current = setInterval(async () => {
      attempts++
      const bridge = getAppBridge()

      if (bridge) {
        setShopifyReady(true)
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null

        const shop = bridge.config?.shop || bridge.shop
        if (shop && !shopDomain) setShopDomain(shop)
        else if (!shopDomain) {
          const params = new URLSearchParams(window.location.search)
          const urlShop = params.get('shop')
          if (urlShop) setShopDomain(urlShop)
        }

        if (!isAppInitialized) {
          await loadBillingData()
          setAppInitialized(true)
          showToast('Amazon Product Manager loaded!')
        }

        try {
          const idToken = await getIdToken()
          await checkStatusOnce(API_URL, idToken) // ✅ Cron status check
        } catch (err) {}
        return
      }

      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(bridgeCheckRef.current)
        bridgeCheckRef.current = null
        if (!isAppInitialized) {
          setMessage({ type: 'error', text: '⚠️ Shopify Admin se app kholein.' })
          await loadBillingData()
          setAppInitialized(true)
        }
      }
    }, 500)

    return () => {
      if (bridgeCheckRef.current) clearInterval(bridgeCheckRef.current)
    }
  }, [loadBillingData, checkStatusOnce, isAppInitialized, shopDomain, setAppInitialized, setShopDomain])

  // 3. Load Markup
  const loadStoreMarkup = useCallback(async (domain, force = false) => {
    if (storeMarkup && !force) return
    const actualDomain = resolveShopDomain(domain)
    if (!actualDomain) return
    setStoreMarkupLoading(true)

    try {
      const res = await safeFetch(`${API_URL}/api/markup/store-default?shop_domain=${encodeURIComponent(actualDomain)}`)
      if (res.ok && res.data) {
        setStoreMarkup({
          markup: res.data.markup ?? 2.0,
          markupType: res.data.markup_type ?? 'fixed',
          extraPercent: res.data.extra_percent ?? 0,
          countryId: res.data.country_id ?? null,
          countryName: res.data.country_name ?? null,
          taxRate: res.data.tax_rate ?? 0,
        })
      }
    } catch (err) {
      console.error('❌ Load store markup error:', err)
    } finally {
      setStoreMarkupLoading(false)
    }
  }, [storeMarkup, setStoreMarkup])

  // 4. Load Collections
  const loadCollections = useCallback(async (domain, force = false) => {
    if (collections.length > 0 && !force) return
    const actualDomain = resolveShopDomain(domain)
    setCollectionsLoading(true)

    try {
      const res = await safeFetch(`${API_URL}/api/shopify/collections?shop_domain=${encodeURIComponent(actualDomain)}`)
      if (res.ok && res.data.success) {
        setCollections(res.data.collections || [])
      }
    } catch (err) {
      console.error('❌ Load collections error:', err)
    } finally {
      setCollectionsLoading(false)
    }
  }, [collections.length, setCollections])

  // 5. Auto Load
  useEffect(() => {
    const domain = resolveShopDomain(shopDomain)
    if (domain && subscription?.active) {
      loadCollections(domain)
      loadStoreMarkup(domain)
    }
  }, [shopDomain, subscription?.active, loadCollections, loadStoreMarkup])

  // Handlers
  const toggleCollection = useCallback((id) => {
    setSelectedCollections((prev) => {
      const newSet = new Set(prev)
      newSet.has(id) ? newSet.delete(id) : newSet.add(id)
      return newSet
    })
  }, [])

  const clearCollections = useCallback(() => setSelectedCollections(new Set()), [])
  
  const refreshCollections = useCallback(() => {
    const domain = resolveShopDomain(shopDomain)
    return loadCollections(domain, true)
  }, [shopDomain, loadCollections])

  // Cron Job
  const handleRunCron = useCallback(async () => {
    if (cronRunning) return
    setCronRunning(true)
    setCronMessage(null)
    setCronProgress({ running: true, step: 0, total: 0, currentProduct: 'Starting...', summary: null })

    try {
      const idToken = await getIdToken()
      const res = await safeFetch(`${API_URL}/api/shopify/trigger-price-update-async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${idToken}` },
      })
      if (!res.ok) throw new Error(res.data.detail || `HTTP ${res.status}`)
      startPolling(API_URL, idToken)
    } catch (err) {
      stopPolling()
      setCronProgress({ running: false, step: 0, total: 0, currentProduct: null, summary: null })
      setCronMessage({ type: 'error', text: `❌ ${err.message}` })
      showToast('Price update failed!', true)
      setCronRunning(false)
    }
  }, [cronRunning, startPolling, stopPolling, setCronRunning, setCronMessage, setCronProgress])

  // Subscribe
  const handleSubscribe = async (planKey) => {
    if (isSubscribing) return
    setIsSubscribing(true)
    setMessage(null)

    try {
      const bridge = getAppBridge()
      if (!bridge) {
        await new Promise((r) => setTimeout(r, 800))
        const planName = plans.find((p) => p.key === planKey)?.name || planKey
        setMessage({ type: 'success', text: `🧪 TEST MODE: "${planName}" selected.` })
        setIsSubscribing(false)
        return
      }

      const idToken = await getIdToken()
      const res = await safeFetch(`${API_URL}/api/billing/subscribe/${planKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${idToken}` },
      })

      if (!res.ok) throw new Error(res.data.detail || 'Subscription failed')
      const confirmationUrl = res.data.confirmation_url
      if (!confirmationUrl) throw new Error('No confirmation URL received')

      if (window.shopify?.navigation?.navigate) window.shopify.navigation.navigate(confirmationUrl)
      else if (window.top) window.top.location.href = confirmationUrl
      else window.location.href = confirmationUrl
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
      setIsSubscribing(false)
    }
  }

  // Test Activate
  const handleTestActivate = async () => {
    setIsSubscribing(true)
    try {
      const targetShop = resolveShopDomain(shopDomain)
      const res = await safeFetch(`${API_URL}/api/billing/activate-test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shop_domain: targetShop, plan_name: 'Basic Plan (Test)' }),
      })
      if (res.ok) {
        setSubscription({ active: true, shop_domain: targetShop, subscription: { name: 'Basic Plan (Test)', status: 'ACTIVE' } })
        showToast('Active Test Mode enabled!')
        if (targetShop) {
          loadCollections(targetShop, true)
          loadStoreMarkup(targetShop, true)
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

  // Add Product
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim() || isLoading) return

    setIsLoading(true)
    setMessage(null)

    try {
      const idToken = await getIdToken()
      const collectionIdsArray = Array.from(selectedCollections)

      const res = await safeFetch(`${API_URL}/api/shopify/app/add-product`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${idToken}` },
        body: JSON.stringify({ amazon_url: amazonUrl.trim(), collection_ids: collectionIdsArray }),
      })

      if (!res.ok) {
        if (res.status === 401) throw new Error('Session expired. Please reload the app.')
        if (res.status === 402) {
          setMessage({ type: 'error', text: '❌ Active subscription required.' })
          setSubscription({ active: false })
          return
        }
        if (res.status === 404) throw new Error(res.data.detail || 'Store not connected.')
        if (res.status === 409) throw new Error(res.data.detail || 'Product already exists.')
        throw new Error(res.data.detail || 'Failed to add product')
      }

      const collectionsAdded = res.data.collections_added || 0
      const finalPrice = res.data.final_price
      const successMsg = res.data.message || 'Product added successfully!'

      setMessage({ type: 'success', text: `✅ ${successMsg}${collectionsAdded > 0 ? ` (+${collectionsAdded})` : ''}${finalPrice ? ` — $${finalPrice}` : ''}` })
      setAmazonUrl('')
      clearCollections()
      showToast('Product added!')
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setIsLoading(false)
    }
  }

  // Auto Redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const isSuccess = params.get('subscription') === 'success'
    const queryShop = params.get('shop') || shopDomain || FALLBACK_SHOP_DOMAIN

    if (isSuccess && window.top === window.self && queryShop) {
      const shopSlug = queryShop.replace('.myshopify.com', '')
      const adminUrl = `https://admin.shopify.com/store/${shopSlug}/apps/stock-sync-partner`
      setMessage({ type: 'success', text: '✅ Redirecting to Shopify Admin...' })
      setTimeout(() => { window.location.href = adminUrl }, 1200)
    }
  }, [shopDomain])

  return {
    amazonUrl, isLoading, isSubscribing, message, shopifyReady, shopDomain,
    subscription, plans,
    checkingSub: !isAppInitialized, // ✅ Caching ki wajah se ab fast hoga
    setAmazonUrl, storeMarkup, storeMarkupLoading,
    handleAddProduct, handleSubscribe, handleTestActivate,
    collections, selectedCollections, collectionsLoading, toggleCollection, clearCollections, loadCollections, refreshCollections,
    cronRunning, cronMessage, cronProgress, handleRunCron,
  }
}