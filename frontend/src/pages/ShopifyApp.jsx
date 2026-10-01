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
  const [shopDomain, setShopDomain] = useState('')

  // ========================================
  // App Bridge ready check + shop domain nikalo
  // ========================================
  useEffect(() => {
    const checkShopify = setInterval(() => {
      if (window.shopify) {
        setShopifyReady(true)
        clearInterval(checkShopify)

        // Shop domain nikalo URL se
        const params = new URLSearchParams(window.location.search)
        const shop = params.get('shop')
        if (shop) {
          setShopDomain(shop)
        }

        // Toast dikhao
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
      // ========================================
      // App Bridge se ID token lein
      // ========================================
      let idToken = ''
      if (window.shopify && window.shopify.idToken) {
        idToken = await window.shopify.idToken()
      }

      if (!idToken) {
        throw new Error(
          'ID token not available. Please reload the app from Shopify Admin.'
        )
      }

      // ========================================
      // Backend par bhejein
      // ========================================
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

      // ========================================
      // Success
      // ========================================
      setMessage({
        type: 'success',
        text: `✅ ${data.message || 'Product added successfully!'}`,
      })
      setAmazonUrl('')

      // Toast dikhao
      if (window.shopify && window.shopify.toast) {
        window.shopify.toast.show('Product added successfully!')
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
        {/* ========================================
            HEADER
        ======================================== */}
        <div style={{ marginBottom: '24px' }}>
          <h1
            style={{
              fontSize: '24px',
              fontWeight: 'bold',
              marginBottom: '4px',
              color: '#202223',
            }}
          >
            🛒 Amazon Product Manager
          </h1>
          <p style={{ color: '#637381', fontSize: '14px', marginTop: '4px' }}>
            Add Amazon products directly to your Shopify store
          </p>

          {/* Status badges */}
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {shopifyReady ? (
              <span
                style={{
                  display: 'inline-block',
                  padding: '4px 12px',
                  background: '#d4f5d4',
                  color: '#008060',
                  fontSize: '12px',
                  borderRadius: '12px',
                  fontWeight: '500',
                }}
              >
                ● Connected to Shopify
              </span>
            ) : (
              <span
                style={{
                  display: 'inline-block',
                  padding: '4px 12px',
                  background: '#fef3cd',
                  color: '#8a6d3b',
                  fontSize: '12px',
                  borderRadius: '12px',
                  fontWeight: '500',
                }}
              >
                ⏳ Connecting...
              </span>
            )}

            {shopDomain && (
              <span
                style={{
                  display: 'inline-block',
                  padding: '4px 12px',
                  background: '#e1f0ff',
                  color: '#005bd3',
                  fontSize: '12px',
                  borderRadius: '12px',
                  fontWeight: '500',
                  fontFamily: 'monospace',
                }}
              >
                {shopDomain}
              </span>
            )}
          </div>
        </div>

        {/* ========================================
            ADD PRODUCT FORM
        ======================================== */}
        <div
          style={{
            background: 'white',
            border: '1px solid #e1e3e5',
            borderRadius: '8px',
            padding: '20px',
            marginBottom: '20px',
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
          }}
        >
          <h2
            style={{
              fontSize: '16px',
              fontWeight: '600',
              marginBottom: '16px',
              color: '#202223',
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
                  background: isLoading ? '#f6f6f7' : 'white',
                  color: '#202223',
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
              This may take 20-40 seconds while we fetch data from Amazon...
            </p>
          )}

          {message && (
            <div
              style={{
                marginTop: '16px',
                padding: '12px 16px',
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

        {/* ========================================
            INFO SECTION
        ======================================== */}
        <div
          style={{
            background: '#f6f6f7',
            borderRadius: '6px',
            padding: '16px',
            fontSize: '13px',
            color: '#637381',
            lineHeight: '1.6',
          }}
        >
          <strong style={{ color: '#202223' }}>💡 How it works:</strong>
          <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
            <li>Paste any Amazon product URL</li>
            <li>Click "Fetch & Add"</li>
            <li>
              We fetch title, images, price, and specs from Amazon
            </li>
            <li>Product is added to both Supabase and your Shopify store</li>
            <li>Product appears in your Shopify Products list</li>
          </ol>
        </div>

        {/* ========================================
            SECURITY NOTE
        ======================================== */}
        <div
          style={{
            marginTop: '16px',
            padding: '12px 16px',
            background: '#f0f7ff',
            border: '1px solid #c3ddf8',
            borderRadius: '6px',
            fontSize: '12px',
            color: '#005bd3',
          }}
        >
          🔒 <strong>Secure:</strong> This app uses Shopify ID tokens for
          authentication. Only users with access to this store can add products.
        </div>
      </div>
    </div>
  )
}

export default ShopifyApp