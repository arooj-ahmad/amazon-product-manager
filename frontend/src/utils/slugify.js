// ============================================
// frontend/src/utils/slugify.js
// Product title se URL-safe slug banata hai
// ============================================

/**
 * Title ko URL-safe slug mein convert karta hai
 * Example: "HP Chromebook 14 Laptop, Intel!" → "hp-chromebook-14-laptop-intel"
 */
export function slugify(text) {
  if (!text) return ''

  return (
    text
      .toString()
      .toLowerCase()
      .trim()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .substring(0, 80)
      .replace(/-+$/, '')
  )
}

/**
 * Product ke liye URL path — SIRF SLUG (koi numeric ID nahi)
 * Example: productUrl({id: 12, title: "HP Chromebook"}) → "/product/hp-chromebook"
 */
export function productUrl(product) {
  if (!product) return '/'
  const slug = slugify(product.title)
  // ⚠️ Sirf slug — koi ID nahi
  return slug ? `/product/${slug}` : `/product/id/${product.id}`
}