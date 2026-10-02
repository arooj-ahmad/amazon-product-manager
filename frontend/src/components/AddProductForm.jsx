// src/components/AddProductForm.jsx
import { styles, theme } from '../styles/theme'
import MessageAlert from './MessageAlert'

export default function AddProductForm({
  amazonUrl,
  setAmazonUrl,
  markup,
  setMarkup,
  markupType,
  setMarkupType,
  isLoading,
  message,
  onSubmit,
}) {
  return (
    <div style={styles.card}>
      <h2 style={styles.h2}>
        <span style={{ marginRight: '8px' }}>➕</span>
        Add New Product
      </h2>

      <form onSubmit={onSubmit}>
        {/* URL Input */}
        <label style={styles.label}>Amazon Product URL</label>
        <input
          type="url"
          value={amazonUrl}
          onChange={(e) => setAmazonUrl(e.target.value)}
          placeholder="https://www.amazon.com/dp/B0B2RM68G2"
          required
          disabled={isLoading}
          style={{
            ...styles.input,
            background: isLoading ? '#f6f6f7' : 'white',
            cursor: isLoading ? 'not-allowed' : 'text',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = theme.colors.primary
            e.target.style.boxShadow = `0 0 0 3px rgba(0, 128, 96, 0.1)`
          }}
          onBlur={(e) => {
            e.target.style.borderColor = theme.colors.borderInput
            e.target.style.boxShadow = 'none'
          }}
        />

        {/* Markup */}
        <label style={styles.label}>Markup Settings</label>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '8px' }}>
          <select
            value={markupType}
            onChange={(e) => setMarkupType(e.target.value)}
            disabled={isLoading}
            style={{
              ...styles.input,
              width: '150px',
              marginBottom: 0,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              background: isLoading ? '#f6f6f7' : 'white',
            }}
          >
            <option value="fixed">$ Fixed</option>
            <option value="percent">% Percent</option>
          </select>
          <input
            type="number"
            step="0.01"
            min="0"
            value={markup}
            onChange={(e) => setMarkup(e.target.value)}
            placeholder="2.00"
            disabled={isLoading}
            style={{
              ...styles.input,
              flex: 1,
              marginBottom: 0,
              background: isLoading ? '#f6f6f7' : 'white',
              cursor: isLoading ? 'not-allowed' : 'text',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = theme.colors.primary
              e.target.style.boxShadow = `0 0 0 3px rgba(0, 128, 96, 0.1)`
            }}
            onBlur={(e) => {
              e.target.style.borderColor = theme.colors.borderInput
              e.target.style.boxShadow = 'none'
            }}
          />
        </div>

        <p style={styles.helpText}>
          💡 Final price = Amazon price{' '}
          {markupType === 'percent' ? '× (1 + %/100)' : '+ $'}
        </p>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading}
          style={{
            ...styles.primaryBtn,
            background: isLoading
              ? theme.colors.primaryDisabled
              : theme.colors.primary,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            marginTop: '24px',
            boxShadow: isLoading
              ? 'none'
              : '0 2px 8px rgba(0, 128, 96, 0.2)',
          }}
          onMouseEnter={(e) => {
            if (!isLoading) {
              e.currentTarget.style.background = theme.colors.primaryHover
              e.currentTarget.style.boxShadow =
                '0 4px 12px rgba(0, 128, 96, 0.3)'
            }
          }}
          onMouseLeave={(e) => {
            if (!isLoading) {
              e.currentTarget.style.background = theme.colors.primary
              e.currentTarget.style.boxShadow =
                '0 2px 8px rgba(0, 128, 96, 0.2)'
            }
          }}
        >
          {isLoading ? (
            <>
              <span className="spinner" />
              Fetching from Amazon...
            </>
          ) : (
            <>🛍️ Fetch &amp; Add to Shopify</>
          )}
        </button>
      </form>

      {isLoading && (
        <p style={{ ...styles.helpText, textAlign: 'center' }}>
          ⏱ This may take 20–40 seconds while we fetch data from Amazon...
        </p>
      )}

      <MessageAlert message={message} />
    </div>
  )
}