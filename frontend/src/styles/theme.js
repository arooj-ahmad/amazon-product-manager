// src/styles/theme.js
// ✅ UPDATED: container maxWidth 720px → 1000px (better centering)

export const theme = {
  colors: {
    // Primary (Shopify green)
    primary: '#008060',
    primaryDark: '#006e52',
    primaryLight: '#e6f5f1',
    
    // Gradients
    gradientPrimary: 'linear-gradient(135deg, #008060 0%, #00a67d 100%)',
    gradientSuccess: 'linear-gradient(135deg, #00a67d 0%, #4cd4a7 100%)',
    gradientDanger: 'linear-gradient(135deg, #d32f2f 0%, #f44336 100%)',
    
    // Backgrounds
    bg: '#f6f6f7',
    bgCard: '#ffffff',
    bgHover: '#f0f1f2',
    bgSubtle: '#fafbfc',
    
    // Text
    text: '#202223',
    textSecondary: '#6d7175',
    textMuted: '#8c9196',
    
    // Borders
    border: '#e1e3e5',
    borderLight: '#f1f2f3',
    
    // Status
    success: '#008060',
    successBg: '#eefbf4',
    successBorder: '#aee9d1',
    error: '#d32f2f',
    errorBg: '#fff4f4',
    errorBorder: '#ffd6d6',
    warning: '#ffb700',
    warningBg: '#fff8e6',
    
    // Accents
    blue: '#4a90e2',
    purple: '#8b5cf6',
    pink: '#ec4899',
    orange: '#ff8c42',
  },
  
  shadows: {
    sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
    md: '0 2px 8px rgba(0, 0, 0, 0.08)',
    lg: '0 4px 16px rgba(0, 0, 0, 0.10)',
    xl: '0 8px 24px rgba(0, 0, 0, 0.12)',
    focus: '0 0 0 3px rgba(0, 128, 96, 0.15)',
  },
  
  radii: {
    sm: '6px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    full: '9999px',
  },
  
  transitions: {
    fast: 'all 0.15s ease',
    normal: 'all 0.25s ease',
    slow: 'all 0.4s ease',
  },
}

export const styles = {
  // Page layout
  page: {
    minHeight: '100vh',
    background: theme.colors.bg,
    padding: '0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  
  // ✅ UPDATED: 720px → 1000px
  container: {
    maxWidth: '1000px',
    margin: '0 auto',
    padding: '24px 20px 60px',
  },
  
  // Cards
  card: {
    background: theme.colors.bgCard,
    borderRadius: theme.radii.lg,
    border: `1px solid ${theme.colors.border}`,
    padding: '24px',
    marginBottom: '20px',
    boxShadow: theme.shadows.sm,
  },
  
  // Typography
  h1: {
    fontSize: '26px',
    fontWeight: '700',
    color: theme.colors.text,
    margin: '0 0 8px',
    letterSpacing: '-0.02em',
  },
  
  subtitle: {
    fontSize: '14px',
    color: theme.colors.textSecondary,
    margin: '0 0 24px',
  },
  
  // Buttons
  button: {
    padding: '12px 24px',
    background: theme.colors.gradientPrimary,
    color: 'white',
    border: 'none',
    borderRadius: theme.radii.md,
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: theme.transitions.fast,
    boxShadow: theme.shadows.sm,
  },
  
  // ... existing styles (keep them for compatibility)
  centerBox: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    background: theme.colors.bg,
  },
  
  messageBox: {
    padding: '16px 20px',
    borderRadius: theme.radii.md,
    fontSize: '14px',
    marginBottom: '16px',
  },
  
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '16px',
    marginBottom: '24px',
  },
}