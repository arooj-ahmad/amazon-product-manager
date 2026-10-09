// src/components/Header.jsx
import { styles, theme } from '../styles/theme'

const badgeBase = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  padding: '5px 12px',
  fontSize: '12px',
  borderRadius: '20px',
  fontWeight: '600',
  lineHeight: '1.4',
  transition: 'all 0.2s',
}

export default function Header({ shopifyReady, shopDomain, subscription }) {
  return (
    <>
      <h1 style={styles.h1}>🛒 Amazon Product Manager</h1>
      <p style={styles.subtitle}>
        Add Amazon products directly to your Shopify store
      </p>

      <div style={styles.badgeRow}>
        {shopifyReady ? (
          <span
            style={{
              ...badgeBase,
              background: theme.colors.badgeSuccessBg,
              color: theme.colors.successText,
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: theme.colors.successText,
                display: 'inline-block',
              }}
            />
            Connected
          </span>
        ) : (
          <span
            style={{
              ...badgeBase,
              background: theme.colors.warningBg,
              color: theme.colors.warningText,
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: theme.colors.warningText,
                display: 'inline-block',
                animation: 'pulse 1.5s infinite',
              }}
            />
            Connecting...
          </span>
        )}

        {shopDomain && (
          <span
            style={{
              ...badgeBase,
              background: theme.colors.badgeInfoBg,
              color: theme.colors.infoText,
              fontFamily: 'ui-monospace, SFMono-Regular, monospace',
              fontSize: '11.5px',
              fontWeight: '500',
            }}
          >
            {shopDomain}
          </span>
        )}

        {subscription?.subscription?.name && (
          <span
            style={{
              ...badgeBase,
              background: theme.colors.badgeSuccessBg,
              color: theme.colors.successText,
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: theme.colors.successText,
                display: 'inline-block',
              }}
            />
            {subscription.subscription.name} Active
          </span>
        )}

        {/* ✅ FIX: target="_top" hata diya */}
        <a
          href="/markup-settings"
          style={{
            ...badgeBase,
            background: theme.colors.badgeInfoBg,
            color: theme.colors.infoText,
            textDecoration: 'none',
            cursor: 'pointer',
          }}
        >
          ⚙️ Markup Settings
        </a>
      </div>
    </>
  )
}