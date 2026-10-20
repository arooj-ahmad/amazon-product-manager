// ============================================
// frontend/src/pages/ProductsPricing.jsx
// Product-wise Pricing Editor
// + ✅ FIXED: Bulk Update hamesha Settings se values load karega
// ============================================

import { useState, useEffect } from 'react'
import {
  updatePricing,
  bulkUpdatePricing,
  getStoreIdByDomain,
} from '../api/pricing'
import Loader from '../components/Loader'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ============================================
// Detect Shopify store domain
// ============================================
function getShopDomain() {
  const params = new URLSearchParams(window.location.search)
  const shop = params.get('shop')
  if (shop) return shop

  const pathMatch = window.location.pathname.match(/\/store\/([^/]+)/)
  if (pathMatch) {
    return `${pathMatch[1]}.myshopify.com`
  }

  return null
}

// ============================================
// ✅ Shopify iframe-compatible navigation
// ============================================
function navigateTo(path) {
  const targetHash = `#${path}`
  console.log(`🧭 Navigating to: ${targetHash}`)

  if (window.location.hash === targetHash) {
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = targetHash
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

function formatCurrency(amount) {
  return `$${parseFloat(amount || 0).toFixed(2)}`
}

function formatMarkup(markup, type, extra) {
  if (type === 'percent') return `+${markup}%`
  if (type === 'both') return `+$${markup} + ${extra}%`
  return `+$${markup}`
}

// ============================================
// Main Component
// ============================================
export default function ProductsPricing() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [message, setMessage] = useState(null)
  const [storeId, setStoreId] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)

  const [savedDefault, setSavedDefault] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')

  // ✅ FIXED: Bulk data load from Local Storage (pehle se hai)
  const [bulkData, setBulkData] = useState(() => {
    const saved = localStorage.getItem('bulkPricingData')
    if (saved) {
      try { return JSON.parse(saved) } catch (e) {}
    }
    return {
      markup_type: 'fixed',
      markup_value: '',
      extra_percent: '',
      tax_rate: '0',
    }
  })
  const [bulkLoading, setBulkLoading] = useState(false)

  // ✅ FIXED: Save to Local Storage whenever bulkData changes
  useEffect(() => {
    localStorage.setItem('bulkPricingData', JSON.stringify(bulkData))
  }, [bulkData])

  useEffect(() => {
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const init = async () => {
    setLoading(true)
    try {
      const domain = getShopDomain()
      if (!domain) {
        throw new Error('Could not detect shop domain.')
      }
      setShopDomain(domain)

      const sid = await getStoreIdByDomain(domain)
      setStoreId(sid)

      await loadProducts(sid)

      // Load default markup + tax
      try {
        const defRes = await safeFetch(
          `${API_URL}/api/markup/store-default?shop_domain=${encodeURIComponent(domain)}`
        )
        if (defRes.ok && defRes.data) {
          console.log('✅ Loaded default markup:', defRes.data)
          setSavedDefault(defRes.data)

          // ✅ FIXED: Ab hamesha Settings se values load hongi (Local Storage check hata diya)
          setBulkData({
            markup_type: defRes.data.markup_type || 'fixed',
            markup_value: defRes.data.markup
              ? String(defRes.data.markup)
              : '',
            extra_percent: defRes.data.extra_percent
              ? String(defRes.data.extra_percent)
              : '',
            tax_rate: defRes.data.tax_rate ? String(defRes.data.tax_rate) : '0',
          })
        }
      } catch (err) {
        console.warn('⚠️ Could not load default markup:', err)
      }
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  const loadProducts = async (sid) => {
    const url = `${API_URL}/api/markup/products?store_id=${sid}`
    const productsRes = await safeFetch(url)
    if (!productsRes.ok) {
      throw new Error(productsRes.data.detail || 'Failed to load products')
    }
    setProducts(productsRes.data || [])
  }

  const handleBulkUpdate = async () => {
    if (!bulkData.markup_value || parseFloat(bulkData.markup_value) <= 0) {
      setMessage({ type: 'error', text: '❌ Please enter a markup value' })
      return
    }
    if (!storeId) {
      setMessage({ type: 'error', text: '❌ Could not detect Store ID' })
      return
    }

    if (!window.confirm('Apply this pricing to all products?')) return

    setBulkLoading(true)
    setMessage(null)
    try {
      const res = await bulkUpdatePricing({
        store_id: storeId,
        markup_type: bulkData.markup_type,
        markup_value: parseFloat(bulkData.markup_value),
        extra_percent: parseFloat(bulkData.extra_percent) || 0,
        tax_rate: parseFloat(bulkData.tax_rate),
      })

      setMessage({
        type: 'success',
        text: `✅ ${res.updated} products updated! (Shopify: ${res.shopify_updated || 0})`,
      })

      await loadProducts(storeId)
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setBulkLoading(false)
    }
  }

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  const filteredProducts = products.filter((p) => {
    if (!searchTerm.trim()) return true
    const term = searchTerm.toLowerCase()
    return (
      (p.title || '').toLowerCase().includes(term) ||
      (p.asin || '').toLowerCase().includes(term)
    )
  })

  if (loading) {
    return <Loader text="Loading products..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <button
          type="button"
          onClick={handleBackToDashboard}
          style={styles.backBtn}
        >
          ← Back to Dashboard
        </button>

        <h1 style={styles.h1}>📦 Product Pricing</h1>
        <p style={styles.subtitle}>
          Bulk update or set a different markup for each product.
        </p>

        {!storeId && (
          <div
            style={{
              ...styles.messageBox,
              background: '#fef3e7',
              color: '#b54708',
              border: '1px solid #fedf89',
            }}
          >
            ⚠️ Could not detect Store ID.
          </div>
        )}

        {savedDefault && (
          <div style={styles.infoBanner}>
            <span style={styles.infoIcon}>💾</span>
            <div style={styles.infoText}>
              <strong>Current Default Markup:</strong>{' '}
              <span style={styles.infoValue}>
                {formatMarkup(
                  savedDefault.markup,
                  savedDefault.markup_type,
                  savedDefault.extra_percent
                )}
              </span>
              <span style={styles.infoHint}>
                {' '}
                — this markup will be applied to new products
              </span>
            </div>
          </div>
        )}

        {/* Bulk Update Section */}
        <div style={styles.bulkCard}>
          <div style={styles.bulkHeader}>
            <span style={styles.bulkIcon}>🔄</span>
            <div>
              <h3 style={styles.bulkTitle}>Bulk Update All Products</h3>
              <p style={styles.bulkSubtitle}>
                These settings will be applied to all existing products
              </p>
            </div>
          </div>

          <div style={styles.bulkRow}>
            <select
              value={bulkData.markup_type}
              onChange={(e) =>
                setBulkData({ ...bulkData, markup_type: e.target.value })
              }
              style={styles.bulkSelect}
              disabled={bulkLoading}
            >
              <option value="fixed">$ Fixed</option>
              <option value="percent">% Percent</option>
              <option value="both">$ + % (Both)</option>
            </select>

            <input
              type="number"
              step="0.01"
              min="0"
              value={bulkData.markup_value}
              onChange={(e) =>
                setBulkData({ ...bulkData, markup_value: e.target.value })
              }
              style={styles.bulkInput}
              disabled={bulkLoading}
              placeholder={
                bulkData.markup_type === 'percent' ? 'e.g. 10' : 'e.g. 2.00'
              }
            />

            {bulkData.markup_type === 'both' && (
              <input
                type="number"
                step="0.01"
                min="0"
                max="500"
                value={bulkData.extra_percent}
                onChange={(e) =>
                  setBulkData({
                    ...bulkData,
                    extra_percent: e.target.value,
                  })
                }
                style={styles.bulkInput}
                disabled={bulkLoading}
                placeholder="Extra %"
              />
            )}

            <input
              type="number"
              step="0.01"
              min="0"
              max="100"
              placeholder="Tax %"
              value={bulkData.tax_rate}
              onChange={(e) =>
                setBulkData({ ...bulkData, tax_rate: e.target.value })
              }
              style={styles.bulkInput}
              disabled={bulkLoading}
            />

            <button
              type="button"
              onClick={handleBulkUpdate}
              disabled={
                bulkLoading ||
                !storeId ||
                !bulkData.markup_value ||
                parseFloat(bulkData.markup_value) <= 0
              }
              style={{
                ...styles.primaryBtn,
                background:
                  bulkLoading || !storeId || !bulkData.markup_value
                    ? '#babfc3'
                    : '#008060',
                cursor:
                  bulkLoading || !storeId || !bulkData.markup_value
                    ? 'not-allowed'
                    : 'pointer',
              }}
            >
              {bulkLoading ? '⏳ Applying...' : 'Apply to All'}
            </button>
          </div>
        </div>

        {/* Search bar */}
        <div style={styles.searchBox}>
          <input
            type="text"
            placeholder="🔍 Search by title or ASIN..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={styles.searchInput}
          />
          <span style={styles.searchCount}>
            {filteredProducts.length} / {products.length} products
          </span>
        </div>

        {message && (
          <div
            style={{
              ...styles.messageBox,
              background: message.type === 'success' ? '#e4f5e4' : '#fbeae5',
              color: message.type === 'success' ? '#008060' : '#d72c0d',
              border: `1px solid ${
                message.type === 'success' ? '#aee9ae' : '#febcb3'
              }`,
            }}
          >
            {message.text}
          </div>
        )}

        {filteredProducts.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#666' }}>
            {searchTerm
              ? 'No products matched your search.'
              : 'No products found.'}
          </p>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.theadRow}>
                  <th style={styles.th}>Product</th>
                  <th style={styles.th}>Amazon Price</th>
                  <th style={styles.th}>Type</th>
                  <th style={styles.th}>Markup</th>
                  <th style={styles.th}>Extra %</th>
                  <th style={styles.th}>Tax %</th>
                  <th style={styles.th}>Tax Amt</th>
                  <th style={styles.th}>Final Price</th>
                  <th style={styles.th}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((p) => (
                  <ProductRow
                    key={p.id}
                    product={p}
                    storeId={storeId}
                    saving={savingId === p.id}
                    onSaveStart={() => setSavingId(p.id)}
                    onSaveEnd={() => setSavingId(null)}
                    onMessage={setMessage}
                    loadProducts={loadProducts}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================
// Product Row
// ============================================
function ProductRow({
  product,
  storeId,
  saving,
  onSaveStart,
  onSaveEnd,
  onMessage,
  loadProducts,
}) {
  const [markup, setMarkup] = useState('')
  const [type, setType] = useState('fixed')
  const [extraPercent, setExtraPercent] = useState('')
  const [taxRate, setTaxRate] = useState('0')

  // ✅ FIXED: Force state update jab bhi product prop change ho
  useEffect(() => {
    setMarkup(product.markup != null && product.markup > 0 ? String(product.markup) : '')
    setType(product.markup_type || 'fixed')
    setExtraPercent(product.extra_percent != null && product.extra_percent > 0 ? String(product.extra_percent) : '')
    setTaxRate(product.tax_rate != null ? String(product.tax_rate) : '0')
  }, [product])

  const calc = (() => {
    const amazon = parseFloat(product.amazon_price) || 0
    const m = parseFloat(markup) || 0
    const extra = parseFloat(extraPercent) || 0
    const tax = parseFloat(taxRate) || 0

    let subtotal
    if (type === 'percent') {
      subtotal = amazon * (1 + m / 100)
    } else if (type === 'both') {
      const base = amazon + m
      subtotal = base * (1 + extra / 100)
    } else {
      subtotal = amazon + m
    }

    const taxAmount = subtotal * (tax / 100)
    const finalPrice = subtotal + taxAmount

    return {
      tax_amount: taxAmount.toFixed(2),
      final_price: finalPrice.toFixed(2),
    }
  })()

  const handleSave = async () => {
    if (!markup || parseFloat(markup) <= 0) {
      onMessage({ type: 'error', text: '❌ Please enter a markup value' })
      return
    }
    if (!storeId) {
      onMessage({ type: 'error', text: '❌ Could not detect Store ID' })
      return
    }

    onSaveStart()
    onMessage(null)
    try {
      await updatePricing({
        product_id: product.id,
        store_id: storeId,
        markup_type: type,
        markup_value: parseFloat(markup),
        extra_percent: parseFloat(extraPercent) || 0,
        tax_rate: parseFloat(taxRate),
      })
      onMessage({
        type: 'success',
        text: '✅ Pricing saved! (Shopify also updated)',
      })
      
      if (loadProducts) await loadProducts(storeId);

    } catch (err) {
      onMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      onSaveEnd()
    }
  }

  return (
    <tr style={styles.tbodyRow}>
      <td style={styles.td}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {product.image_url && (
            <img
              src={product.image_url}
              alt=""
              style={{
                width: 40,
                height: 40,
                objectFit: 'cover',
                borderRadius: 4,
              }}
            />
          )}
          <span style={{ fontSize: 13 }}>
            {product.title?.slice(0, 50) || 'Untitled'}
          </span>
        </div>
      </td>

      <td style={styles.td}>${(product.amazon_price || 0).toFixed(2)}</td>

      <td style={styles.td}>
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          style={styles.rowSelect}
          disabled={saving}
        >
          <option value="fixed">$ Fixed</option>
          <option value="percent">% Percent</option>
          <option value="both">$ + % (Both)</option>
        </select>
      </td>

      <td style={styles.td}>
        <input
          type="number"
          step="0.01"
          min="0"
          value={markup}
          onChange={(e) => setMarkup(e.target.value)}
          style={styles.rowInput}
          disabled={saving}
          placeholder={type === 'percent' ? '10' : '2.00'}
        />
      </td>

      <td style={styles.td}>
        <input
          type="number"
          step="0.01"
          min="0"
          max="500"
          value={extraPercent}
          onChange={(e) => setExtraPercent(e.target.value)}
          style={{
            ...styles.rowInput,
            opacity: type === 'both' ? 1 : 0.4,
          }}
          disabled={saving || type !== 'both'}
          placeholder="0"
        />
      </td>

      <td style={styles.td}>
        <input
          type="number"
          step="0.01"
          min="0"
          max="100"
          value={taxRate}
          onChange={(e) => setTaxRate(e.target.value)}
          style={styles.rowInput}
          disabled={saving}
        />
      </td>

      <td style={{ ...styles.td, color: '#637381' }}>${calc.tax_amount}</td>

      <td style={{ ...styles.td, fontWeight: 600, color: '#008060' }}>
        {formatCurrency(parseFloat(calc.final_price))}
      </td>

      <td style={styles.td}>
        <button
          type="button"
          onClick={handleSave}
          disabled={!markup || saving || !storeId}
          style={{
            padding: '6px 16px',
            background:
              markup && !saving && storeId
                ? '#008060'
                : '#babfc3',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor:
              markup && !saving && storeId
                ? 'pointer'
                : 'not-allowed',
            fontSize: 13,
          }}
        >
          {saving ? '⏳' : 'Save'}
        </button>
      </td>
    </tr>
  )
}

// ============================================
// Styles
// ============================================
const styles = {
  page: {
    padding: '20px',
    fontFamily: 'Inter, -apple-system, sans-serif',
    background: '#f6f6f7',
    minHeight: '100vh',
  },
  container: { maxWidth: '1400px', margin: '0 auto' },
  centerBox: { padding: '60px 20px', textAlign: 'center' },
  h1: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#202223',
    marginBottom: '4px',
  },
  subtitle: { color: '#637381', fontSize: '14px', marginBottom: '20px' },

  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 16px',
    marginBottom: '16px',
    background: 'white',
    color: '#202223',
    border: '1px solid #e1e3e5',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  infoBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    marginBottom: '16px',
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: 8,
  },
  infoIcon: {
    fontSize: '18px',
  },
  infoText: {
    fontSize: '13px',
    color: '#166534',
  },
  infoValue: {
    background: 'white',
    padding: '2px 10px',
    borderRadius: 4,
    border: '1px solid #86efac',
    fontWeight: '700',
    color: '#15803d',
    marginLeft: '4px',
  },
  infoHint: {
    color: '#65a30d',
  },

  bulkCard: {
    background: 'white',
    padding: 20,
    borderRadius: 8,
    marginBottom: 20,
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  bulkHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: 16,
  },
  bulkIcon: {
    fontSize: '22px',
  },
  bulkTitle: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 2px 0',
  },
  bulkSubtitle: {
    fontSize: '12px',
    color: '#637381',
    margin: 0,
  },
  bulkRow: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  bulkSelect: {
    padding: '8px 12px',
    border: '1px solid #babfc3',
    borderRadius: 6,
    fontSize: 14,
  },
  bulkInput: {
    padding: '8px 12px',
    border: '1px solid #babfc3',
    borderRadius: 6,
    fontSize: 14,
    width: 100,
  },

  searchBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 16px',
    marginBottom: '16px',
    background: 'white',
    border: '1px solid #e1e3e5',
    borderRadius: 8,
  },
  searchInput: {
    flex: 1,
    padding: '8px 12px',
    border: '1px solid #babfc3',
    borderRadius: 6,
    fontSize: 14,
    outline: 'none',
  },
  searchCount: {
    fontSize: 13,
    color: '#637381',
    whiteSpace: 'nowrap',
  },

  messageBox: {
    padding: '12px 16px',
    borderRadius: 6,
    fontSize: 14,
    marginBottom: '16px',
  },
  tableWrap: {
    background: 'white',
    borderRadius: 8,
    overflow: 'hidden',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  theadRow: { background: '#f6f6f7', textAlign: 'left' },
  th: {
    padding: 12,
    fontSize: 13,
    fontWeight: 600,
    color: '#202223',
    borderBottom: '1px solid #e1e3e5',
  },
  tbodyRow: { borderBottom: '1px solid #f0f0f0' },
  td: {
    padding: 12,
    fontSize: 13,
    color: '#202223',
    verticalAlign: 'middle',
  },
  rowSelect: {
    padding: '6px 8px',
    border: '1px solid #babfc3',
    borderRadius: 4,
    fontSize: 13,
  },
  rowInput: {
    padding: '6px 8px',
    border: '1px solid #babfc3',
    borderRadius: 4,
    fontSize: 13,
    width: 70,
  },
  primaryBtn: {
    color: 'white',
    border: 'none',
    padding: '10px 20px',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: '600',
  },
}