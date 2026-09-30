// ============================================
// frontend/src/api/products.js
// Product se related saari API calls
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

export const adminUpdateProduct = async (id, updates) => {
  const response = await api.put(`/api/admin/products/${id}`, updates)
  return response.data
}

export const adminDeleteProduct = async (id) => {
  const response = await api.delete(`/api/admin/products/${id}`)
  return response.data
}

// ============================================
// SHOPIFY ENDPOINTS
// ============================================

/**
 * Product ko Shopify mein push karo
 */
export const adminPushToShopify = async (productId, shopDomain) => {
  const response = await api.post(`/api/shopify/push-product/${productId}`, {
    shop_domain: shopDomain,
  })
  return response.data
}

/**
 * Connected Shopify stores list karo
 */
export const getShopifyStores = async () => {
  const response = await api.get('/api/shopify/stores')
  return response.data
}