// src/components/Loader.jsx
// ✅ Reusable Circle Spinner Loader
// Har page pe use kar sakte ho — full screen centered

import { theme } from '../styles/theme'

export default function Loader({ text = 'Loading...', fullScreen = true }) {
  const containerStyle = fullScreen
    ? {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        width: '100%',
        padding: '40px 20px',
      }
    : {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 20px',
      }

  return (
    <div style={containerStyle}>
      <div style={{ textAlign: 'center' }}>
        <div style={styles.spinner} />
        <p style={styles.text}>{text}</p>
      </div>
    </div>
  )
}

// Inline spinner (chhote buttons ke liye)
export function InlineSpinner({ size = 16, color = 'white' }) {
  return (
    <div
      style={{
        width: `${size}px`,
        height: `${size}px`,
        border: `2px solid rgba(255,255,255,0.3)`,
        borderTopColor: color,
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
        display: 'inline-block',
      }}
    />
  )
}

const styles = {
  spinner: {
    width: '48px',
    height: '48px',
    border: '4px solid #e1e3e5',
    borderTop: '4px solid #ff9900',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    margin: '0 auto 16px',
  },
  text: {
    color: '#637381',
    fontSize: '14px',
    fontWeight: '500',
    margin: 0,
  },
}