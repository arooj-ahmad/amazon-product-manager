// src/components/MessageAlert.jsx
import { theme } from '../styles/theme'

export default function MessageAlert({ message }) {
  if (!message) return null

  const isSuccess = message.type === 'success'
  const isError = message.type === 'error'
  const isWarning = message.type === 'warning'

  const config = isSuccess
    ? {
        bg: theme.colors.successBg,
        color: theme.colors.successText,
        border: theme.colors.successBorder,
        icon: '✓',
      }
    : isError
    ? {
        bg: theme.colors.errorBg,
        color: theme.colors.errorText,
        border: theme.colors.errorBorder,
        icon: '!',
      }
    : {
        bg: theme.colors.warningBg,
        color: theme.colors.warningText,
        border: '#f5d97a',
        icon: '⚠',
      }

  return (
    <div
      style={{
        marginTop: '16px',
        padding: '12px 16px',
        borderRadius: theme.radius.md,
        fontSize: '13.5px',
        fontWeight: '500',
        background: config.bg,
        color: config.color,
        border: `1px solid ${config.border}`,
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        lineHeight: '1.5',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          background: config.color,
          color: 'white',
          fontSize: '11px',
          fontWeight: 'bold',
          flexShrink: 0,
          marginTop: '1px',
        }}
      >
        {config.icon}
      </span>
      <span style={{ flex: 1 }}>{message.text}</span>
    </div>
  )
}