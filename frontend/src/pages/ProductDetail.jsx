// ============================================
// frontend/src/pages/ProductDetail.jsx
// Product detail — clean (no dummy data)
// + Real-time availability check (Storefront API)
// + Add to Cart / Buy Now buttons
// ============================================

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getProductById,
  getProductBySlug,
  getProductVariants,
  getProductAvailability,
} from '../api/products'

function ProductDetail() {
  const { slug, id } = useParams()
  const [product, setProduct] = useState(null)
  const [variants, setVariants] = useState([])
  const [selectedVariantId, setSelectedVariantId] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedImage, setSelectedImage] = useState(null)
  const [activeTab, setActiveTab] = useState('description')

  // ✅ NAYA — Availability state
  const [availability, setAvailability] = useState(null)
  const [checkingAvailability, setCheckingAvailability] = useState(false)

  // Product + variants fetch
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true)

        let data
        if (slug) {
          data = await getProductBySlug(slug)
        } else if (id) {
          data = await getProductById(id)
        } else {
          throw new Error('Product identifier missing')
        }

        setProduct(data)
        setSelectedImage(data.image_url || data.images?.[0] || null)
        setSelectedVariantId(data.id)

        try {
          const variantsData = await getProductVariants(data.id)
          setVariants(variantsData)
        } catch (err) {
          console.warn('Variants fetch fail:', err)
          setVariants([data])
        }
      } catch (err) {
        console.error('Product fetch fail:', err)
        setError(
          err.response?.status === 404
            ? 'Product not found'
            : 'Failed to load product'
        )
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [slug, id])

  // ✅ NAYA — Availability check (jab bhi product ya variant change ho)
  useEffect(() => {
    if (!product?.id) return

    const checkAvail = async () => {
      setCheckingAvailability(true)
      try {
        const data = await getProductAvailability(product.id)
        setAvailability(data)
      } catch (err) {
        console.error('Availability check fail:', err)
        setAvailability(null)
      } finally {
        setCheckingAvailability(false)
      }
    }

    checkAvail()
  }, [product?.id])

  // Variant change
  const handleVariantChange = async (variantId) => {
    if (variantId === selectedVariantId) return

    try {
      setSelectedVariantId(variantId)
      const data = await getProductById(variantId)
      setProduct(data)
      setSelectedImage(data.image_url || data.images?.[0] || null)
      // Availability will re-fetch automatically due to useEffect [product?.id]
    } catch (err) {
      console.error('Variant fetch fail:', err)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="text-center">
          <div className="inline-block w-12 h-12 border-4 border-[#ff9900] border-t-transparent rounded-full animate-spin-slow"></div>
          <p className="mt-4 text-gray-600">Loading product...</p>
        </div>
      </div>
    )
  }

  if (error || !product) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 text-center">
        <p className="text-6xl mb-4">😕</p>
        <h2 className="text-2xl font-bold text-gray-800 mb-4">
          {error || 'Product not found'}
        </h2>
        <Link
          to="/"
          className="inline-block bg-[#ff9900] hover:bg-[#e88b00] text-[#0f1111] font-medium px-6 py-3 rounded-lg transition-colors"
        >
          ← Back to Home
        </Link>
      </div>
    )
  }

  const allImages =
    product.images && product.images.length > 0
      ? product.images
      : product.image_url
      ? [product.image_url]
      : []

  const specs = product.specifications || {}
  const specEntries = Object.entries(specs)
  const hasMultipleVariants = variants.length > 1

  // ✅ NAYA — Availability derived values
  const isAvailable = availability?.available !== false
  const showAvailability =
    availability && !checkingAvailability && !isLoading

  return (
    <div className="min-h-screen bg-white">
      {/* Breadcrumbs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
        <nav className="flex items-center gap-2 text-xs text-gray-600">
          <Link to="/" className="hover:text-[#c7511f] hover:underline">
            Home
          </Link>
          <span>›</span>
          {product.brand && (
            <>
              <span className="hover:text-[#c7511f] hover:underline cursor-pointer">
                {product.brand}
              </span>
              <span>›</span>
            </>
          )}
          <span className="text-gray-800 truncate max-w-md">
            {product.title?.substring(0, 50)}
            {product.title?.length > 50 ? '...' : ''}
          </span>
        </nav>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
        {/* MAIN LAYOUT */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
          {/* Thumbnails */}
          {allImages.length > 1 && (
            <div className="lg:col-span-1 order-2 lg:order-1">
              <div className="flex lg:flex-col gap-2 overflow-x-auto lg:overflow-visible pb-2 lg:pb-0">
                {allImages.map((img, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onMouseEnter={() => setSelectedImage(img)}
                    onClick={() => setSelectedImage(img)}
                    className={`flex-shrink-0 w-14 h-14 lg:w-12 lg:h-12 rounded border-2 bg-white overflow-hidden transition-all ${
                      selectedImage === img
                        ? 'border-[#007185] shadow-md'
                        : 'border-gray-200 hover:border-[#007185]'
                    }`}
                  >
                    <img
                      src={img}
                      alt={`view ${idx + 1}`}
                      className="w-full h-full object-contain p-1"
                      loading="lazy"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Main Image */}
          <div
            className={`${
              allImages.length > 1 ? 'lg:col-span-5' : 'lg:col-span-6'
            } order-1 lg:order-2`}
          >
            <div className="sticky top-20">
              <div className="aspect-square bg-white rounded-lg overflow-hidden flex items-center justify-center">
                {selectedImage ? (
                  <img
                    src={selectedImage}
                    alt={product.title}
                    className="w-full h-full object-contain hover:scale-110 transition-transform duration-300 cursor-zoom-in"
                  />
                ) : (
                  <span className="text-8xl text-gray-300">📦</span>
                )}
              </div>
            </div>
          </div>

          {/* Details */}
          <div className="lg:col-span-6 order-3">
            {/* Brand */}
            {product.brand && (
              <p className="text-sm text-[#007185] font-medium">
                {product.brand}
              </p>
            )}

            {/* Title */}
            <h1 className="text-xl sm:text-2xl text-[#0f1111] font-medium mt-1 mb-3 leading-snug">
              {product.title || 'Untitled Product'}
            </h1>

            {/* Price Section */}
            <div className="mb-4 py-3 border-t border-b border-gray-200">
              <div className="flex items-baseline gap-2">
                <span className="text-sm text-gray-600">Price:</span>
                <span className="text-3xl font-normal text-[#0f1111]">
                  <sup className="text-lg">$</sup>
                  {Math.floor(product.price || 0)}
                  <sup className="text-lg">
                    .{((product.price || 0) % 1).toFixed(2).substring(2)}
                  </sup>
                </span>
              </div>
              {product.amazon_price && product.amazon_price > product.price && (
                <p className="text-xs text-gray-600 mt-1">
                  List Price:{' '}
                  <span className="line-through">
                    ${product.amazon_price.toFixed(2)}
                  </span>{' '}
                  — You save ${(product.amazon_price - product.price).toFixed(2)}
                </p>
              )}
            </div>

            {/* ✅ NAYA — Stock Status Banner */}
            {showAvailability && (
              <p
                className={`text-sm font-medium mb-4 ${
                  isAvailable ? 'text-green-700' : 'text-red-700'
                }`}
              >
                {isAvailable
                  ? `● In Stock${
                      availability.quantity
                        ? ` (${availability.quantity} available)`
                        : ''
                    }`
                  : '● Currently Out of Stock'}
              </p>
            )}

            {/* ✅ NAYA — Add to Cart / Buy Now Buttons */}
            <div className="space-y-3 mb-6">
              <button
                type="button"
                disabled={!isAvailable || checkingAvailability}
                className={`w-full font-medium py-3 rounded-full transition-colors ${
                  !isAvailable || checkingAvailability
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-[#ffd814] hover:bg-[#f7ca00] text-[#0f1111]'
                }`}
              >
                {checkingAvailability
                  ? '⏳ Checking...'
                  : !isAvailable
                  ? '❌ Out of Stock'
                  : '🛒 Add to Cart'}
              </button>

              <button
                type="button"
                disabled={!isAvailable || checkingAvailability}
                className={`w-full font-medium py-3 rounded-full transition-colors ${
                  !isAvailable || checkingAvailability
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-[#ffa41c] hover:bg-[#fa8900] text-[#0f1111]'
                }`}
              >
                {!isAvailable ? 'Out of Stock' : '⚡ Buy Now'}
              </button>
            </div>

            {/* Variant Selector */}
            {hasMultipleVariants && (
              <div className="mb-4 pb-4 border-b border-gray-200">
                <p className="text-sm font-bold text-[#0f1111] mb-3">
                  {variants.length} options available
                </p>
                <div className="flex flex-wrap gap-2">
                  {variants.map((variant) => (
                    <button
                      key={variant.id}
                      type="button"
                      onClick={() => handleVariantChange(variant.id)}
                      className={`px-3 py-2 rounded border-2 text-xs font-medium transition-all ${
                        selectedVariantId === variant.id
                          ? 'border-[#007185] bg-[#e7f4f5] text-[#0f1111]'
                          : 'border-gray-300 bg-white text-gray-700 hover:border-[#007185]'
                      }`}
                      title={variant.title}
                    >
                      {variant.title?.substring(0, 25) || 'Variant'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Badges */}
            <div className="flex flex-wrap gap-2 mb-4">
              {product.is_manual_override && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-3 py-1 rounded">
                  Custom Price
                </span>
              )}
            </div>

            {/* About this item */}
            {product.description && (
              <div className="mb-6">
                <h3 className="text-base font-bold text-[#0f1111] mb-2">
                  About this item
                </h3>
                <p className="text-sm text-[#0f1111] leading-relaxed line-clamp-5 whitespace-pre-line">
                  {product.description}
                </p>
              </div>
            )}

            {/* ASIN */}
            <div className="text-xs text-gray-600 pt-3 border-t border-gray-200">
              <span className="font-bold">ASIN:</span>{' '}
              <span className="font-mono">{product.asin}</span>
              {product.parent_asin && (
                <>
                  {' '}| <span className="font-bold">Parent:</span>{' '}
                  <span className="font-mono">{product.parent_asin}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* TABS SECTION */}
        <div className="mt-12 border-t-2 border-gray-200 pt-6">
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setActiveTab('description')}
              className={`px-6 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === 'description'
                  ? 'border-[#e77600] text-[#c7511f]'
                  : 'border-transparent text-gray-600 hover:text-[#c7511f]'
              }`}
            >
              Description
            </button>
            <button
              onClick={() => setActiveTab('specifications')}
              className={`px-6 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === 'specifications'
                  ? 'border-[#e77600] text-[#c7511f]'
                  : 'border-transparent text-gray-600 hover:text-[#c7511f]'
              }`}
            >
              Specifications
            </button>
          </div>

          <div className="py-6">
            {activeTab === 'description' && (
              <div>
                {product.description ? (
                  <div className="text-sm text-[#0f1111] leading-relaxed whitespace-pre-line max-w-4xl">
                    {product.description}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">
                    No description available.
                  </p>
                )}
              </div>
            )}

            {activeTab === 'specifications' && (
              <div>
                {specEntries.length > 0 ? (
                  <div className="max-w-3xl border border-gray-200 rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <tbody>
                        {specEntries.map(([key, value], idx) => (
                          <tr
                            key={key}
                            className={
                              idx % 2 === 0 ? 'bg-gray-50' : 'bg-white'
                            }
                          >
                            <td className="px-4 py-3 font-medium text-[#0f1111] w-1/3 align-top border-r border-gray-200">
                              {key}
                            </td>
                            <td className="px-4 py-3 text-[#0f1111]">
                              {value}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">
                    No specifications available.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProductDetail