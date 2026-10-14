// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — DEFAULT MARKUP ONLY
// Ye page sirf store ka default markup set karta hai
// jo har naye product par apply hoga.
// Bulk update + products table → Products page par hain.
// ============================================

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCountries, getStoreIdByDomain } from '../api/pricing'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ============================================
// Shop domain nikaalo
// ============================================
function getShopDomain() {
  const params = new URLSearchParams(window.location.search)
  const shop = params.get('shop')
  if (shop) {
    console.log(`✅ Shop domain from ?shop=: ${shop}`)
    return shop
  }

  const pathMatch = window.location.pathname.match(/\/store\/([^/]+)/)
  if (pathMatch) {
    const storeName = pathMatch[1]
    const shopDomain = `${storeName}.myshopify.com`
    console.log(`✅ Shop domain from admin URL: ${shopDomain}`)
    return shopDomain
  }

  console.warn('⚠️ Shop domain detect nahi ho saka')
  return null
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

// ============================================
// Main Component
// ============================================
export default function MarkupSettings() {
  const navigate = useNavigate()

  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)

  // Store ka saved default markup
  const [savedDefault, setSavedDefault] = useState(null)

  // Form data
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
          'Shop domain detect nahi ho saka. URL mein ?shop= ya /store/... hona chahiye.'
        )
      }
      setShopDomain(domain)

      // Sirf countries load karo (store ID ki zaroorat nahi — save me shop_domain se hoga)
      const countriesData = await getCountries()
      setCountries(countriesData || [])

      // Store ka saved default markup load karo
      try {
        const defRes = await safeFetch(
          `${API_URL}/api/markup/store-default?shop_domain=${encodeURIComponent(domain)}`
        )
        if (defRes.ok && defRes.data) {
          setSavedDefault(defRes.data)
          console.log('✅ Saved default markup:', defRes.data)

          // Form me current values prefill karo
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
        console.warn('⚠️ Could not load saved default:', err)
      }
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
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
    // Validation
    if (!formData.markup_value || parseFloat(formData.markup_value) <= 0) {
      setMessage({
        type: 'error',
        text: '❌ Please enter a markup value',
      })
      return
    }

    if (!shopDomain) {
      setMessage({ type: 'error', text: '❌ Shop domain missing' })
      return
    }

    if (
      !window.confirm(
        `Default markup set karein: ${
          formData.markup_type === 'percent'
            ? `+${formData.markup_value}%`
            : formData.markup_type === 'both'
              ? `+$${formData.markup_value} + ${formData.extra_percent || 0}%`
              : `+$${formData.markup_value}`
        }? Ye har naye product par apply hoga.`
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
          text: '✅ Default markup save ho gaya! Ab har naya product par apply hoga.',
        })
        console.log('✅ Store default markup saved:', defRes.data)
      } else {
        throw new Error(defRes.data?.detail || 'Save failed')
      }
    } catch (err) {
      setMessage({ type: 'error', text: `❌ ${err.message}` })
    } finally {
      setSaving(false)
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
        <button
          type="button"
          onClick={() => navigate('/shopify-app')}
          style={styles.backBtn}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#f6f6f7'
            e.currentTarget.style.transform = 'translateX(-2px)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'white'
            e.currentTarget.style.transform = 'translateX(0)'
          }}
        >
          ← Back to Dashboard
        </button>

        <h1 style={styles.h1}>⚙️ Markup Settings</h1>
        <p style={styles.subtitle}>
          Yahan jo markup set karenge, wo{' '}
          <strong>har naye product par automatically apply</strong> hoga.
        </p>

        {/* Current default markup banner */}
        {savedDefault && (
          <div style={styles.defaultBanner}>
            <span style={styles.defaultIcon}>💾</span>
            <div>
              <strong style={styles.defaultTitle}>
                Current Default Markup:
              </strong>{' '}
              <span style={styles.defaultValue}>
                {savedDefault.markup_type === 'percent'
                  ? `+${savedDefault.markup}%`
                  : savedDefault.markup_type === 'both'
                    ? `+$${savedDefault.markup} + ${savedDefault.extra_percent}%`
                    : `+$${savedDefault.markup}`}
              </span>
              <p style={styles.defaultHint}>
                Ye markup har naye product par apply hoga.
              </p>
            </div>
          </div>
        )}

        {/* Default Markup Form */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.cardIcon}>💰</span>
            <div>
              <h3 style={styles.cardTitle}>Set Default Markup</h3>
              <p style={styles.cardSubtitle}>
                Ye markup har naye product par apply hoga
              </p>
            </div>
          </div>

          <div style={styles.formRow}>
            <select
              value={formData.country_id}
              onChange={(e) => handleCountryChange(e.target.value)}
              style={styles.input}
              disabled={saving}
            >
              <option value="">Country (optional)</option>
              {countries.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.default_tax_rate}% {c.tax_label})
                </option>
              ))}
            </select>

            <select
              value={formData.markup_type}
              onChange={(e) =>
                setFormData({ ...formData, markup_type: e.target.value })
              }
              style={styles.input}
              disabled={saving}
            >
              <option value="fixed">$ Fixed</option>
              <option value="percent">% Percent</option>
              <option value="both">$ + % (Both)</option>
            </select>

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
                formData.markup_type === 'percent'
                  ? 'e.g. 10'
                  : 'e.g. 2.00'
              }
            />

            {formData.markup_type === 'both' && (
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
                placeholder="Extra %"
              />
            )}
          </div>

          <button
            type="button"
            onClick={handleSaveDefault}
            disabled={
              saving || !formData.markup_value || parseFloat(formData.markup_value) <= 0
            }
            style={{
              ...styles.primaryBtn,
              background:
                saving || !formData.markup_value
                  ? '#babfc3'
                  : '#008060',
              cursor:
                saving || !formData.markup_value
                  ? 'not-allowed'
                  : 'pointer',
              marginTop: 16,
            }}
          >
            {saving ? '⏳ Saving...' : '💾 Save as Default'}
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

        {/* Info card — Products page ka link */}
        <div style={styles.infoCard}>
          <div style={styles.infoIconBox}>
            <span style={styles.infoIcon}>📦</span>
          </div>
          <div style={styles.infoContent}>
            <h3 style={styles.infoTitle}>Product-wise Pricing</h3>
            <p style={styles.infoText}>
              Existing products ka markup change karne ke liye, ya{' '}
              <strong>Bulk Update</strong> karne ke liye{' '}
              <strong>Products</strong> page par jaayein.
            </p>
            <button
              type="button"
              onClick={() => navigate('/products')}
              style={styles.infoBtn}
            >
              📦 Go to Products →
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
  subtitle: { color: '#637381', fontSize: '14px', marginBottom: '20px' },

  defaultBanner: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    padding: '14px 18px',
    marginBottom: '20px',
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: '8px',
  },
  defaultIcon: {
    fontSize: '20px',
    flexShrink: 0,
  },
  defaultTitle: {
    color: '#166534',
    fontSize: '13px',
  },
  defaultValue: {
    color: '#15803d',
    fontSize: '14px',
    fontWeight: '700',
    background: 'white',
    padding: '2px 10px',
    borderRadius: '4px',
    border: '1px solid #86efac',
    marginLeft: '4px',
  },
  defaultHint: {
    color: '#65a30d',
    fontSize: '12px',
    margin: '4px 0 0 0',
  },

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
    transition: 'all 0.15s ease',
  },

  // ✅ Card styles
  card: {
    background: 'white',
    padding: 24,
    borderRadius: 8,
    marginBottom: 20,
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: 16,
  },
  cardIcon: {
    fontSize: '24px',
  },
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

  formRow: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  input: {
    padding: '10px 12px',
    border: '1px solid #babfc3',
    borderRadius: 6,
    fontSize: 14,
    background: 'white',
    minWidth: 100,
  },

  messageBox: {
    padding: '12px 16px',
    borderRadius: 6,
    fontSize: 14,
    marginBottom: 16,
  },

  infoCard: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '16px',
    padding: '20px',
    background: 'white',
    border: '1px solid #e1e3e5',
    borderRadius: 8,
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  },
  infoIconBox: {
    width: '48px',
    height: '48px',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  infoIcon: {
    fontSize: '24px',
  },
  infoContent: {
    flex: 1,
  },
  infoTitle: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 4px 0',
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
    borderRadius: 6,
    fontSize: 14,
    fontWeight: '600',
  },
}