// ============================================
// frontend/src/pages/ShopifyApp.jsx
// Shopify Admin ke andar iframe mein dikhne wala app
// ============================================

import { useState, useEffect } from 'react'

function ShopifyApp() {
  const [amazonUrl, setAmazonUrl] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [shopifyReady, setShopifyReady] = useState(false)

  // ========================================
  // App Bridge ready check
  // ========================================
  useEffect(() => {
    const checkShopify = setInterval(() => {
      if (window.shopify) {
        setShopifyReady(true)
        clearInterval(checkShopify)

        if (window.shopify.toast) {
          window.shopify.toast.show('Amazon Product Manager loaded!')
        }
      }
    }, 500)

    return () => clearInterval(checkShopify)
  }, [])

  // ========================================
  // Add Product Handler
  // ========================================
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim()) return

    setIsLoading(true)
    setMessage(null)

    try {
      // App Bridge se ID token lein
      let idToken = ''
      if (window.shopify && window.shopify.idToken) {
        idToken = await window.shopify.idToken()
      }

      // Backend par bhejein
      const API_URL =
        import.meta.env.VITE_API_URL || 'http://localhost:8000'

      const response = await fetch(
        `${API_URL}/api/shopify/app/add-product`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${idToken}`,
          },
          body: JSON.stringify({ amazon_url: amazonUrl.trim() }),
        }
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to add product')
      }

      setMessage({
        type: 'success',
        text: `✅ ${data.message || 'Product added successfully!'}`,
      })
      setAmazonUrl('')

      if (window.shopify && window.shopify.toast) {
        window.shopify.toast.show('Product added!')
      }
    } catch (err) {
      setMessage({
        type: 'error',
        text: `❌ ${err.message || 'Failed to add product'}`,
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={{ padding: '20px', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <h1
            style={{
              fontSize: '24px',
              fontWeight: 'bold',
              marginBottom: '4px',
            }}
          >
            🛒 Amazon Product Manager
          </h1>
          <p style={{ color: '#637381', fontSize: '14px' }}>
            Add Amazon products directly to your Shopify store
          </p>

          {shopifyReady && (
            <span
              style={{
                display: 'inline-block',
                marginTop: '8px',
                padding: '4px 10px',
                background: '#d4f5d4',
                color: '#008060',
                fontSize: '12px',
                borderRadius: '12px',
                fontWeight: '500',
              }}
            >
              ● Connected to Shopify
            </span>
          )}
        </div>

        {/* Add Product Form */}
        <div
          style={{
            background: 'white',
            border: '1px solid #e1e3e5',
            borderRadius: '8px',
            padding: '20px',
            marginBottom: '20px',
          }}
        >
          <h2
            style={{
              fontSize: '16px',
              fontWeight: '600',
              marginBottom: '16px',
            }}
          >
            ➕ Add New Product
          </h2>

          <form onSubmit={handleAddProduct}>
            <div style={{ marginBottom: '16px' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  marginBottom: '6px',
                  color: '#202223',
                }}
              >
                Amazon Product URL
              </label>
              <input
                type="url"
                value={amazonUrl}
                onChange={(e) => setAmazonUrl(e.target.value)}
                placeholder="https://www.amazon.com/dp/B0B2RM68G2"
                required
                disabled={isLoading}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #babfc3',
                  borderRadius: '6px',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              style={{
                background: isLoading ? '#babfc3' : '#008060',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '600',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                transition: 'background 0.2s',
              }}
            >
              {isLoading
                ? '⏳ Fetching from Amazon...'
                : '🛍️ Fetch & Add to Shopify'}
            </button>
          </form>

          {isLoading && (
            <p
              style={{
                marginTop: '12px',
                fontSize: '13px',
                color: '#637381',
              }}
            >
              This may take 20-40 seconds...
            </p>
          )}

          {message && (
            <div
              style={{
                marginTop: '12px',
                padding: '12px',
                borderRadius: '6px',
                fontSize: '14px',
                background:
                  message.type === 'success' ? '#e4f5e4' : '#fbeae5',
                color: message.type === 'success' ? '#008060' : '#d72c0d',
                border: `1px solid ${
                  message.type === 'success' ? '#aee9ae' : '#febcb3'
                }`,
              }}
            >
              {message.text}
            </div>
          )}
        </div>

        {/* Info */}
        <div
          style={{
            background: '#f6f6f7',
            borderRadius: '6px',
            padding: '16px',
            fontSize: '13px',
            color: '#637381',
          }}
        >
          <strong style={{ color: '#202223' }}>💡 How it works:</strong>
          <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
            <li>Paste any Amazon product URL</li>
            <li>Click "Fetch & Add"</li>
            <li>We fetch data from Amazon and add to your Shopify store</li>
            <li>Product appears in your Shopify Products list</li>
          </ol>
        </div>
      </div>
    </div>
  )
}

export default ShopifyApp