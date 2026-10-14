// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — DEFAULT MARKUP ONLY
// Sets the store's default markup that applies to
// every new product added to Shopify.
// + ✅ FIXED: Navigation via window.location.hash
//             (Shopify iframe compatible)
// ============================================

import { useState, useEffect } from 'react'
import { getCountries } from '../api/pricing'

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

// ============================================
// ✅ NAYA: Shopify iframe-compatible navigation
// HashRouter ke saath iframe me `navigate()` reliably
// kaam nahi karta, isliye window.location.hash use karo.
// ============================================
function navigateTo(path) {
  const targetHash = `#${path}`
  console.log(`🧭 Navigating to: ${targetHash}`)

  // If already in HashRouter context, just change hash
  if (window.location.hash === targetHash) {
    // Force a re-dispatch
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = targetHash
  }
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

// Format markup for display
function formatMarkup(markup, type, extra) {
  if (type === 'percent') return `+${markup}%`
  if (type === 'both') return `+$${markup} + ${extra}%`
  return `+$${markup}`
}

// ============================================
// Main Component
// ============================================
export default function MarkupSettings() {
  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)
  const [savedDefault, setSavedDefault] = useState(null)

  const [formData, setFormData] = useState({
    country_id: '',
    markup_type: 'fixed',
    markup_value: '',
    extra_percent: '',
    tax_rate: '0',
  })

  const [saving, setSaving] = useState(false)

  useEffect(() => {
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const init = async () => {
    setLoading(true)
    try {
      const domain = getShopDomain()
      if (!domain) {
        throw new Error(
          'Unable to detect store domain. Open this app from Shopify Admin.'
        )
      }
      setShopDomain(domain)

      const countriesData = await getCountries()
      setCountries(countriesData || [])

      // Load saved default markup
      try {
        const defRes = await safeFetch(
          `${API_URL}/api/markup/store-default?shop_domain=${encodeURIComponent(domain)}`
        )
        if (defRes.ok && defRes.data) {
          setSavedDefault(defRes.data)
          setFormData({
            country_id: '',
            markup_type: defRes.data.markup_type || 'fixed',
            markup_value: defRes.data.markup ? String(defRes.data.markup) : '',
            extra_percent: defRes.data.extra_percent
              ? String(defRes.data.extra_percent)
              : '',
            tax_rate: '0',
          })
        }
      } catch (err) {
        console.warn('Could not load saved default markup:', err)
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  const handleCountryChange = (countryId) => {
    const country = countries.find((c) => c.id === parseInt(countryId))
    setFormData({
      ...formData,
      country_id: countryId,
      tax_rate: country ? String(country.default_tax_rate) : '0',
    })
  }

  const handleSaveDefault = async () => {
    if (!formData.markup_value || parseFloat(formData.markup_value) <= 0) {
      setMessage({ type: 'error', text: 'Please enter a markup value.' })
      return
    }

    if (!shopDomain) {
      setMessage({ type: 'error', text: 'Store domain is missing.' })
      return
    }

    const preview = formatMarkup(
      formData.markup_value,
      formData.markup_type,
      formData.extra_percent || 0
    )

    if (
      !window.confirm(
        `Set default markup to ${preview}? This will apply to all new products.`
      )
    ) {
      return
    }

    setSaving(true)
    setMessage(null)

    try {
      const defRes = await safeFetch(
        `${API_URL}/api/markup/store-default`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shop_domain: shopDomain,
            markup: parseFloat(formData.markup_value),
            markup_type: formData.markup_type,
            extra_percent: parseFloat(formData.extra_percent) || 0,
          }),
        }
      )

      if (defRes.ok) {
        setSavedDefault(defRes.data)
        setMessage({
          type: 'success',
          text: 'Default markup saved. It will now apply to every new product.',
        })
      } else {
        throw new Error(defRes.data?.detail || 'Failed to save default markup.')
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setSaving(false)
    }
  }

  // ✅ NAYA: Navigation handlers
  const handleBackToDashboard = () => {
    navigateTo('/shopify-app')
  }

  const handleGoToProducts = () => {
    navigateTo('/products')
  }

  if (loading) {
    return (
      <div style={styles.centerBox}>
        <p style={{ color: '#637381', fontSize: 14 }}>Loading...</p>
      </div>
    )
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

        <h1 style={styles.h1}>Markup Settings</h1>
        <p style={styles.subtitle}>
          Configure the default markup that applies to{' '}
          <strong>every new product</strong> you add.
        </p>

        {/* Current Default Markup Banner */}
        {savedDefault && (
          <div style={styles.defaultBanner}>
            <div style={styles.bannerIcon}>💾</div>
            <div style={styles.bannerContent}>
              <div style={styles.bannerTitle}>Current Default Markup</div>
              <div style={styles.bannerValue}>
                {formatMarkup(
                  savedDefault.markup,
                  savedDefault.markup_type,
                  savedDefault.extra_percent
                )}
              </div>
              <div style={styles.bannerHint}>
                This will apply to all new products added to your store.
              </div>
            </div>
          </div>
        )}

        {/* Set Default Markup Form */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardIconBox}>
              <span style={styles.cardIcon}>💰</span>
            </div>
            <div>
              <h3 style={styles.cardTitle}>Set Default Markup</h3>
              <p style={styles.cardSubtitle}>
                Choose how you want to price new products
              </p>
            </div>
          </div>

          <div style={styles.formRow}>
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Markup Type</label>
              <select
                value={formData.markup_type}
                onChange={(e) =>
                  setFormData({ ...formData, markup_type: e.target.value })
                }
                style={styles.select}
                disabled={saving}
              >
                <option value="fixed">Fixed Amount ($)</option>
                <option value="percent">Percentage (%)</option>
                <option value="both">Fixed + Percentage</option>
              </select>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>
                {formData.markup_type === 'percent'
                  ? 'Percentage (%)'
                  : formData.markup_type === 'both'
                    ? 'Fixed Amount ($)'
                    : 'Amount ($)'}
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.markup_value}
                onChange={(e) =>
                  setFormData({ ...formData, markup_value: e.target.value })
                }
                style={styles.input}
                disabled={saving}
                placeholder={
                  formData.markup_type === 'percent' ? 'e.g. 10' : 'e.g. 5.00'
                }
              />
            </div>

            {formData.markup_type === 'both' && (
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Additional Percentage (%)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="500"
                  value={formData.extra_percent}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      extra_percent: e.target.value,
                    })
                  }
                  style={styles.input}
                  disabled={saving}
                  placeholder="e.g. 10"
                />
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={handleSaveDefault}
            disabled={
              saving ||
              !formData.markup_value ||
              parseFloat(formData.markup_value) <= 0
            }
            style={{
              ...styles.primaryBtn,
              background:
                saving || !formData.markup_value ? '#b5b5b5' : '#008060',
              cursor:
                saving || !formData.markup_value
                  ? 'not-allowed'
                  : 'pointer',
              marginTop: 20,
            }}
          >
            {saving ? 'Saving...' : 'Save as Default'}
          </button>
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

        {/* Info Card — Products Page Link */}
        <div style={styles.infoCard}>
          <div style={styles.infoIconBox}>
            <span style={styles.infoIcon}>📦</span>
          </div>
          <div style={styles.infoContent}>
            <h3 style={styles.infoTitle}>Product-wise Pricing</h3>
            <p style={styles.infoText}>
              To edit existing products or run a bulk update, go to the
              Products page.
            </p>
            <button
              type="button"
              onClick={handleGoToProducts}
              style={styles.infoBtn}
            >
              Go to Products →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================
// Styles
// ============================================
const styles = {
  page: {
    padding: '24px',
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    background: '#f6f6f7',
    minHeight: '100vh',
  },
  container: { maxWidth: '900px', margin: '0 auto' },
  centerBox: { padding: '60px 20px', textAlign: 'center' },

  h1: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#202223',
    marginBottom: '6px',
  },
  subtitle: {
    color: '#637381',
    fontSize: '14px',
    marginBottom: '24px',
    lineHeight: '1.5',
  },

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

  // Banner
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
  bannerIcon: {
    fontSize: '22px',
    lineHeight: 1,
  },
  bannerContent: { flex: 1 },
  bannerTitle: {
    fontSize: '12px',
    fontWeight: '600',
    color: '#166534',
    textTransform: 'uppercase',
    letterSpacing: '0.4px',
    marginBottom: '4px',
  },
  bannerValue: {
    display: 'inline-block',
    fontSize: '16px',
    fontWeight: '700',
    color: '#15803d',
    background: 'white',
    padding: '4px 12px',
    borderRadius: '6px',
    border: '1px solid #86efac',
    marginBottom: '6px',
  },
  bannerHint: {
    fontSize: '12px',
    color: '#65a30d',
  },

  // Card
  card: {
    background: 'white',
    padding: '24px',
    borderRadius: '10px',
    marginBottom: '20px',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '20px',
  },
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
  cardTitle: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 2px 0',
  },
  cardSubtitle: {
    fontSize: '12px',
    color: '#637381',
    margin: 0,
  },

  // Form
  formRow: {
    display: 'flex',
    gap: '16px',
    flexWrap: 'wrap',
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    flex: '1 1 180px',
    minWidth: '160px',
  },
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

  // Messages
  messageBox: {
    padding: '12px 16px',
    borderRadius: '6px',
    fontSize: '13px',
    marginBottom: '20px',
    fontWeight: '500',
  },

  // Info card
  infoCard: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '16px',
    padding: '20px',
    background: 'white',
    border: '1px solid #e1e3e5',
    borderRadius: '10px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
  },
  infoIconBox: {
    width: '48px',
    height: '48px',
    borderRadius: '8px',
    background: '#ede9fe',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  infoIcon: { fontSize: '24px' },
  infoContent: { flex: 1 },
  infoTitle: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 6px 0',
  },
  infoText: {
    fontSize: '13px',
    color: '#637381',
    margin: '0 0 12px 0',
    lineHeight: '1.5',
  },
  infoBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 16px',
    background: '#008060',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
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