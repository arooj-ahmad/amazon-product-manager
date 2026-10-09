// ============================================
// frontend/src/api/pricing.js
// Pricing (Markup + Country + Tax) API calls
// + ✅ NAYA: Store ID database se nikaalo
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
// ✅ NAYA: Shop domain se store ID nikaalo
// ============================================
export const getStoreIdByDomain = async (shop) => {
  const res = await fetch(
    `${API_URL}/api/shopify/store-id?shop=${encodeURIComponent(shop)}`
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Store not found');
  }
  const data = await res.json();
  return data.store_id;
};

// ============================================
// Update single product pricing
// ============================================
export const updatePricing = async (data) => {
  const res = await markupApi.patch(`/${data.product_id}`, {
    markup: data.markup_value,
    markup_type: data.markup_type,
  });
  return res.data;
};

// ============================================
// Bulk update all products
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