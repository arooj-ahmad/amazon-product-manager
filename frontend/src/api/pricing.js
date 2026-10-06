// ============================================
// frontend/src/api/pricing.js
// Pricing (Markup + Country + Tax) API calls
// ============================================
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/pricing`,
  headers: { 'Content-Type': 'application/json' },
});

// Get all countries — direct data return
export const getCountries = async () => {
  const res = await api.get('/countries');
  return res.data;
};

// Get pricing for a product
export const getProductPricing = async (productId) => {
  const res = await api.get(`/product/${productId}`);
  return res.data;
};

// Update single product pricing
export const updatePricing = async (data) => {
  const res = await api.post('/update', data);
  return res.data;
};

// Bulk update all products
export const bulkUpdatePricing = async (data) => {
  const res = await api.post('/bulk-update', data);
  return res.data;
};

export default api;