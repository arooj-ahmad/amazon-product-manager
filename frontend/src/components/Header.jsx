// src/components/Header.jsx
import { theme } from '../styles/theme'

// ✅ Naya Premium Amazon Logo (SVG)
const AmazonLogoIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Background White Circle taake icon pop kare */}
    <rect width="24" height="24" rx="6" fill="white" />
    {/* Amazon Cart Outline */}
    <path d="M5 7H7L9 14H16L18 9H8" stroke="#232F3E" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="9.5" cy="17.5" r="1.5" fill="#FF9900"/>
    <circle cx="15.5" cy="17.5" r="1.5" fill="#FF9900"/>
    {/* Amazon Smile Arrow */}
    <path d="M7 11C7 11 10 14 12 14C14 14 17 11 17 11" stroke="#FF9900" strokeWidth="1.8" strokeLinecap="round"/>
    <path d="M15 10L17 11L16 12.5" stroke="#FF9900" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

export default function Header({
  shopifyReady,
  shopDomain,
  subscription,
}) {
  return (
    <div style={styles.wrapper}>
      {/* Logo + Title */}
      <div style={styles.brandRow}>
        <div style={styles.logoBox}>
          <AmazonLogoIcon />
        </div>
        <div>
          <h1 style={styles.h1}>Amazon Product Manager</h1>
          <p style={styles.subtitle}>
            Add Amazon products directly to your Shopify store
          </p>
        </div>
      </div>

      {/* Status Pills */}
      <div style={styles.statusRow}>
        {/* Connection status */}
        <div
          style={{
            ...styles.pill,
            background: shopifyReady
              ? theme.colors.successBg
              : theme.colors.warningBg,
            color: shopifyReady
              ? theme.colors.success
              : '#b45309',
            border: `1px solid ${
              shopifyReady
                ? theme.colors.successBorder
                : '#ffe4a3'
            }`,
          }}
        >
          <span
            style={{
              ...styles.dot,
              background: shopifyReady
                ? theme.colors.success
                : theme.colors.warning,
            }}
          />
          {shopifyReady ? 'Connected' : 'Testing Mode'}
        </div>

        {/* Shop domain */}
        {shopDomain && (
          <div style={styles.pillLight}>
            <span style={styles.pillIcon}>🏪</span>
            {shopDomain}
          </div>
        )}

        {/* Subscription plan */}
        {subscription?.active && (
          <div style={styles.pillPlan}>
            <span style={styles.dot} />
            {subscription.subscription?.name || 'Active'}
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  wrapper: {
    marginBottom: '24px',
  },
  brandRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    marginBottom: '16px',
  },
  logoBox: {
    width: '52px',
    height: '52px',
    borderRadius: theme.radii.lg,
    // ✅ Amazon Dark Navy Blue Gradient
    background: 'linear-gradient(135deg, #232F3E 0%, #131A22 100%)', 
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(35, 47, 62, 0.25)', // Premium Shadow
    flexShrink: 0,
  },
  h1: {
    fontSize: '22px',
    fontWeight: '700',
    color: theme.colors.text,
    margin: '0 0 4px',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '13px',
    color: theme.colors.textSecondary,
    margin: 0,
  },
  statusRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    alignItems: 'center',
  },
  pill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: theme.radii.full,
    fontSize: '12px',
    fontWeight: '600',
  },
  pillLight: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: theme.radii.full,
    fontSize: '12px',
    fontWeight: '500',
    background: theme.colors.bgCard,
    color: theme.colors.textSecondary,
    border: `1px solid ${theme.colors.border}`,
  },
  pillPlan: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: theme.radii.full,
    fontSize: '12px',
    fontWeight: '600',
    background: 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)',
    color: '#6d28d9',
    border: '1px solid #c4b5fd',
  },
  dot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: 'currentColor',
    display: 'inline-block',
  },
  pillIcon: {
    fontSize: '12px',
  },
}