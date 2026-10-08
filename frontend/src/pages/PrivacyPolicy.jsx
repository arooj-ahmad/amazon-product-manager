// src/pages/PrivacyPolicy.jsx
export default function PrivacyPolicy() {
  return (
    <div style={{ maxWidth: '800px', margin: '40px auto', padding: '20px', fontFamily: 'Arial, sans-serif', lineHeight: '1.6' }}>
      <h1>Privacy Policy</h1>
      <p><strong>Last updated:</strong> 2026-10-08</p>

      <h2>1. Information We Collect</h2>
      <p>
        When you install Amazon Product Manager on your Shopify store, we collect:
      </p>
      <ul>
        <li>Your Shopify store domain (e.g., your-store.myshopify.com)</li>
        <li>Shopify Admin API access token (to sync products and prices)</li>
        <li>Product data (titles, prices, images, ASINs) from your Shopify store</li>
      </ul>

      <h2>2. How We Use Your Information</h2>
      <p>
        We use your information solely to:
      </p>
      <ul>
        <li>Sync Amazon product data (price, availability, images) to your Shopify store</li>
        <li>Update product prices automatically based on Amazon prices + your markup</li>
        <li>Manage your subscription via Shopify Billing API</li>
      </ul>

      <h2>3. Data Sharing</h2>
      <p>
        We do <strong>not</strong> sell, trade, or share your data with third parties.
        All data is stored securely in our database (Supabase PostgreSQL).
      </p>

      <h2>4. Data Retention</h2>
      <p>
        We retain your data as long as you use the app. When you uninstall the app,
        your data is deleted within 30 days.
      </p>

      <h2>5. Your Rights</h2>
      <p>
        You can request deletion of your data at any time by contacting us.
      </p>

      <h2>6. Contact</h2>
      <p>
        For privacy questions, contact us at: <strong>your-email@example.com</strong>
      </p>
    </div>
  )
}