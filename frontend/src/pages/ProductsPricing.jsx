// ============================================
// frontend/src/pages/ProductsPricing.jsx
// Product-wise Pricing Editor
// Har product ka markup, country, tax alag set karo
// ============================================

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCountries,
  updatePricing,
  getStoreIdByDomain,
} from '../api/pricing'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ============================================
// Shop domain nikaalo
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

function formatCurrency(amount, country) {
  if (!country) return `$${parseFloat(amount || 0).toFixed(2)}`
  try {
    return new Intl.NumberFormat('en', {
      style: 'currency',
      currency: country.currency_code,
    }).format(amount)
  } catch {
    return `${country.currency_symbol || '$'}${parseFloat(amount || 0).toFixed(2)}`
  }
}

// ============================================
// Main Component
// ============================================
export default function ProductsPricing() {
  const navigate = useNavigate()

  const [products, setProducts] = useState([])
  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [message, setMessage] = useState(null)
  const [storeId, setStoreId] = useState(null)

  // ✅ Search
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const init = async () => {
    setLoading(true)
    try {
      const domain = getShopDomain()
      if (!domain) {
        throw new Error('Shop domain detect nahi ho saka.')
      }

      const sid = await getStoreIdByDomain(domain)
      setStoreId(sid)

      const countriesData = await getCountries()
      setCountries(countriesData || [])

      const url = `${API_URL}/api/markup/products?store_id=${sid}`
      const productsRes = await safeFetch(url)
      if (!productsRes.ok) {
        throw new Error(productsRes.data.detail || 'Failed to load products')
      }
      setProducts(productsRes.data || [])
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  // Filtered products
  const filteredProducts = products.filter((p) => {
    if (!searchTerm.trim()) return true
    const term = searchTerm.toLowerCase()
    return (
      (p.title || '').toLowerCase().includes(term) ||
      (p.asin || '').toLowerCase().includes(term)
    )
  })

  if (loading) {
    return (
      <div style={styles.centerBox}>
        <p style={{ color: '#637381' }}>⏳ Loading products...</p>
      </div>
    )
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <button
          type="button"
          onClick={() => navigate('/shopify-app')}
          style={styles.backBtn}
        >
          ← Back to Dashboard
        </button>

        <h1 style={styles.h1}>📦 Product Pricing</h1>
        <p style={styles.subtitle}>
          Har product ka markup, country aur tax alag set karein.
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
            ⚠️ Store ID detect nahi ho saka.
          </div>
        )}

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
              ? 'Koi product search se match nahi hua.'
              : 'Koi product nahi mila.'}
          </p>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.theadRow}>
                  <th style={styles.th}>Product</th>
                  <th style={styles.th}>Amazon Price</th>
                  <th style={styles.th}>Country</th>
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
                    countries={countries}
                    storeId={storeId}
                    saving={savingId === p.id}
                    onSaveStart={() => setSavingId(p.id)}
                    onSaveEnd={() => setSavingId(null)}
                    onMessage={setMessage}
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
// Product Row (same as before)
// ============================================
function ProductRow({
  product,
  countries,
  storeId,
  saving,
  onSaveStart,
  onSaveEnd,
  onMessage,
}) {
  const [countryId, setCountryId] = useState('')

  const [markup, setMarkup] = useState(
    product.markup != null && product.markup > 0 ? String(product.markup) : ''
  )

  const [type, setType] = useState(product.markup_type || 'fixed')

  const [extraPercent, setExtraPercent] = useState(
    product.extra_percent != null && product.extra_percent > 0
      ? String(product.extra_percent)
      : ''
  )

  const [taxRate, setTaxRate] = useState('0')

  const selectedCountry = countries.find((c) => c.id === parseInt(countryId))

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

  const handleCountryChange = (val) => {
    setCountryId(val)
    const country = countries.find((c) => c.id === parseInt(val))
    if (country) setTaxRate(String(country.default_tax_rate))
  }

  const handleSave = async () => {
    if (!countryId) {
      onMessage({ type: 'error', text: '❌ Country select karein' })
      return
    }
    if (!markup || parseFloat(markup) <= 0) {
      onMessage({ type: 'error', text: '❌ Markup value enter karein' })
      return
    }
    if (!storeId) {
      onMessage({ type: 'error', text: '❌ Store ID detect nahi ho saka' })
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
        text: '✅ Pricing save ho gayi! (Shopify bhi update)',
      })
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
          value={countryId}
          onChange={(e) => handleCountryChange(e.target.value)}
          style={styles.rowSelect}
          disabled={saving}
        >
          <option value="">Select</option>
          {countries.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </td>

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
        {formatCurrency(parseFloat(calc.final_price), selectedCountry)}
      </td>

      <td style={styles.td}>
        <button
          type="button"
          onClick={handleSave}
          disabled={!countryId || !markup || saving || !storeId}
          style={{
            padding: '6px 16px',
            background:
              countryId && markup && !saving && storeId
                ? '#008060'
                : '#babfc3',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor:
              countryId && markup && !saving && storeId
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
    marginBottom: 16,
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
}