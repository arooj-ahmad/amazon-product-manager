// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — Country + Tax support
// + ✅ NAYA: Store ID support (multi-store)
// ============================================

import { useState, useEffect } from 'react'
import { getCountries, updatePricing, bulkUpdatePricing } from '../api/pricing'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ============================================
// ✅ NAYA: Store ID nikaalo (Shopify iframe se)
// ============================================
function getStoreIdFromUrl() {
  // Shopify iframe se "shop" parameter nikaalo
  const params = new URLSearchParams(window.location.search)
  const shop = params.get('shop') // "test-store-ispfraip.myshopify.com"
  
  if (!shop) return null
  
  // Store domain se store ID ka mapping (aap isay API se bhi le sakti hain)
  // Filhal hardcoded mapping — behtar hai API se lein
  const storeMap = {
    'amazon-product-manager.myshopify.com': 13,
    'stock-sync-test-store-hvmaovlm.myshopify.com': 14,
    'test-store-ispfraip.myshopify.com': 15,
  }
  
  return storeMap[shop] || null
}

// ============================================
// Helpers
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
export default function MarkupSettings() {
  const [products, setProducts] = useState([])
  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [message, setMessage] = useState(null)
  const [storeId, setStoreId] = useState(null)  // ✅ NAYA

  const [bulkData, setBulkData] = useState({
    country_id: '',
    markup_type: 'fixed',
    markup_value: '2.00',
    tax_rate: '0',
  })
  const [bulkLoading, setBulkLoading] = useState(false)

  useEffect(() => {
    // ✅ Store ID nikaalo
    const sid = getStoreIdFromUrl()
    setStoreId(sid)
    loadAll(sid)
  }, [])

  const loadAll = async (sid) => {
    setLoading(true)
    try {
      const countriesData = await getCountries()
      setCountries(countriesData || [])

      // ✅ NAYA: store_id ke saath products fetch karo
      let url = `${API_URL}/api/markup/products`
      if (sid) {
        url += `?store_id=${sid}`
      }
      
      const productsRes = await safeFetch(url)
      if (!productsRes.ok) throw new Error(productsRes.data.detail || 'Failed to load products')
      setProducts(productsRes.data || [])
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  const handleBulkCountryChange = (countryId) => {
    const country = countries.find((c) => c.id === parseInt(countryId))
    setBulkData({
      ...bulkData,
      country_id: countryId,
      tax_rate: country ? String(country.default_tax_rate) : '0',
    })
  }

  const handleBulkUpdate = async () => {
    if (!bulkData.country_id) {
      setMessage({ type: 'error', text: '❌ Please select a country' })
      return
    }

    if (!window.confirm('Saare products par yeh pricing apply karein?')) return

    setBulkLoading(true)
    setMessage(null)
    try {
      const res = await bulkUpdatePricing({
        country_id: parseInt(bulkData.country_id),
        markup_type: bulkData.markup_type,
        markup_value: parseFloat(bulkData.markup_value),
        tax_rate: parseFloat(bulkData.tax_rate),
      })
      setMessage({ type: 'success', text: `✅ ${res.updated} products update ho gaye!` })
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setBulkLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={styles.centerBox}>
        <p style={{ color: '#637381' }}>⏳ Loading...</p>
      </div>
    )
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.h1}>⚙️ Markup Settings</h1>
        <p style={styles.subtitle}>
          Har product ka markup, country aur tax set karein. Default $2 hai.
        </p>

        {/* Bulk Update Box */}
        <div style={styles.bulkBox}>
          <strong>🔄 Bulk Update All:</strong>

          <select
            value={bulkData.country_id}
            onChange={(e) => handleBulkCountryChange(e.target.value)}
            style={styles.bulkSelect}
            disabled={bulkLoading}
          >
            <option value="">Select Country</option>
            {countries.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.default_tax_rate}% {c.tax_label})
              </option>
            ))}
          </select>

          <select
            value={bulkData.markup_type}
            onChange={(e) => setBulkData({ ...bulkData, markup_type: e.target.value })}
            style={styles.bulkSelect}
            disabled={bulkLoading}
          >
            <option value="fixed">$ Fixed</option>
            <option value="percent">% Percent</option>
          </select>

          <input
            type="number"
            step="0.01"
            min="0"
            value={bulkData.markup_value}
            onChange={(e) => setBulkData({ ...bulkData, markup_value: e.target.value })}
            style={styles.bulkInput}
            disabled={bulkLoading}
          />

          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            placeholder="Tax %"
            value={bulkData.tax_rate}
            onChange={(e) => setBulkData({ ...bulkData, tax_rate: e.target.value })}
            style={styles.bulkInput}
            disabled={bulkLoading}
          />

          <button
            onClick={handleBulkUpdate}
            disabled={bulkLoading}
            style={{
              ...styles.primaryBtn,
              background: bulkLoading ? '#babfc3' : '#008060',
              cursor: bulkLoading ? 'not-allowed' : 'pointer',
            }}
          >
            {bulkLoading ? '⏳ Applying...' : 'Apply to All'}
          </button>
        </div>

        {message && (
          <div
            style={{
              ...styles.messageBox,
              background: message.type === 'success' ? '#e4f5e4' : '#fbeae5',
              color: message.type === 'success' ? '#008060' : '#d72c0d',
              border: `1px solid ${message.type === 'success' ? '#aee9ae' : '#febcb3'}`,
            }}
          >
            {message.text}
          </div>
        )}

        {products.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#666' }}>
            Koi product nahi mila.
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
                  <th style={styles.th}>Tax %</th>
                  <th style={styles.th}>Tax Amt</th>
                  <th style={styles.th}>Final Price</th>
                  <th style={styles.th}>Action</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <ProductRow
                    key={p.id}
                    product={p}
                    countries={countries}
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
// Product Row (Same as before)
// ============================================
function ProductRow({ product, countries, saving, onSaveStart, onSaveEnd, onMessage }) {
  const [countryId, setCountryId] = useState('')
  const [markup, setMarkup] = useState(String(product.markup ?? 2))
  const [type, setType] = useState(product.markup_type || 'fixed')
  const [taxRate, setTaxRate] = useState('0')

  const selectedCountry = countries.find((c) => c.id === parseInt(countryId))

  const calc = (() => {
    const amazon = parseFloat(product.amazon_price) || 0
    const m = parseFloat(markup) || 0
    const tax = parseFloat(taxRate) || 0

    let subtotal
    if (type === 'percent') {
      subtotal = amazon * (1 + m / 100)
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

    onSaveStart()
    onMessage(null)
    try {
      await updatePricing({
        product_id: product.id,
        country_id: parseInt(countryId),
        markup_type: type,
        markup_value: parseFloat(markup),
        tax_rate: parseFloat(taxRate),
      })
      onMessage({ type: 'success', text: '✅ Pricing save ho gayi!' })
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
              style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 4 }}
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
            <option key={c.id} value={c.id}>{c.name}</option>
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
          onClick={handleSave}
          disabled={!countryId || saving}
          style={{
            padding: '6px 16px',
            background: countryId && !saving ? '#008060' : '#babfc3',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: countryId && !saving ? 'pointer' : 'not-allowed',
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
  h1: { fontSize: '24px', fontWeight: '700', color: '#202223', marginBottom: '4px' },
  subtitle: { color: '#637381', fontSize: '14px', marginBottom: '20px' },

  bulkBox: {
    background: '#f6f6f7',
    padding: 16,
    borderRadius: 8,
    marginBottom: 20,
    display: 'flex',
    gap: 12,
    alignItems: 'center',
    flexWrap: 'wrap',
    border: '1px solid #e1e3e5',
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
  td: { padding: 12, fontSize: 13, color: '#202223', verticalAlign: 'middle' },
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
    fontWeight: 600,
  },
}