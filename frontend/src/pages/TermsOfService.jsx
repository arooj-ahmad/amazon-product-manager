// src/pages/TermsOfService.jsx
export default function TermsOfService() {
  return (
    <div style={{ maxWidth: '800px', margin: '40px auto', padding: '20px', fontFamily: 'Arial, sans-serif', lineHeight: '1.6' }}>
      <h1>Terms of Service</h1>
      <p><strong>Last updated:</strong> 2026-10-08</p>

      <h2>1. Acceptance of Terms</h2>
      <p>
        By installing and using Amazon Product Manager, you agree to these Terms of Service.
      </p>

      <h2>2. Service Description</h2>
      <p>
        Amazon Product Manager is a Shopify app that:
      </p>
      <ul>
        <li>Imports Amazon products to your Shopify store</li>
        <li>Automatically updates prices based on Amazon prices + your markup</li>
        <li>Tracks availability (In Stock / Out of Stock)</li>
      </ul>

      <h2>3. Subscription & Billing</h2>
      <p>
        The app offers paid plans via Shopify Billing API. Charges are added to your
        Shopify invoice. You can cancel anytime from your Shopify admin.
      </p>

      <h2>4. Acceptable Use</h2>
      <p>
        You agree not to misuse the app, including:
      </p>
      <ul>
        <li>Using the app for illegal purposes</li>
        <li>Attempting to reverse-engineer the app</li>
        <li>Reselling the app without permission</li>
      </ul>

      <h2>5. Limitation of Liability</h2>
      <p>
        We are not liable for any losses resulting from the use of this app,
        including price changes or product sync errors.
      </p>

      <h2>6. Changes to Terms</h2>
      <p>
        We may update these terms. Continued use of the app means you accept the new terms.
      </p>

      <h2>7. Contact</h2>
      <p>
        For questions, contact us at: <strong>your-email@example.com</strong>
      </p>
    </div>
  )
}