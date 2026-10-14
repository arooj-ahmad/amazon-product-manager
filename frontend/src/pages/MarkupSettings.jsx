// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — GLOBAL SETTINGS ONLY
// + Bulk update + store default markup save
// + Products table hata di (wo alag page par hai)
// + Store ID database se aati hai (koi hardcode nahi)
// + "both" markup type — Fixed + Percent
// + useNavigate (sidebar navigation ke liye)
// ============================================

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCountries,
  bulkUpdatePricing,
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
  const [storeId, setStoreId] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)

  // Store ka saved default markup
  const [savedDefault, setSavedDefault] = useState(null)

  const [bulkData, setBulkData] = useState({
    country_id: '',
    markup_type: 'fixed',
    markup_value: '',
    extra_percent: '',
    tax_rate: '0',
  })
  const [bulkLoading, setBulkLoading] = useState(false)

  // Save as default toggle
  const [saveAsDefault, setSaveAsDefault] = useState(true)

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

      const sid = await getStoreIdByDomain(domain)
      console.log(`✅ Store ID from database: ${sid}`)
      setStoreId(sid)

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
    if (!bulkData.markup_value || parseFloat(bulkData.markup_value) <= 0) {
      setMessage({ type: 'error', text: '❌ Please enter a markup value' })
      return
    }
    if (!storeId) {
      setMessage({ type: 'error', text: '❌ Store ID detect nahi ho saka' })
      return
    }

    if (!window.confirm('Saare products par yeh pricing apply karein?')) return

    setBulkLoading(true)
    setMessage(null)
    try {
      // 1️⃣ Bulk update existing products
      const res = await bulkUpdatePricing({
        store_id: storeId,
        markup_type: bulkData.markup_type,
        markup_value: parseFloat(bulkData.markup_value),
        extra_percent: parseFloat(bulkData.extra_percent) || 0,
        tax_rate: parseFloat(bulkData.tax_rate),
      })

      // 2️⃣ Store default bhi save karo (agar checkbox checked hai)
      let defaultSaved = false
      if (saveAsDefault && shopDomain) {
        try {
          const defRes = await safeFetch(
            `${API_URL}/api/markup/store-default`,
            {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                shop_domain: shopDomain,
                markup: parseFloat(bulkData.markup_value),
                markup_type: bulkData.markup_type,
                extra_percent: parseFloat(bulkData.extra_percent) || 0,
              }),
            }
          )

          if (defRes.ok) {
            defaultSaved = true
            setSavedDefault(defRes.data)
            console.log('✅ Store default markup saved:', defRes.data)
          } else {
            console.warn('⚠️ Store default save failed:', defRes.data)
            setMessage({
              type: 'error',
              text: `⚠️ Default markup save nahi hua: ${defRes.data?.detail || 'Unknown error'}`,
            })
          }
        } catch (err) {
          console.warn('⚠️ Store default save error:', err)
          setMessage({
            type: 'error',
            text: `⚠️ Default markup save error: ${err.message}`,
          })
        }
      }

      setMessage({
        type: 'success',
        text: `✅ ${res.updated} products update ho gaye! (Shopify: ${res.shopify_updated || 0})${defaultSaved ? ' + Default markup saved ✅' : ''}`,
      })
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
          Yahan jo markup set karenge, wo <strong>naye products par bhi
          automatically apply</strong> hoga.
        </p>

        {/* Saved default markup info */}
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

        {!storeId && (
          <div
            style={{
              ...styles.messageBox,
              background: '#fef3e7',
              color: '#b54708',
              border: '1px solid #fedf89',
            }}
          >
            ⚠️ Store ID detect nahi ho saka. URL mein <code>?shop=</code> ya{' '}
            <code>/store/...</code> hona chahiye.
          </div>
        )}

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
                setBulkData({ ...bulkData, extra_percent: e.target.value })
              }
              style={styles.bulkInput}
              disabled={bulkLoading}
              placeholder="e.g. 10"
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

          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={saveAsDefault}
              onChange={(e) => setSaveAsDefault(e.target.checked)}
              disabled={bulkLoading}
              style={styles.checkbox}
            />
            <span>Save as store default</span>
          </label>

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

        {/* ✅ Info card — Products page ka link */}
        <div style={styles.infoCard}>
          <div style={styles.infoIconBox}>
            <span style={styles.infoIcon}>📦</span>
          </div>
          <div style={styles.infoContent}>
            <h3 style={styles.infoTitle}>Product-wise Pricing</h3>
            <p style={styles.infoText}>
              Har product ka markup, tax alag set karne ke liye{' '}
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

  bulkBox: {
    background: 'white',
    padding: 20,
    borderRadius: 8,
    marginBottom: 20,
    display: 'flex',
    gap: 12,
    alignItems: 'center',
    flexWrap: 'wrap',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
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

  checkboxLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: 13,
    color: '#202223',
    cursor: 'pointer',
    padding: '8px 12px',
    background: '#f6f6f7',
    border: '1px solid #babfc3',
    borderRadius: 6,
    userSelect: 'none',
  },
  checkbox: {
    cursor: 'pointer',
    width: 16,
    height: 16,
  },

  messageBox: {
    padding: '12px 16px',
    borderRadius: 6,
    fontSize: 14,
    marginBottom: 16,
  },

  // ✅ Info card — Products page link
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
    padding: '10px 20px',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: '600',
  },
}