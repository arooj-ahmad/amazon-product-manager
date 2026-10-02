// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — har product ka markup change karo
// ============================================

import { useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ============================================
// App Bridge helpers
// ============================================
function getAppBridge() {
  if (typeof window === 'undefined') return null
  if (window.shopify) return window.shopify
  if (window.appBridge) return window.appBridge
  return null
}

async function getIdToken() {
  const bridge = getAppBridge()
  if (!bridge) throw new Error('Shopify App Bridge not loaded')
  const token = await bridge.idToken()
  if (!token) throw new Error('Empty ID token')
  return token
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
// Main Component
// ============================================
export default function MarkupSettings() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [message, setMessage] = useState(null)

  const [bulkMarkup, setBulkMarkup] = useState('2.00')
  const [bulkType, setBulkType] = useState('fixed')
  const [bulkLoading, setBulkLoading] = useState(false)

  // Load products
  useEffect(() => {
    loadProducts()
  }, [])

  const loadProducts = async () => {
    setLoading(true)
    try {
      const res = await safeFetch(`${API_URL}/api/markup/products`)
      if (!res.ok) throw new Error(res.data.detail || 'Failed to load')
      setProducts(res.data || [])
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  // Single update
  const handleUpdate = async (productId, newMarkup, newType) => {
    setSavingId(productId)
    setMessage(null)
    try {
      const res = await safeFetch(
        `${API_URL}/api/markup/${productId}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            markup: parseFloat(newMarkup),
            markup_type: newType,
          }),
        }
      )
      if (!res.ok) throw new Error(res.data.detail || 'Failed')

      setProducts((prev) =>
        prev.map((p) => (p.id === productId ? res.data : p))
      )
      setMessage({ type: 'success', text: '✅ Markup update ho gaya!' })
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setSavingId(null)
    }
  }

  // Bulk update
  const handleBulkUpdate = async () => {
    if (
      !window.confirm(
        `Saare products ka markup ${
          bulkType === 'percent' ? bulkMarkup + '%' : '$' + bulkMarkup
        } kar dein?`
      )
    )
      return

    setBulkLoading(true)
    setMessage(null)
    try {
      const res = await safeFetch(
        `${API_URL}/api/markup/bulk-update`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            markup: parseFloat(bulkMarkup),
            markup_type: bulkType,
          }),
        }
      )
      if (!res.ok) throw new Error(res.data.detail || 'Failed')

      setMessage({
        type: 'success',
        text: `✅ ${res.data.updated} products update ho gaye!`,
      })
      loadProducts()
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setBulkLoading(false)
    }
  }

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
        <h1 style={styles.h1}>⚙️ Markup Settings</h1>
        <p style={styles.subtitle}>
          Har product ka markup apni marzi se set karein. Default $2 hai.
        </p>

        {/* Bulk Update Box */}
        <div style={styles.bulkBox}>
          <strong>🔄 Bulk Update All:</strong>
          <select
            value={bulkType}
            onChange={(e) => setBulkType(e.target.value)}
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
            value={bulkMarkup}
            onChange={(e) => setBulkMarkup(e.target.value)}
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

        {/* Message */}
        {message && (
          <div
            style={{
              ...styles.messageBox,
              background:
                message.type === 'success' ? '#e4f5e4' : '#fbeae5',
              color: message.type === 'success' ? '#008060' : '#d72c0d',
              border: `1px solid ${
                message.type === 'success' ? '#aee9ae' : '#febcb3'
              }`,
            }}
          >
            {message.text}
          </div>
        )}

        {/* Products Table */}
        {products.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#666' }}>
            Koi product nahi mila. Pehle Shopify App se product add karein.
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
                  <th style={styles.th}>Final Price</th>
                  <th style={styles.th}>Action</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <ProductRow
                    key={p.id}
                    product={p}
                    onSave={handleUpdate}
                    saving={savingId === p.id}
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
function ProductRow({ product, onSave, saving }) {
  const [markup, setMarkup] = useState(String(product.markup ?? 2))
  const [type, setType] = useState(product.markup_type || 'fixed')

  const changed =
    parseFloat(markup) !== product.markup || type !== product.markup_type

  // Live preview
  const previewPrice = (() => {
    const m = parseFloat(markup) || 0
    const amazon = product.amazon_price || 0
    if (type === 'percent') {
      return (amazon * (1 + m / 100)).toFixed(2)
    }
    return (amazon + m).toFixed(2)
  })()

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
            {product.title?.slice(0, 60) || 'Untitled'}
          </span>
        </div>
      </td>
      <td style={styles.td}>
        ${(product.amazon_price || 0).toFixed(2)}
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
      <td style={{ ...styles.td, fontWeight: 600 }}>${previewPrice}</td>
      <td style={styles.td}>
        <button
          onClick={() => onSave(product.id, markup, type)}
          disabled={!changed || saving}
          style={{
            padding: '6px 16px',
            background: changed ? '#008060' : '#babfc3',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: changed ? 'pointer' : 'not-allowed',
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
  container: { maxWidth: '1200px', margin: '0 auto' },
  centerBox: { padding: '60px 20px', textAlign: 'center' },
  h1: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#202223',
    marginBottom: '4px',
  },
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
  theadRow: {
    background: '#f6f6f7',
    textAlign: 'left',
  },
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
    width: 80,
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