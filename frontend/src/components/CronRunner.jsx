// src/components/CronRunner.jsx
import { theme } from '../styles/theme'

export default function CronRunner({
  cronRunning,
  cronMessage,
  onRunCron,
}) {
  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <span style={styles.icon}>⚡</span>
        </div>
        <div style={styles.headerText}>
          <h3 style={styles.title}>Manual Price Update</h3>
          <p style={styles.subtitle}>
            Fetch latest Amazon prices and sync your Shopify products
          </p>
        </div>
      </div>

      {/* Button */}
      <button
        type="button"
        onClick={onRunCron}
        disabled={cronRunning}
        style={{
          ...styles.button,
          background: cronRunning
            ? 'linear-gradient(135deg, #b5b5b5 0%, #d1d1d1 100%)'
            : theme.colors.gradientPrimary,
          cursor: cronRunning ? 'not-allowed' : 'pointer',
          transform: cronRunning ? 'none' : 'translateY(0)',
        }}
        onMouseEnter={(e) => {
          if (!cronRunning) {
            e.currentTarget.style.transform = 'translateY(-2px)'
            e.currentTarget.style.boxShadow = theme.shadows.lg
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = theme.shadows.md
        }}
      >
        {cronRunning ? (
          <>
            <span style={styles.spinner} />
            <span>Running Price Update...</span>
          </>
        ) : (
          <>
            <span style={styles.buttonIcon}>🚀</span>
            <span>Run Price Update Now</span>
          </>
        )}
      </button>

      {/* Message */}
      {cronMessage && (
        <div
          style={{
            ...styles.message,
            background:
              cronMessage.type === 'success'
                ? theme.colors.successBg
                : theme.colors.errorBg,
            color:
              cronMessage.type === 'success'
                ? theme.colors.success
                : theme.colors.error,
            border: `1px solid ${
              cronMessage.type === 'success'
                ? theme.colors.successBorder
                : theme.colors.errorBorder
            }`,
          }}
        >
          {cronMessage.text}
        </div>
      )}
    </div>
  )
}

const styles = {
  card: {
    background: theme.colors.bgCard,
    borderRadius: theme.radii.lg,
    border: `1px solid ${theme.colors.border}`,
    padding: '20px',
    marginBottom: '20px',
    boxShadow: theme.shadows.sm,
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    marginBottom: '16px',
  },
  iconBox: {
    width: '40px',
    height: '40px',
    borderRadius: theme.radii.md,
    background: 'linear-gradient(135deg, #fff8e6 0%, #ffefc2 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: {
    fontSize: '20px',
  },
  headerText: {
    flex: 1,
  },
  title: {
    fontSize: '15px',
    fontWeight: '600',
    color: theme.colors.text,
    margin: '0 0 4px',
  },
  subtitle: {
    fontSize: '13px',
    color: theme.colors.textSecondary,
    margin: 0,
    lineHeight: '1.4',
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
  },
  buttonIcon: {
    fontSize: '16px',
  },
  spinner: {
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  message: {
    marginTop: '12px',
    padding: '12px 16px',
    borderRadius: theme.radii.md,
    fontSize: '13px',
    fontWeight: '500',
    textAlign: 'center',
  },
}