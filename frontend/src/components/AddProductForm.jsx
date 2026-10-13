// src/components/AddProductForm.jsx
import { theme } from '../styles/theme'

export default function AddProductForm({
  amazonUrl,
  setAmazonUrl,
  markup,
  setMarkup,
  markupType,
  setMarkupType,
  extraPercent,          // ✅ NAYA
  setExtraPercent,       // ✅ NAYA
  isLoading,
  message,
  onSubmit,
}) {
  // ✅ NAYA: Final price hint dynamically banao
  const getPriceHint = () => {
    const m = parseFloat(markup) || 0
    const e = parseFloat(extraPercent) || 0

    if (markupType === 'percent') {
      return `💡 Final price = Amazon price × (1 + ${m}%)`
    }
    if (markupType === 'both') {
      return `💡 Final price = (Amazon price + $${m}) × (1 + ${e}%)`
    }
    return `💡 Final price = Amazon price + $${m}`
  }

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <span style={styles.icon}>➕</span>
        </div>
        <div>
          <h3 style={styles.title}>Add New Product</h3>
          <p style={styles.subtitle}>
            Paste an Amazon URL to import it to your store
          </p>
        </div>
      </div>

      <form onSubmit={onSubmit} style={styles.form}>
        {/* Amazon URL */}
        <div style={styles.field}>
          <label style={styles.label}>
            <span style={styles.labelIcon}>🔗</span>
            Amazon Product URL
          </label>
          <input
            type="text"
            value={amazonUrl}
            onChange={(e) => setAmazonUrl(e.target.value)}
            placeholder="https://www.amazon.com/dp/B0B2RM68G2"
            style={styles.input}
            disabled={isLoading}
          />
        </div>

        {/* Markup */}
        <div style={styles.field}>
          <label style={styles.label}>
            <span style={styles.labelIcon}>💰</span>
            Markup Settings
          </label>
          <div style={styles.markupRow}>
            <select
              value={markupType}
              onChange={(e) => setMarkupType(e.target.value)}
              style={styles.select}
              disabled={isLoading}
            >
              <option value="fixed">$ Fixed</option>
              <option value="percent">% Percent</option>
              <option value="both">$ + % (Both)</option>   {/* ✅ NAYA */}
            </select>
            <input
              type="number"
              value={markup}
              onChange={(e) => setMarkup(e.target.value)}
              placeholder={markupType === 'percent' ? '10' : '2.00'}
              step="0.01"
              min="0"
              style={styles.inputSmall}
              disabled={isLoading}
            />

            {/* ✅ NAYA: Extra % input — sirf "both" ke liye */}
            {markupType === 'both' && (
              <input
                type="number"
                value={extraPercent}
                onChange={(e) => setExtraPercent(e.target.value)}
                placeholder="Extra %"
                step="0.01"
                min="0"
                max="500"
                style={styles.inputSmall}
                disabled={isLoading}
              />
            )}
          </div>
          <p style={styles.hint}>{getPriceHint()}</p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isLoading || !amazonUrl.trim()}
          style={{
            ...styles.button,
            background:
              isLoading || !amazonUrl.trim()
                ? 'linear-gradient(135deg, #b5b5b5 0%, #d1d1d1 100%)'
                : theme.colors.gradientPrimary,
            cursor:
              isLoading || !amazonUrl.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          {isLoading ? (
            <>
              <span style={styles.spinner} />
              <span>Fetching from Amazon...</span>
            </>
          ) : (
            <>
              <span>🛍️</span>
              <span>Fetch & Add to Shopify</span>
            </>
          )}
        </button>

        {/* Loading Hint */}
        {isLoading && (
          <p style={styles.loadingHint}>
            ⏳ This may take 20-40 seconds while we fetch data from Amazon...
          </p>
        )}

        {/* Message */}
        {message && (
          <div
            style={{
              ...styles.message,
              background:
                message.type === 'success'
                  ? theme.colors.successBg
                  : theme.colors.errorBg,
              color:
                message.type === 'success'
                  ? theme.colors.success
                  : theme.colors.error,
              border: `1px solid ${
                message.type === 'success'
                  ? theme.colors.successBorder
                  : theme.colors.errorBorder
              }`,
            }}
          >
            {message.text}
          </div>
        )}
      </form>
    </div>
  )
}

// ============================================
// Styles — SAME AS BEFORE
// ============================================
const styles = {
  card: {
    background: theme.colors.bgCard,
    borderRadius: theme.radii.lg,
    border: `1px solid ${theme.colors.border}`,
    padding: '24px',
    marginBottom: '20px',
    boxShadow: theme.shadows.md,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '20px',
  },
  iconBox: {
    width: '40px',
    height: '40px',
    borderRadius: theme.radii.md,
    background: 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: {
    fontSize: '20px',
  },
  title: {
    fontSize: '16px',
    fontWeight: '700',
    color: theme.colors.text,
    margin: '0 0 2px',
  },
  subtitle: {
    fontSize: '12px',
    color: theme.colors.textSecondary,
    margin: 0,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  label: {
    fontSize: '13px',
    fontWeight: '600',
    color: theme.colors.text,
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  labelIcon: {
    fontSize: '14px',
  },
  input: {
    width: '100%',
    padding: '12px 14px',
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box',
    background: theme.colors.bgSubtle,
    color: theme.colors.text,
    transition: theme.transitions.fast,
  },
  markupRow: {
    display: 'flex',
    gap: '8px',
  },
  select: {
    padding: '12px 14px',
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    fontSize: '14px',
    outline: 'none',
    background: theme.colors.bgSubtle,
    color: theme.colors.text,
    cursor: 'pointer',
    minWidth: '130px',
    fontWeight: '500',
  },
  inputSmall: {
    flex: 1,
    padding: '12px 14px',
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box',
    background: theme.colors.bgSubtle,
    color: theme.colors.text,
    minWidth: '80px',
  },
  hint: {
    fontSize: '12px',
    color: theme.colors.textMuted,
    margin: 0,
  },
  button: {
    width: '100%',
    padding: '14px 20px',
    color: 'white',
    border: 'none',
    borderRadius: theme.radii.md,
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: theme.transitions.fast,
    boxShadow: theme.shadows.md,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    marginTop: '8px',
  },
  spinner: {
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  loadingHint: {
    fontSize: '12px',
    color: theme.colors.textSecondary,
    textAlign: 'center',
    margin: 0,
    padding: '8px',
    background: theme.colors.bgSubtle,
    borderRadius: theme.radii.sm,
  },
  message: {
    padding: '12px 16px',
    borderRadius: theme.radii.md,
    fontSize: '13px',
    fontWeight: '500',
    textAlign: 'center',
  },
}