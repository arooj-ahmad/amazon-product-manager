// src/components/InfoBox.jsx
import { styles, theme } from '../styles/theme'

export default function InfoBox() {
  return (
    <>
      <div style={styles.infoBox}>
        <strong style={{ color: theme.colors.textPrimary }}>
          💡 How it works:
        </strong>
        <ol
          style={{
            marginTop: '12px',
            paddingLeft: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            margin: '12px 0 0 0',
          }}
        >
          <li>Paste any Amazon product URL</li>
          <li>Set your markup ($ fixed or % percent)</li>
          <li>Click "Fetch &amp; Add"</li>
          <li>We fetch title, images, price, and specs from Amazon</li>
          <li>Product is added to both Supabase and your Shopify store</li>
          <li>Product appears in your Shopify Products list</li>
        </ol>
      </div>

      <div style={styles.securityBox}>
        <span>🔒</span>
        <span>
          <strong>Secure:</strong> This app uses Shopify ID tokens for
          authentication. Only users with access to this store can add products.
        </span>
      </div>
    </>
  )
}