// frontend/src/pages/ComparePriceSettings.jsx
// Compare Price Settings Page — DEFAULT COMPARE PRICE RULE
// + ✅ NEW: User sets compare price rule once, applies to all new products
// + ✅ NEW: Options: None / Fixed / Percent / Amazon Price
// + ✅ FIXED: Navigation via window.location.hash
// + ✅ FIXED: Circle spinner loader

import { useState, useEffect } from 'react'
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
  if (pathMatch) return `${pathMatch[1]}.myshopify.com`

  return null
}

function navigateTo(path) {
  const targetHash = `#${path}`
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

// ============================================
// Main Component
// ============================================
export default function ComparePriceSettings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)
  const [savedRule, setSavedRule] = useState(null)

  // Compare price rule options:
  //   none     → do not set compare_at_price at all
  //   amazon   → set compare price = amazon price (default Shopify behavior)
  //   fixed    → set compare price = final_price + fixed amount
  //   percent  → set compare price = final_price * (1 + percent/100)
  const [formData, setFormData] = useState({
    rule_type: 'amazon',
    fixed_amount: '',
    percent: '',
  })

  useEffect(() => {
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const init = async () => {
    setLoading(true)
    try {
      const domain = getShopDomain()
      if (!domain) {
        throw new Error('Unable to detect store domain. Open this app from Shopify Admin.')
      }
      setShopDomain(domain)

      // Load saved compare price rule
      try {
        const res = await safeFetch(
          `${API_URL}/api/markup/store-compare-price?shop_domain=${encodeURIComponent(domain)}`
        )
        if (res.ok && res.data) {
          setSavedRule(res.data)
          setFormData({
            rule_type: res.data.rule_type || 'amazon',
            fixed_amount: res.data.fixed_amount ? String(res.data.fixed_amount) : '',
            percent: res.data.percent ? String(res.data.percent) : '',
          })
        }
      } catch (err) {
        console.warn('Could not load saved compare price rule:', err)
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!shopDomain) {
      setMessage({ type: 'error', text: 'Store domain is missing.' })
      return
    }

    // Validation
    if (formData.rule_type === 'fixed' && (!formData.fixed_amount || parseFloat(formData.fixed_amount) <= 0)) {
      setMessage({ type: 'error', text: 'Please enter a valid fixed amount.' })
      return
    }
    if (formData.rule_type === 'percent' && (!formData.percent || parseFloat(formData.percent) <= 0)) {
      setMessage({ type: 'error', text: 'Please enter a valid percentage.' })
      return
    }

    if (!window.confirm('Save this compare price rule? It will apply to all new products.')) return

    setSaving(true)
    setMessage(null)
    try {
      const res = await safeFetch(
        `${API_URL}/api/markup/store-compare-price`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shop_domain: shopDomain,
            rule_type: formData.rule_type,
            fixed_amount: parseFloat(formData.fixed_amount) || 0,
            percent: parseFloat(formData.percent) || 0,
          }),
        }
      )

      if (res.ok) {
        setSavedRule(res.data)
        setMessage({
          type: 'success',
          text: 'Compare price rule saved. It will now apply to every new product.',
        })
      } else {
        throw new Error(res.data?.detail || 'Failed to save compare price rule.')
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setSaving(false)
    }
  }

  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  if (loading) {
    return <Loader text="Loading compare price settings..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <button type="button" onClick={handleBackToDashboard} style={styles.backBtn}>
          ← Back to Dashboard
        </button>

        <h1 style={styles.h1}>Compare Price Settings</h1>
        <p style={styles.subtitle}>
          Set the default compare-at price rule. It will apply to{' '}
          <strong>every new product</strong> you add.
        </p>

        {/* Current Rule Banner */}
        {savedRule && (
          <div style={styles.defaultBanner}>
            <div style={styles.bannerIcon}>💾</div>
            <div style={styles.bannerContent}>
              <div style={styles.bannerTitle}>Current Rule</div>
              <div style={styles.bannerRow}>
                <span style={styles.bannerLabel}>Type:</span>
                <span style={styles.bannerValue}>{getRuleLabel(savedRule.rule_type)}</span>
              </div>
              {savedRule.rule_type === 'fixed' && (
                <div style={styles.bannerRow}>
                  <span style={styles.bannerLabel}>Amount:</span>
                  <span style={styles.bannerValue}>+${savedRule.fixed_amount}</span>
                </div>
              )}
              {savedRule.rule_type === 'percent' && (
                <div style={styles.bannerRow}>
                  <span style={styles.bannerLabel}>Percent:</span>
                  <span style={styles.bannerValue}>+{savedRule.percent}%</span>
                </div>
              )}
              <div style={styles.bannerHint}>
                This rule will be applied to all new products added to your store.
              </div>
            </div>
          </div>
        )}

        {/* Form */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardIconBox}>
              <span style={styles.cardIcon}>🏷️</span>
            </div>
            <div>
              <h3 style={styles.cardTitle}>Set Compare Price Rule</h3>
              <p style={styles.cardSubtitle}>
                How should the compare-at price be calculated?
              </p>
            </div>
          </div>

          {/* Rule Type */}
          <div style={styles.fieldGroup}>
            <label style={styles.label}>Rule Type</label>
            <select
              value={formData.rule_type}
              onChange={(e) => setFormData({ ...formData, rule_type: e.target.value })}
              style={styles.select}
              disabled={saving}
            >
              <option value="amazon">Amazon Price (default)</option>
              <option value="none">Do Not Set Compare Price</option>
              <option value="fixed">Fixed Amount Above Final Price</option>
              <option value="percent">Percentage Above Final Price</option>
            </select>
          </div>

          {/* Fixed Amount */}
          {formData.rule_type === 'fixed' && (
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Fixed Amount ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.fixed_amount}
                onChange={(e) => setFormData({ ...formData, fixed_amount: e.target.value })}
                style={styles.input}
                disabled={saving}
                placeholder="e.g. 10.00"
              />
            </div>
          )}

          {/* Percent */}
          {formData.rule_type === 'percent' && (
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Percentage (%)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="500"
                value={formData.percent}
                onChange={(e) => setFormData({ ...formData, percent: e.target.value })}
                style={styles.input}
                disabled={saving}
                placeholder="e.g. 20"
              />
            </div>
          )}

          {/* Preview */}
          <div style={styles.previewBox}>
            <div style={styles.previewLabel}>Example</div>
            <div style={styles.previewText}>
              If final price is <strong>$100</strong>, compare price will be:{' '}
              <strong>{getPreview(formData)}</strong>
            </div>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            style={{
              ...styles.primaryBtn,
              background: saving ? '#b5b5b5' : '#008060',
              cursor: saving ? 'not-allowed' : 'pointer',
              marginTop: 20,
            }}
          >
            {saving ? 'Saving...' : 'Save Compare Price Rule'}
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
      </div>
    </div>
  )
}

// ============================================
// Helpers
// ============================================
function getRuleLabel(type) {
  switch (type) {
    case 'amazon': return 'Amazon Price (default)'
    case 'none': return 'Do Not Set Compare Price'
    case 'fixed': return 'Fixed Amount Above Final Price'
    case 'percent': return 'Percentage Above Final Price'
    default: return 'Amazon Price (default)'
  }
}

function getPreview(formData) {
  const base = 100
  switch (formData.rule_type) {
    case 'none':
      return 'not set'
    case 'fixed':
      return `$${(base + (parseFloat(formData.fixed_amount) || 0)).toFixed(2)}`
    case 'percent':
      return `$${(base * (1 + (parseFloat(formData.percent) || 0) / 100)).toFixed(2)}`
    case 'amazon':
    default:
      return 'Amazon price (unchanged)'
  }
}

// ============================================
// Styles
// ============================================
const styles = {
  page: {
    padding: '24px',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    background: '#f6f6f7',
    minHeight: '100vh',
  },
  container: { maxWidth: '900px', margin: '0 auto' },
  h1: { fontSize: '24px', fontWeight: '700', color: '#202223', marginBottom: '6px' },
  subtitle: { color: '#637381', fontSize: '14px', marginBottom: '24px', lineHeight: '1.5' },
  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 16px',
    marginBottom: '20px',
    background: 'white',
    color: '#202223',
    border: '1px solid #e1e3e5',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
  },
  defaultBanner: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '14px',
    padding: '16px 20px',
    marginBottom: '20px',
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: '10px',
  },
  bannerIcon: { fontSize: '22px', lineHeight: 1 },
  bannerContent: { flex: 1 },
  bannerTitle: {
    fontSize: '12px',
    fontWeight: '600',
    color: '#166534',
    textTransform: 'uppercase',
    letterSpacing: '0.4px',
    marginBottom: '8px',
  },
  bannerRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '4px',
    fontSize: '13px',
  },
  bannerLabel: { color: '#166534', fontWeight: '600', minWidth: '70px' },
  bannerValue: {
    display: 'inline-block',
    fontSize: '14px',
    fontWeight: '700',
    color: '#15803d',
    background: 'white',
    padding: '2px 10px',
    borderRadius: '6px',
    border: '1px solid #86efac',
  },
  bannerHint: { fontSize: '12px', color: '#65a30d', marginTop: '8px' },
  card: {
    background: 'white',
    padding: '24px',
    borderRadius: '10px',
    marginBottom: '20px',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
  },
  cardHeader: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' },
  cardIconBox: {
    width: '40px',
    height: '40px',
    borderRadius: '8px',
    background: '#fff7ed',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  cardIcon: { fontSize: '20px' },
  cardTitle: { fontSize: '15px', fontWeight: '700', color: '#202223', margin: '0 0 2px 0' },
  cardSubtitle: { fontSize: '12px', color: '#637381', margin: 0 },
  fieldGroup: { display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '16px' },
  label: {
    fontSize: '12px',
    fontWeight: '600',
    color: '#637381',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  select: {
    padding: '10px 12px',
    border: '1px solid #babfc3',
    borderRadius: '6px',
    fontSize: '14px',
    background: 'white',
    color: '#202223',
    outline: 'none',
  },
  input: {
    padding: '10px 12px',
    border: '1px solid #babfc3',
    borderRadius: '6px',
    fontSize: '14px',
    background: 'white',
    color: '#202223',
    outline: 'none',
  },
  previewBox: {
    padding: '12px 16px',
    background: '#f6f6f7',
    borderRadius: '6px',
    border: '1px solid #e1e3e5',
    marginTop: '8px',
  },
  previewLabel: {
    fontSize: '11px',
    fontWeight: '600',
    color: '#637381',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
    marginBottom: '4px',
  },
  previewText: { fontSize: '13px', color: '#202223' },
  messageBox: {
    padding: '12px 16px',
    borderRadius: '6px',
    fontSize: '13px',
    marginBottom: '20px',
    fontWeight: '500',
  },
  primaryBtn: {
    color: 'white',
    border: 'none',
    padding: '12px 24px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
  },
}