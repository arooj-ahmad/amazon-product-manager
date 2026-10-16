// src/components/InfoBox.jsx
import { styles, theme } from '../styles/theme'

const HOW_IT_WORKS = [
  'Paste any Amazon product URL',
  'Set your markup ($ fixed or % percent)',
  'Click "Fetch & Add"',
  'We fetch title, images, price, and specs from Amazon',
  'Product is added to both Supabase and your Shopify store',
  'Product appears in your Shopify Products list',
]

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
          {HOW_IT_WORKS.map((step, idx) => (
            <li key={idx}>{step}</li>
          ))}
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