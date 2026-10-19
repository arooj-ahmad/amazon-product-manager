// ============================================
// frontend/src/api/products.js
// Product se related saari API calls
// + ✅ NAYA: deleteProduct (Shopify + DB delete)
// ============================================
import api from './axios'


// ============================================
// PUBLIC ENDPOINTS (User side)
// ============================================

export const getAllProducts = async () => {
  const response = await api.get('/api/products')
  return response.data
}

export const getProductById = async (id) => {
  const response = await api.get(`/api/products/${id}`)
  return response.data
}

export const getProductBySlug = async (slug) => {
  const response = await api.get(`/api/products/slug/${slug}`)
  return response.data
}

export const getProductVariants = async (id) => {
  const response = await api.get(`/api/products/${id}/variants`)
  return response.data
}

export const getProductAvailability = async (id) => {
  const response = await api.get(`/api/products/${id}/availability`)
  return response.data
}


// ============================================
// ADMIN ENDPOINTS (Protected)
// ============================================

export const getAllProductsFlat = async () => {
  const response = await api.get('/api/admin/products')
  return response.data
}

export const adminLogin = async (username, password) => {
  const response = await api.post('/api/token', { username, password })
  return response.data
}

export const adminFetchProduct = async (amazonUrl) => {
  const response = await api.post('/api/admin/fetch', { amazon_url: amazonUrl })
  return response.data
}

// ✅ NAYA: DELETE PRODUCT
export const deleteProduct = async (productId) => {
  const response = await api.delete(`/api/admin/products/${productId}`)
  return response.data
}

// ✅ UPDATE PRODUCT
export const updateProduct = async (productId, data) => {
  const response = await api.put(`/api/admin/products/${productId}`, data)
  return response.data
}


// ============================================
// SHOPIFY ENDPOINTS
// ============================================

export const adminPushToShopify = async (productId, shopDomain) => {
  const response = await api.post(`/api/shopify/push-product/${productId}`, {
    shop_domain: shopDomain,
  })
  return response.data
}

export const getShopifyStores = async () => {
  const response = await api.get('/api/shopify/stores')
  return response.data
}