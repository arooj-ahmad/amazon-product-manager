// src/components/Header.jsx
import { theme } from '../styles/theme'

export default function Header({
  shopifyReady,
  shopDomain,
  subscription,
  // ❌ onOpenMarkupSettings HATAO — ab sidebar mein hai
}) {
  return (
    <div style={styles.wrapper}>
      {/* Logo + Title */}
      <div style={styles.brandRow}>
        <div style={styles.logoBox}>
          <span style={styles.logo}>🛒</span>
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
    background: theme.colors.gradientPrimary,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: theme.shadows.md,
    flexShrink: 0,
  },
  logo: {
    fontSize: '26px',
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