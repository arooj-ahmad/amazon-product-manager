// ============================================
// frontend/src/components/ProductCard.jsx
// Amazon-style product card (clean — no dummy data)
// + Out of Stock + Low Stock tracking
// ============================================

import { Link } from 'react-router-dom'
import { productUrl } from '../utils/slugify'

function ProductCard({ product, totalVariants = 1 }) {
  // ========================================
  // Discount calculate karo
  // ========================================
  const discount =
    product.amazon_price && product.price && product.amazon_price > product.price
      ? Math.round(
          ((product.amazon_price - product.price) / product.amazon_price) * 100
        )
      : 0

  // ========================================
  // ✅ Availability checks
  // ========================================
  const isOutOfStock = product.is_available === false
  const isLowStock =
    !isOutOfStock &&
    product.availability &&
    product.availability.toLowerCase().includes('left in stock')

  return (
    <Link
      to={isOutOfStock ? '#' : productUrl(product)}
      onClick={(e) => {
        if (isOutOfStock) e.preventDefault()
      }}
      className={`group bg-white rounded-lg overflow-hidden border border-gray-200 transition-all duration-200 flex flex-col ${
        isOutOfStock ? 'opacity-90 cursor-not-allowed' : 'hover:shadow-lg'
      }`}
    >
      {/* ========================================
          IMAGE AREA
      ======================================== */}
      <div className="relative aspect-square bg-white p-4 overflow-hidden">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.title || 'Product'}
            className={`w-full h-full object-contain transition-transform duration-300 ${
              isOutOfStock
                ? 'opacity-60 grayscale'
                : 'group-hover:scale-105'
            }`}
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-300">
            <span className="text-6xl">📦</span>
          </div>
        )}

        {/* ✅ OUT OF STOCK badge */}
        {isOutOfStock && (
          <span className="absolute top-2 right-2 bg-[#cc0c39] text-white text-xs font-bold px-2 py-1 rounded shadow-md">
            OUT OF STOCK
          </span>
        )}

        {/* ✅ LOW STOCK badge */}
        {isLowStock && (
          <span className="absolute top-2 right-2 bg-orange-500 text-white text-[10px] font-bold px-2 py-1 rounded shadow-md">
            LOW STOCK
          </span>
        )}

        {/* Variants badge */}
        {totalVariants > 1 && !isOutOfStock && !isLowStock && (
          <span className="absolute top-2 left-2 bg-[#232f3e] text-white text-[10px] font-medium px-2 py-0.5 rounded">
            {totalVariants} variants
          </span>
        )}

        {/* Discount badge */}
        {discount > 0 && !isOutOfStock && (
          <span className="absolute top-2 left-2 bg-[#cc0c39] text-white text-xs font-bold px-2 py-1 rounded">
            -{discount}%
          </span>
        )}
      </div>

      {/* ========================================
          INFO AREA
      ======================================== */}
      <div className="p-3 flex flex-col flex-1">
        {/* Brand */}
        {product.brand && (
          <p className="text-xs text-[#007185] font-medium mb-1 truncate group-hover:text-[#c7511f] transition-colors">
            {product.brand}
          </p>
        )}

        {/* Title */}
        <h3 className="text-sm text-[#0f1111] line-clamp-2 mb-2 leading-snug min-h-[2.5rem] group-hover:text-[#c7511f] transition-colors">
          {product.title || 'Untitled Product'}
        </h3>

        {/* ✅ Availability text */}
        {product.availability && (
          <p
            className={`text-xs mb-2 ${
              isOutOfStock
                ? 'text-red-600 font-medium'
                : isLowStock
                ? 'text-orange-600 font-medium'
                : 'text-[#007185]'
            }`}
          >
            {product.availability}
          </p>
        )}

        {/* Price */}
        <div className="mt-auto">
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold text-[#0f1111]">
              ${product.price?.toFixed(2) || '0.00'}
            </span>
            {discount > 0 && !isOutOfStock && (
              <span className="text-xs text-gray-500 line-through">
                ${product.amazon_price?.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {/* CTA Button */}
        <button
          type="button"
          disabled={isOutOfStock}
          onClick={(e) => {
            e.preventDefault()
            if (!isOutOfStock) {
              window.location.href = productUrl(product)
            }
          }}
          className={`mt-3 w-full text-sm font-medium py-2 rounded-full transition-colors ${
            isOutOfStock
              ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
              : 'bg-[#ffd814] hover:bg-[#f7ca00] text-[#0f1111]'
          }`}
        >
          {isOutOfStock ? 'Out of Stock' : 'See Options'}
        </button>
      </div>
    </Link>
  )
}

export default ProductCard