// ============================================
// frontend/src/api/pricing.js
// Pricing (Markup + Country + Tax) API calls
// + ✅ NAYA: Markup endpoints use karo (Shopify update ke saath)
// ============================================
import axios from 'axios';

const API_URL =
  (import.meta.env.VITE_API_URL || '').trim() ||
  'https://amazon-product-manager-production.up.railway.app';

// Countries ke liye — pricing API
const pricingApi = axios.create({
  baseURL: `${API_URL}/api/pricing`,
  headers: { 'Content-Type': 'application/json' },
});

// Markup update ke liye — markup API (Shopify update karta hai)
const markupApi = axios.create({
  baseURL: `${API_URL}/api/markup`,
  headers: { 'Content-Type': 'application/json' },
});

// ============================================
// Get all countries
// ============================================
export const getCountries = async () => {
  const res = await pricingApi.get('/countries');
  return res.data;
};

// ============================================
// Get pricing for a product
// ============================================
export const getProductPricing = async (productId) => {
  const res = await pricingApi.get(`/product/${productId}`);
  return res.data;
};

// ============================================
// ✅ NAYA: Update single product pricing
// Ab /api/markup/{id} use karo — Shopify bhi update hoga
// ============================================
export const updatePricing = async (data) => {
  const res = await markupApi.patch(`/${data.product_id}`, {
    markup: data.markup_value,
    markup_type: data.markup_type,
  });
  return res.data;
};

// ============================================
// ✅ NAYA: Bulk update all products
// Ab /api/markup/bulk-update use karo — Shopify bhi update hoga
// ============================================
export const bulkUpdatePricing = async (data) => {
  let url = '/bulk-update';
  if (data.store_id) {
    url += `?store_id=${data.store_id}`;
  }
  const res = await markupApi.post(url, {
    markup: data.markup_value,
    markup_type: data.markup_type,
  });
  return res.data;
};

export default pricingApi;