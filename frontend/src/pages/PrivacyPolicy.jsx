// src/pages/PrivacyPolicy.jsx
export default function PrivacyPolicy() {
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.h1}>Privacy Policy</h1>
        <p style={styles.updated}>
          <strong>Last updated:</strong> 2026-10-08
        </p>

        <h2 style={styles.h2}>1. Information We Collect</h2>
        <p style={styles.text}>
          When you install Amazon Product Manager on your Shopify store, we collect:
        </p>
        <ul style={styles.list}>
          <li>Your Shopify store domain (e.g., your-store.myshopify.com)</li>
          <li>Shopify Admin API access token (to sync products and prices)</li>
          <li>Product data (titles, prices, images, ASINs) from your Shopify store</li>
        </ul>

        <h2 style={styles.h2}>2. How We Use Your Information</h2>
        <p style={styles.text}>We use your information solely to:</p>
        <ul style={styles.list}>
          <li>Sync Amazon product data (price, availability, images) to your Shopify store</li>
          <li>Update product prices automatically based on Amazon prices + your markup</li>
          <li>Manage your subscription via Shopify Billing API</li>
        </ul>

        <h2 style={styles.h2}>3. Data Sharing</h2>
        <p style={styles.text}>
          We do <strong>not</strong> sell, trade, or share your data with third parties.
          All data is stored securely in our database (Supabase PostgreSQL).
        </p>

        <h2 style={styles.h2}>4. Data Retention</h2>
        <p style={styles.text}>
          We retain your data as long as you use the app. When you uninstall the app,
          your data is deleted within 30 days.
        </p>

        <h2 style={styles.h2}>5. Your Rights</h2>
        <p style={styles.text}>
          You can request deletion of your data at any time by contacting us.
        </p>

        <h2 style={styles.h2}>6. Contact</h2>
        <p style={styles.text}>
          For privacy questions, contact us at:{' '}
          <strong>your-email@example.com</strong>
        </p>
      </div>
    </div>
  )
}

// ============================================
// Styles
// ============================================
const styles = {
  page: {
    padding: '40px 20px',
    background: '#f6f6f7',
    minHeight: '100vh',
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  container: {
    maxWidth: '800px',
    margin: '0 auto',
    background: 'white',
    padding: '40px',
    borderRadius: '10px',
    border: '1px solid #e1e3e5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
    lineHeight: '1.6',
  },
  h1: {
    fontSize: '26px',
    fontWeight: '700',
    color: '#202223',
    marginBottom: '6px',
  },
  updated: {
    fontSize: '13px',
    color: '#637381',
    marginBottom: '24px',
  },
  h2: {
    fontSize: '17px',
    fontWeight: '700',
    color: '#202223',
    marginTop: '24px',
    marginBottom: '8px',
  },
  text: {
    fontSize: '14px',
    color: '#202223',
    marginBottom: '12px',
  },
  list: {
    fontSize: '14px',
    color: '#202223',
    paddingLeft: '20px',
    marginBottom: '12px',
  },
}