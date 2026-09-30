// ============================================
// frontend/src/pages/admin/Dashboard.jsx
// Admin dashboard — grouped products + Shopify push
// ============================================

import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  getAllProductsFlat,
  adminFetchProduct,
  adminDeleteProduct,
  adminPushToShopify,
  getShopifyStores,
} from '../../api/products'

function Dashboard() {
  const [products, setProducts] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [amazonUrl, setAmazonUrl] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [addMessage, setAddMessage] = useState(null)
  const [searchFilter, setSearchFilter] = useState('')
  const [expandedGroups, setExpandedGroups] = useState({})
  const [shopifyStore, setShopifyStore] = useState(null)
  const [pushingProduct, setPushingProduct] = useState(null)

  // ========================================
  // Load products
  // ========================================
  const loadProducts = async () => {
    try {
      setIsLoading(true)
      const data = await getAllProductsFlat()
      setProducts(data.products || [])
      setError(null)
    } catch (err) {
      console.error('Dashboard load fail:', err)
      setError('Failed to load products')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadProducts()
  }, [])

  // ========================================
  // Load Shopify store
  // ========================================
  useEffect(() => {
    const loadStore = async () => {
      try {
        const data = await getShopifyStores()
        if (data.stores && data.stores.length > 0) {
          setShopifyStore(data.stores[0].shop_domain)
        }
      } catch (err) {
        console.warn('Shopify store not connected:', err)
      }
    }
    loadStore()
  }, [])

  // ========================================
  // Add product
  // ========================================
  const handleAddProduct = async (e) => {
    e.preventDefault()
    if (!amazonUrl.trim()) return

    setIsAdding(true)
    setAddMessage(null)

    try {
      const result = await adminFetchProduct(amazonUrl.trim())
      setAddMessage({
        type: 'success',
        text: `✅ ${result.message}`,
      })
      setAmazonUrl('')
      await loadProducts()
    } catch (err) {
      setAddMessage({
        type: 'error',
        text: `❌ ${err.response?.data?.detail || 'Failed to add product'}`,
      })
    } finally {
      setIsAdding(false)
    }
  }

  // ========================================
  // Delete
  // ========================================
  const handleDelete = async (id, title) => {
    if (!confirm(`Delete "${title}"? This action cannot be undone.`)) return

    try {
      await adminDeleteProduct(id)
      await loadProducts()
    } catch (err) {
      alert('Delete failed: ' + (err.response?.data?.detail || err.message))
    }
  }

  // ========================================
  // Shopify Push
  // ========================================
  const handlePushToShopify = async (productId, title) => {
    if (!shopifyStore) {
      alert('Shopify store not connected! Please install the app first.')
      return
    }

    setPushingProduct(productId)

    try {
      const result = await adminPushToShopify(productId, shopifyStore)
      alert(`✅ "${title}" pushed to Shopify successfully!`)
    } catch (err) {
      const errorMsg =
        err.response?.data?.detail || 'Failed to push to Shopify'
      alert(`❌ Push failed: ${errorMsg}`)
    } finally {
      setPushingProduct(null)
    }
  }

  // Toggle group
  const toggleGroup = (groupKey) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }))
  }

  // ========================================
  // GROUP PRODUCTS
  // ========================================
  const groupedProducts = useMemo(() => {
    const groups = {}

    products.forEach((p) => {
      const groupKey = p.parent_asin || p.asin

      if (!groups[groupKey]) {
        groups[groupKey] = {
          groupKey,
          parent: null,
          variants: [],
        }
      }

      if (p.parent_asin === null || p.parent_asin === undefined) {
        groups[groupKey].parent = p
      } else {
        if (!groups[groupKey].parent) {
          groups[groupKey].parent = p
        } else {
          groups[groupKey].variants.push(p)
        }
      }
    })

    Object.values(groups).forEach((g) => {
      if (!g.parent) {
        g.parent = g.variants.shift()
      }
    })

    return Object.values(groups).filter((g) => g.parent)
  }, [products])

  // Filter groups
  const filteredGroups = useMemo(() => {
    if (!searchFilter.trim()) return groupedProducts
    const q = searchFilter.toLowerCase()

    return groupedProducts.filter((g) => {
      const allItems = [g.parent, ...g.variants]
      return allItems.some(
        (p) =>
          (p.title || '').toLowerCase().includes(q) ||
          (p.asin || '').toLowerCase().includes(q) ||
          (p.brand || '').toLowerCase().includes(q)
      )
    })
  }, [groupedProducts, searchFilter])

  // Stats
  const totalProducts = products.length
  const totalGroups = groupedProducts.length
  const variations = products.filter((p) => p.is_variation).length
  const manualOverrides = products.filter((p) => p.is_manual_override).length

  return (
    <div className="min-h-screen bg-[#eaeded]">
      {/* HEADER */}
      <div className="bg-gradient-to-b from-[#232f3e] to-[#37475a] text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">
                Admin Dashboard
              </h1>
              <p className="text-sm text-gray-300 mt-1">
                Manage products — add, edit, delete
                {shopifyStore && (
                  <span className="ml-2 inline-flex items-center gap-1 text-xs bg-green-500/20 text-green-300 px-2 py-0.5 rounded-full">
                    <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
                    Shopify: {shopifyStore.split('.')[0]}
                  </span>
                )}
              </p>
            </div>
            <Link
              to="/"
              className="inline-flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded text-sm font-medium transition-colors self-start sm:self-auto"
            >
              🏠 View Store
            </Link>
          </div>
        </div>
      </div>

      {/* STATS CARDS */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-6 sm:-mt-8 relative z-10">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-[#ff9900]">
            <p className="text-xs text-gray-600 uppercase tracking-wide font-medium mb-1">
              Groups
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-[#0f1111]">
              {totalGroups}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-blue-500">
            <p className="text-xs text-gray-600 uppercase tracking-wide font-medium mb-1">
              Total Items
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-[#0f1111]">
              {totalProducts}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-purple-500">
            <p className="text-xs text-gray-600 uppercase tracking-wide font-medium mb-1">
              Variations
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-[#0f1111]">
              {variations}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-4 border-l-4 border-yellow-500">
            <p className="text-xs text-gray-600 uppercase tracking-wide font-medium mb-1">
              Manual
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-[#0f1111]">
              {manualOverrides}
            </p>
          </div>
        </div>
      </div>

      {/* ADD PRODUCT FORM */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <div className="bg-white rounded-lg shadow-md p-4 sm:p-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xl">➕</span>
            <h2 className="text-lg font-bold text-[#0f1111]">
              Add New Product
            </h2>
          </div>

          <form
            onSubmit={handleAddProduct}
            className="flex flex-col sm:flex-row gap-3"
          >
            <input
              type="url"
              value={amazonUrl}
              onChange={(e) => setAmazonUrl(e.target.value)}
              placeholder="https://www.amazon.com/dp/B0B2RM68G2"
              required
              disabled={isAdding}
              className="flex-1 px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-[#ff9900] focus:ring-2 focus:ring-[#ff9900]/30 focus:outline-none transition-all disabled:bg-gray-100 text-sm"
            />
            <button
              type="submit"
              disabled={isAdding}
              className="bg-[#ffd814] hover:bg-[#f7ca00] disabled:bg-gray-300 disabled:cursor-not-allowed text-[#0f1111] font-medium px-6 py-3 rounded-full transition-colors whitespace-nowrap"
            >
              {isAdding ? '⏳ Fetching...' : 'Fetch & Add'}
            </button>
          </form>

          {isAdding && (
            <p className="text-xs text-gray-500 mt-2 flex items-center gap-2">
              <span className="inline-block w-2 h-2 bg-[#ff9900] rounded-full animate-pulse"></span>
              Fetching data from Amazon via Bright Data — this may take 20-40
              seconds...
            </p>
          )}

          {addMessage && (
            <div
              className={`mt-3 px-4 py-3 rounded text-sm ${
                addMessage.type === 'success'
                  ? 'bg-green-50 text-green-800 border border-green-200'
                  : 'bg-red-50 text-red-800 border border-red-200'
              }`}
            >
              {addMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* PRODUCTS TABLE */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
        <div className="bg-white rounded-lg shadow-md overflow-hidden">
          {/* Table Header */}
          <div className="px-4 sm:px-6 py-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <h2 className="text-lg font-bold text-[#0f1111] flex items-center gap-2">
              📦 Products
              <span className="text-sm font-normal text-gray-500">
                ({filteredGroups.length} groups)
              </span>
            </h2>

            <div className="relative w-full sm:w-64">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="w-4 h-4 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Filter products..."
                className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg focus:border-[#ff9900] focus:ring-2 focus:ring-[#ff9900]/30 focus:outline-none text-sm"
              />
            </div>
          </div>

          {isLoading ? (
            <div className="p-12 text-center">
              <div className="inline-block w-10 h-10 border-4 border-[#ff9900] border-t-transparent rounded-full animate-spin-slow"></div>
              <p className="mt-3 text-gray-600 text-sm">Loading...</p>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-600 text-sm">{error}</div>
          ) : products.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <p className="text-5xl mb-3">📭</p>
              <p className="text-sm">
                No products yet. Add one using the URL above.
              </p>
            </div>
          ) : filteredGroups.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <p className="text-5xl mb-3">🔍</p>
              <p className="text-sm">No results for "{searchFilter}"</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">
                      Product
                    </th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">
                      ASIN
                    </th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">
                      Amazon
                    </th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">
                      Website
                    </th>
                    <th className="px-4 sm:px-6 py-3 text-right text-xs font-bold text-gray-600 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredGroups.map((group) => {
                    const hasVariants = group.variants.length > 0
                    const isExpanded = expandedGroups[group.groupKey]

                    return (
                      <>
                        {/* Parent row */}
                        <tr
                          key={group.parent.id}
                          className="hover:bg-gray-50 transition-colors border-l-4 border-[#ff9900]"
                        >
                          <td className="px-4 sm:px-6 py-4">
                            <div className="flex items-center gap-3">
                              {hasVariants ? (
                                <button
                                  onClick={() => toggleGroup(group.groupKey)}
                                  className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded hover:bg-gray-200 transition-colors text-gray-600 font-bold"
                                  title={
                                    isExpanded
                                      ? 'Hide variants'
                                      : 'Show variants'
                                  }
                                >
                                  {isExpanded ? '▼' : '▶'}
                                </button>
                              ) : (
                                <span className="w-6 h-6 flex-shrink-0"></span>
                              )}
                              <div className="w-12 h-12 bg-gray-50 rounded border border-gray-200 overflow-hidden flex-shrink-0">
                                {group.parent.image_url ? (
                                  <img
                                    src={group.parent.image_url}
                                    alt={group.parent.title}
                                    className="w-full h-full object-contain p-1"
                                  />
                                ) : (
                                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                                    📦
                                  </div>
                                )}
                              </div>
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-[#0f1111] line-clamp-2 max-w-xs">
                                  {group.parent.title || 'Untitled'}
                                </p>
                                <div className="flex items-center gap-2 mt-0.5">
                                  {group.parent.brand && (
                                    <p className="text-xs text-[#007185]">
                                      {group.parent.brand}
                                    </p>
                                  )}
                                  {hasVariants && (
                                    <span className="text-[10px] bg-purple-100 text-purple-800 px-2 py-0.5 rounded-full font-medium">
                                      {group.variants.length} variant
                                      {group.variants.length !== 1 ? 's' : ''}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 sm:px-6 py-4 text-xs text-gray-600 font-mono">
                            {group.parent.asin}
                          </td>
                          <td className="px-4 sm:px-6 py-4 text-sm text-gray-600">
                            ${group.parent.amazon_price?.toFixed(2) || '—'}
                          </td>
                          <td className="px-4 sm:px-6 py-4">
                            <span className="text-sm font-bold text-[#0f1111]">
                              ${group.parent.price?.toFixed(2) || '—'}
                            </span>
                            {group.parent.is_manual_override && (
                              <span className="ml-2 text-[10px] bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-medium">
                                Manual
                              </span>
                            )}
                          </td>
                          <td className="px-4 sm:px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-1 sm:gap-2">
                              {shopifyStore && (
                                <button
                                  onClick={() =>
                                    handlePushToShopify(
                                      group.parent.id,
                                      group.parent.title
                                    )
                                  }
                                  disabled={pushingProduct === group.parent.id}
                                  className="text-[#008060] hover:text-[#004c3f] hover:underline text-sm font-medium px-2 py-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                  title="Push to Shopify"
                                >
                                  {pushingProduct === group.parent.id
                                    ? '⏳'
                                    : '🛍️ Push'}
                                </button>
                              )}
                              <Link
                                to={`/admin/edit/${group.parent.id}`}
                                className="text-[#007185] hover:text-[#c7511f] hover:underline text-sm font-medium px-2 py-1 transition-colors"
                              >
                                Edit
                              </Link>
                              <button
                                onClick={() =>
                                  handleDelete(
                                    group.parent.id,
                                    group.parent.title
                                  )
                                }
                                className="text-red-600 hover:text-red-800 hover:underline text-sm font-medium px-2 py-1 transition-colors"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* Variant rows */}
                        {hasVariants &&
                          isExpanded &&
                          group.variants.map((variant) => (
                            <tr
                              key={variant.id}
                              className="hover:bg-blue-50/50 transition-colors bg-gray-50/40"
                            >
                              <td className="px-4 sm:px-6 py-3">
                                <div className="flex items-center gap-3 pl-9">
                                  <span className="text-gray-400 text-sm">
                                    ↳
                                  </span>
                                  <div className="w-10 h-10 bg-white rounded border border-gray-200 overflow-hidden flex-shrink-0">
                                    {variant.image_url ? (
                                      <img
                                        src={variant.image_url}
                                        alt={variant.title}
                                        className="w-full h-full object-contain p-0.5"
                                      />
                                    ) : (
                                      <div className="w-full h-full flex items-center justify-center text-gray-300 text-xs">
                                        📦
                                      </div>
                                    )}
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-xs text-gray-700 line-clamp-2 max-w-xs">
                                      {variant.title || 'Untitled'}
                                    </p>
                                    {variant.brand &&
                                      variant.brand !==
                                        group.parent.brand && (
                                        <p className="text-[10px] text-gray-500">
                                          {variant.brand}
                                        </p>
                                      )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-4 sm:px-6 py-3 text-xs text-gray-500 font-mono">
                                {variant.asin}
                              </td>
                              <td className="px-4 sm:px-6 py-3 text-xs text-gray-500">
                                ${variant.amazon_price?.toFixed(2) || '—'}
                              </td>
                              <td className="px-4 sm:px-6 py-3">
                                <span className="text-xs font-semibold text-gray-700">
                                  ${variant.price?.toFixed(2) || '—'}
                                </span>
                                {variant.is_manual_override && (
                                  <span className="ml-2 text-[10px] bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full font-medium">
                                    Manual
                                  </span>
                                )}
                              </td>
                              <td className="px-4 sm:px-6 py-3 text-right">
                                <div className="flex items-center justify-end gap-1 sm:gap-2">
                                  {shopifyStore && (
                                    <button
                                      onClick={() =>
                                        handlePushToShopify(
                                          variant.id,
                                          variant.title
                                        )
                                      }
                                      disabled={pushingProduct === variant.id}
                                      className="text-[#008060] hover:text-[#004c3f] hover:underline text-xs font-medium px-2 py-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                      title="Push to Shopify"
                                    >
                                      {pushingProduct === variant.id
                                        ? '⏳'
                                        : '🛍️ Push'}
                                    </button>
                                  )}
                                  <Link
                                    to={`/admin/edit/${variant.id}`}
                                    className="text-[#007185] hover:text-[#c7511f] hover:underline text-xs font-medium px-2 py-1 transition-colors"
                                  >
                                    Edit
                                  </Link>
                                  <button
                                    onClick={() =>
                                      handleDelete(
                                        variant.id,
                                        variant.title
                                      )
                                    }
                                    className="text-red-600 hover:text-red-800 hover:underline text-xs font-medium px-2 py-1 transition-colors"
                                  >
                                    Delete
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                      </>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard