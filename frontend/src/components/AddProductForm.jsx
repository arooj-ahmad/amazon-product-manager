// src/components/AddProductForm.jsx
// ✅ SIMPLIFIED & IMPROVED: Amazon Logo added to input field
import { useState } from 'react'
import { theme } from '../styles/theme'

// Amazon Smile Logo (SVG) - No external image needed
const AmazonLogo = ({ size = 20 }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none" 
    xmlns="http://www.w3.org/2000/svg"
    style={{ flexShrink: 0 }}
  >
    {/* Amazon Smile Arrow */}
    <path 
      d="M3 15C3 15 7.5 19 12 19C16.5 19 21 15 21 15" 
      stroke="#FF9900" 
      strokeWidth="2.5" 
      strokeLinecap="round"
    />
    <path 
      d="M18 13L21 15L18 17" 
      stroke="#FF9900" 
      strokeWidth="2.5" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    />
    {/* Amazon Box 'a' style outline */}
    <rect x="4" y="4" width="16" height="16" rx="4" stroke="#232F3E" strokeWidth="1.5" strokeOpacity="0.8"/>
    <text x="12" y="15.5" textAnchor="middle" fontSize="9" fontWeight="bold" fill="#232F3E" fontFamily="Arial, sans-serif">a</text>
  </svg>
)

export default function AddProductForm({
  amazonUrl,
  setAmazonUrl,
  isLoading,
  message,
  onSubmit,
}) {
  const [isFocused, setIsFocused] = useState(false)

  // ✅ URL validation only
  const isFormValid = () => {
    return amazonUrl.trim().length > 0
  }

  const formValid = isFormValid()

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
            Amazon Product URL
          </label>
          
          {/* ✅ Input Wrapper with Amazon Logo inside */}
          <div 
            style={{
              ...styles.inputWrapper,
              borderColor: isFocused ? theme.colors.primary || '#3b82f6' : theme.colors.border,
              boxShadow: isFocused ? `0 0 0 3px ${(theme.colors.primary || '#3b82f6')}20` : 'none',
            }}
          >
            <div style={styles.inputIconContainer}>
              <AmazonLogo size={20} />
            </div>
            <input
              type="text"
              value={amazonUrl}
              onChange={(e) => setAmazonUrl(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder="https://www.amazon.com/dp/B0B2RM68G2"
              style={styles.input}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Info Banner */}
        <div style={styles.infoBanner}>
          <span style={styles.infoIcon}>💡</span>
          <span style={styles.infoText}>
            Markup will be applied from your saved settings. To change it, go to the{' '}
            <strong>Markup Settings</strong> page.
          </span>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isLoading || !formValid}
          style={{
            ...styles.button,
            background:
              isLoading || !formValid
                ? 'linear-gradient(135deg, #b5b5b5 0%, #d1d1d1 100%)'
                : theme.colors.gradientPrimary,
            cursor:
              isLoading || !formValid ? 'not-allowed' : 'pointer',
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
// Styles
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
  // ✅ NEW: Wrapper for input + logo
  inputWrapper: {
    display: 'flex',
    alignItems: 'center',
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    background: theme.colors.bgSubtle,
    transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
    overflow: 'hidden',
  },
  inputIconContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 12px',
    background: 'white',
    borderRight: `1px solid ${theme.colors.border}`,
    height: '100%',
    alignSelf: 'stretch',
  },
  input: {
    width: '100%',
    padding: '12px 14px',
    border: 'none',
    borderRadius: 0,
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box',
    background: 'transparent',
    color: theme.colors.text,
    transition: theme.transitions.fast,
  },
  infoBanner: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    padding: '12px 14px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: theme.radii.md,
  },
  infoIcon: {
    fontSize: '16px',
    flexShrink: 0,
  },
  infoText: {
    fontSize: '13px',
    color: '#1e40af',
    lineHeight: '1.5',
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