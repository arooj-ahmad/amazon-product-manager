// ============================================
// frontend/src/pages/MarkupSettings.jsx
// Markup Settings Page — Professional UI
// + ✅ FIXED: both mode requires extra_percent
// + ✅ FIXED: stale extra_percent cleared on type switch
// + ✅ FIXED: safe parseFloat (NaN protection)
// + ✅ FIXED: validation runs on disabled/enabled state
// + ✅ FIXED: tax_rate clamped 0–100
// + ✅ FIXED: formatMarkup handles undefined
// + ✅ FIXED: Replaced window.confirm() with Custom Modal
// ============================================

import { useState, useEffect } from 'react'
import Loader from '../components/Loader'

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app'

// ============================================
// Helpers
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
    try {
      data = await res.json()
    } catch {
      data = null
    }
  } else {
    const text = await res.text()
    data = { detail: text || `HTTP ${res.status}` }
  }
  return { ok: res.ok, status: res.status, data }
}

// ✅ Safe number parse
function safeNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function formatMarkup(markup, type, extra) {
  const m = safeNumber(markup)
  const e = safeNumber(extra)

  if (m === null) return '—'

  if (type === 'percent') return `+${m}%`
  if (type === 'both') return `+$${m} + ${e ?? 0}%`
  return `+$${m}`
}

// ============================================
// Main Component
// ============================================
export default function MarkupSettings() {
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [shopDomain, setShopDomain] = useState(null)
  const [savedDefault, setSavedDefault] = useState(null)
  const [saving, setSaving] = useState(false)

  // ✅ Modal State
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [pendingPreview, setPendingPreview] = useState('')

  const [formData, setFormData] = useState({
    markup_type: 'fixed',
    markup_value: '',
    extra_percent: '',
    tax_rate: '0',
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
        throw new Error(
          'Unable to detect store domain. Open this app from Shopify Admin.'
        )
      }
      setShopDomain(domain)

      try {
        const defRes = await safeFetch(
          `${API_URL}/api/markup/store-default?shop_domain=${encodeURIComponent(domain)}`
        )
        if (defRes.ok && defRes.data) {
          setSavedDefault(defRes.data)
          setFormData({
            markup_type: defRes.data.markup_type || 'fixed',
            markup_value: defRes.data.markup
              ? String(defRes.data.markup)
              : '',
            extra_percent: defRes.data.extra_percent
              ? String(defRes.data.extra_percent)
              : '',
            tax_rate: defRes.data.tax_rate
              ? String(defRes.data.tax_rate)
              : '0',
          })
        } else if (!defRes.ok && defRes.status !== 404) {
          console.warn('Could not load saved default markup:', defRes.data)
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

  // ✅ Type change — stale extra_percent clear if switching away from "both"
  const handleTypeChange = (newType) => {
    setFormData((prev) => ({
      ...prev,
      markup_type: newType,
      extra_percent: newType === 'both' ? prev.extra_percent : '',
    }))
  }

  // ✅ Validation for current form
  const validateForm = () => {
    const markupVal = safeNumber(formData.markup_value)
    if (markupVal === null || markupVal <= 0) {
      return 'Please enter a valid markup value (greater than 0).'
    }
    if (
      formData.markup_type === 'both' &&
      safeNumber(formData.extra_percent) === null
    ) {
      return 'Additional percentage is required for "Fixed + Percentage" markup.'
    }
    const taxVal = safeNumber(formData.tax_rate)
    if (taxVal !== null && (taxVal < 0 || taxVal > 100)) {
      return 'Tax rate must be between 0 and 100.'
    }
    return null
  }

  // ✅ Step 1: Validate and show custom modal
  const handleSaveClick = () => {
    const validationError = validateForm()
    if (validationError) {
      setMessage({ type: 'error', text: validationError })
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
    
    setPendingPreview(preview)
    setShowConfirmModal(true)
  }

  // ✅ Step 2: Actual Save Function (Modal Confirm ke baad)
  const performSave = async () => {
    setShowConfirmModal(false)
    setSaving(true)
    setMessage(null)

    const markupVal = safeNumber(formData.markup_value)
    const extraVal = safeNumber(formData.extra_percent) ?? 0
    const taxVal = safeNumber(formData.tax_rate) ?? 0

    try {
      const defRes = await safeFetch(
        `${API_URL}/api/markup/store-default`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shop_domain: shopDomain,
            markup: markupVal,
            markup_type: formData.markup_type,
            extra_percent: extraVal,
            country_id: null,
            tax_rate: taxVal,
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
        throw new Error(
          defRes.data?.detail || 'Failed to save default markup.'
        )
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setSaving(false)
    }
  }

  // ✅ Save disabled when invalid
  const saveDisabled = saving || validateForm() !== null

  if (loading) {
    return <Loader text="Loading markup settings..." />
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Header Navigation */}
        <div style={styles.headerNav}>
          <button
            type="button"
            onClick={() => navigateTo('/shopify-app')}
            style={styles.backBtn}
          >
            ← Back to Dashboard
          </button>
        </div>

        <div style={styles.pageHeader}>
          <h1 style={styles.h1}>Markup Settings</h1>
          <p style={styles.subtitle}>
            Configure the default markup and tax that applies to{' '}
            <strong>every new product</strong> you add.
          </p>
        </div>

        {/* Current Default Banner */}
        {savedDefault && (
          <div style={styles.defaultBanner}>
            <div style={styles.bannerIconBox}>
              <span style={styles.bannerIcon}>💾</span>
            </div>
            <div style={styles.bannerContent}>
              <div style={styles.bannerTitle}>CURRENT DEFAULTS</div>
              <div style={styles.bannerGrid}>
                <div style={styles.bannerItem}>
                  <span style={styles.bannerLabel}>Markup:</span>
                  <span style={styles.bannerValue}>
                    {formatMarkup(
                      savedDefault.markup,
                      savedDefault.markup_type,
                      savedDefault.extra_percent
                    )}
                  </span>
                </div>

                <div style={styles.bannerItem}>
                  <span style={styles.bannerLabel}>Tax:</span>
                  <span style={styles.bannerValue}>
                    {savedDefault.tax_rate || 0}%
                  </span>
                </div>
              </div>
              <div style={styles.bannerHint}>
                This will apply to all new products added to your store.
              </div>
            </div>
          </div>
        )}

        {/* Main Form Card */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardIconBox}>
              <span style={styles.cardIcon}>💰</span>
            </div>
            <div>
              <h2 style={styles.cardTitle}>Set Defaults</h2>
              <p style={styles.cardSubtitle}>
                Tax and markup for new products
              </p>
            </div>
          </div>

          <div style={styles.formGroup}>
            {/* Row 1: Tax */}
            <div style={styles.formRow}>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Tax Rate (%)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  value={formData.tax_rate}
                  onChange={(e) =>
                    setFormData({ ...formData, tax_rate: e.target.value })
                  }
                  style={styles.input}
                  disabled={saving}
                  placeholder="e.g. 10"
                />
              </div>
            </div>

            {/* Row 2: Markup Type + Amount */}
            <div style={styles.formRow}>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Markup Type</label>
                <select
                  value={formData.markup_type}
                  onChange={(e) => handleTypeChange(e.target.value)}
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
                    formData.markup_type === 'percent'
                      ? 'e.g. 10'
                      : 'e.g. 5.00'
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
          </div>

          {/* Preview Box */}
          {formData.markup_value && (
            <div style={styles.previewBox}>
              <div style={styles.previewLabel}>Preview</div>
              <div style={styles.previewText}>
                <strong>
                  (Amazon Price + ${formData.markup_value}
                  {formData.markup_type === 'percent' ? '%' : ''}
                  {formData.markup_type === 'both' &&
                  formData.extra_percent
                    ? ` + ${formData.extra_percent}%`
                    : ''}
                  )
                </strong>
                {parseFloat(formData.tax_rate) > 0 && (
                  <span style={{ color: '#6d7175' }}>
                    {' '}
                    + <strong>{formData.tax_rate}% tax</strong>
                  </span>
                )}
              </div>
            </div>
          )}

          <div style={styles.formFooter}>
            <button
              type="button"
              onClick={handleSaveClick}
              disabled={saveDisabled}
              style={{
                ...styles.primaryBtn,
                opacity: saveDisabled ? 0.6 : 1,
                cursor: saveDisabled ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? 'Saving...' : 'Save as Default'}
            </button>
          </div>
        </div>

        {/* Alerts */}
        {message && (
          <div
            style={{
              ...styles.messageBox,
              background: message.type === 'success' ? '#f0fdf4' : '#fef2f2',
              color: message.type === 'success' ? '#166534' : '#991b1b',
              border: `1px solid ${
                message.type === 'success' ? '#bbf7d0' : '#fecaca'
              }`,
            }}
          >
            <span style={{ fontSize: '18px', marginRight: '8px' }}>
              {message.type === 'success' ? '✅' : '⚠️'}
            </span>
            {message.text}
          </div>
        )}

        {/* Bottom Action Cards Grid */}
        <div style={styles.grid}>
          {/* Compare Price Settings */}
          <div style={styles.actionCard}>
            <div style={styles.actionCardHeader}>
              <div style={{ ...styles.actionIconBox, background: '#fef3c7' }}>
                <span style={styles.actionIcon}>🏷️</span>
              </div>
              <h3 style={styles.actionTitle}>Compare Price Settings</h3>
            </div>
            <p style={styles.actionText}>
              Set the default <strong>compare-at price</strong> rule
              (strikethrough price). It will apply to every new product you
              add.
            </p>
            <button
              type="button"
              onClick={() => navigateTo('/compare-price-settings')}
              style={{
                ...styles.secondaryBtn,
                background: '#92400e',
                color: 'white',
              }}
            >
              Configure Compare Price →
            </button>
          </div>

          {/* Product-wise Pricing */}
          <div style={styles.actionCard}>
            <div style={styles.actionCardHeader}>
              <div style={{ ...styles.actionIconBox, background: '#ede9fe' }}>
                <span style={styles.actionIcon}>📦</span>
              </div>
              <h3 style={styles.actionTitle}>Product-wise Pricing</h3>
            </div>
            <p style={styles.actionText}>
              To edit existing products or run a bulk update, go to the Products
              page.
            </p>
            <button
              type="button"
              onClick={() => navigateTo('/products')}
              style={{
                ...styles.secondaryBtn,
                background: '#008060',
                color: 'white',
              }}
            >
              Go to Products →
            </button>
          </div>
        </div>
      </div>

      {/* ✅ Custom Confirm Modal (Replaces window.confirm) */}
      {showConfirmModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalBox}>
            <h3 style={styles.modalTitle}>Confirm markup change</h3>
            <p style={styles.modalText}>
              Set default markup to <strong>{pendingPreview}</strong>?
            </p>
            <p style={styles.modalHint}>
              This will apply to all new products added to your store.
            </p>
            <div style={styles.modalActions}>
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                style={styles.modalCancelBtn}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={performSave}
                style={styles.modalConfirmBtn}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================
// Styles
// ============================================
const styles = {
  page: {
    padding: '32px 24px',
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    background: '#f4f6f8',
    minHeight: '100vh',
    color: '#202223',
  },
  container: { maxWidth: '960px', margin: '0 auto' },

  headerNav: { marginBottom: '16px' },
  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '8px 14px',
    background: 'white',
    color: '#202223',
    border: '1px solid #c9cccf',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    transition: 'all 0.2s',
  },

  pageHeader: { marginBottom: '24px' },
  h1: {
    fontSize: '26px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 8px 0',
    letterSpacing: '-0.5px',
  },
  subtitle: {
    color: '#6d7175',
    fontSize: '14px',
    margin: 0,
    lineHeight: '1.5',
  },

  // Banner
  defaultBanner: {
    display: 'flex',
    gap: '16px',
    padding: '20px',
    marginBottom: '24px',
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
    borderRadius: '12px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
  },
  bannerIconBox: {
    width: '40px',
    height: '40px',
    borderRadius: '8px',
    background: '#dcfce7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  bannerIcon: { fontSize: '20px' },
  bannerContent: { flex: 1 },
  bannerTitle: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#166534',
    letterSpacing: '0.5px',
    marginBottom: '12px',
  },
  bannerGrid: {
    display: 'flex',
    gap: '16px',
    flexWrap: 'wrap',
    marginBottom: '12px',
  },
  bannerItem: { display: 'flex', alignItems: 'center', gap: '8px' },
  bannerLabel: { fontSize: '13px', color: '#166534', fontWeight: '500' },
  bannerValue: {
    fontSize: '13px',
    fontWeight: '600',
    color: '#15803d',
    background: 'white',
    padding: '4px 10px',
    borderRadius: '6px',
    border: '1px solid #bbf7d0',
  },
  bannerHint: { fontSize: '13px', color: '#15803d', fontWeight: '500' },

  // Main Card
  card: {
    background: 'white',
    padding: '28px',
    borderRadius: '12px',
    marginBottom: '24px',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    marginBottom: '24px',
  },
  cardIconBox: {
    width: '44px',
    height: '44px',
    borderRadius: '10px',
    background: '#fff7ed',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    border: '1px solid #ffedd5',
  },
  cardIcon: { fontSize: '22px' },
  cardTitle: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 4px 0',
  },
  cardSubtitle: { fontSize: '13px', color: '#6d7175', margin: 0 },

  // Form
  formGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    marginBottom: '24px',
  },
  formRow: { display: 'flex', gap: '20px', flexWrap: 'wrap' },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    flex: '1 1 200px',
    minWidth: '180px',
  },
  label: { fontSize: '13px', fontWeight: '600', color: '#202223' },
  select: {
    padding: '10px 14px',
    border: '1px solid #c9cccf',
    borderRadius: '8px',
    fontSize: '14px',
    background: 'white',
    color: '#202223',
    outline: 'none',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02) inset',
  },
  input: {
    padding: '10px 14px',
    border: '1px solid #c9cccf',
    borderRadius: '8px',
    fontSize: '14px',
    background: 'white',
    color: '#202223',
    outline: 'none',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02) inset',
  },

  // Preview
  previewBox: {
    padding: '16px',
    background: '#f8fafc',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    marginBottom: '24px',
  },
  previewLabel: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '6px',
  },
  previewText: { fontSize: '14px', color: '#1e293b', fontWeight: '500' },

  // Footer & Buttons
  formFooter: {
    display: 'flex',
    justifyContent: 'flex-start',
    borderTop: '1px solid #e1e3e5',
    paddingTop: '24px',
  },
  primaryBtn: {
    color: 'white',
    background: '#008060',
    border: 'none',
    padding: '12px 24px',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
    transition: 'background 0.2s',
  },

  // Message
  messageBox: {
    display: 'flex',
    alignItems: 'center',
    padding: '16px',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    marginBottom: '24px',
  },

  // Grid for bottom cards
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
    gap: '20px',
  },
  actionCard: {
    display: 'flex',
    flexDirection: 'column',
    padding: '24px',
    background: 'white',
    border: '1px solid #e1e3e5',
    borderRadius: '12px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  actionCardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '12px',
  },
  actionIconBox: {
    width: '40px',
    height: '40px',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  actionIcon: { fontSize: '20px' },
  actionTitle: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#202223',
    margin: 0,
  },
  actionText: {
    fontSize: '14px',
    color: '#6d7175',
    margin: '0 0 20px 0',
    lineHeight: '1.5',
    flex: 1,
  },
  secondaryBtn: {
    alignSelf: 'flex-start',
    padding: '10px 18px',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'opacity 0.2s',
  },

  // ✅ Modal Styles (New)
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modalBox: {
    background: 'white',
    padding: '24px',
    borderRadius: '12px',
    maxWidth: '400px',
    width: '90%',
    boxShadow: '0 10px 40px rgba(0,0,0,0.15)',
  },
  modalTitle: { fontSize: '18px', fontWeight: '700', margin: '0 0 12px 0' },
  modalText: { fontSize: '14px', color: '#202223', margin: '0 0 8px 0' },
  modalHint: { fontSize: '13px', color: '#6d7175', margin: '0 0 20px 0' },
  modalActions: { display: 'flex', gap: '12px', justifyContent: 'flex-end' },
  modalCancelBtn: {
    padding: '10px 18px',
    background: 'white',
    border: '1px solid #c9cccf',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
  },
  modalConfirmBtn: {
    padding: '10px 18px',
    background: '#008060',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
  },
}