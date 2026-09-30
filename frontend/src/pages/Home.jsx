// ============================================
// frontend/src/pages/Home.jsx
// Home page — Amazon style, clean
// ============================================

import { useEffect, useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getAllProducts } from '../api/products'
import ProductCard from '../components/ProductCard'

function Home() {
  const [searchParams] = useSearchParams()
  const [groups, setGroups] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  // URL se search query
  const searchQuery = searchParams.get('q') || ''

  // Products fetch
  useEffect(() => {
    const fetchProducts = async () => {
      try {
        setIsLoading(true)
        const data = await getAllProducts()
        setGroups(data.groups || [])
      } catch (err) {
        console.error('Products fetch fail:', err)
        setError(
          err.response?.data?.detail ||
            'Products load nahi ho paye. Backend chal raha hai?'
        )
      } finally {
        setIsLoading(false)
      }
    }

    fetchProducts()
  }, [])

  // Filter (sirf search)
  const filteredGroups = useMemo(() => {
    if (!searchQuery) return groups
    const query = searchQuery.toLowerCase().trim()
    return groups.filter((g) => {
      const product = g.parent_product
      const title = (product.title || '').toLowerCase()
      const brand = (product.brand || '').toLowerCase()
      return title.includes(query) || brand.includes(query)
    })
  }, [groups, searchQuery])

  return (
    <div className="min-h-screen bg-[#eaeded]">
      {/* HERO BANNER */}
      <section className="relative bg-gradient-to-b from-[#232f3e] via-[#37475a] to-[#eaeded]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-10 pb-20 sm:pt-12 sm:pb-24 lg:pt-16 lg:pb-32">
          <div className="max-w-2xl">
            <h1 className="text-2xl sm:text-3xl lg:text-5xl font-bold text-white mb-3 sm:mb-4 leading-tight">
              Great products at
              <span className="text-[#ff9900]"> great prices</span>
            </h1>
            <p className="text-sm sm:text-base lg:text-lg text-gray-200">
              Curated collection from Amazon. Best deals, quality products,
              delivered to your door.
            </p>
          </div>
        </div>
      </section>

      {/* PRODUCTS */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 -mt-16 sm:-mt-20 relative z-10">
        <div className="bg-white rounded-lg shadow-md p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl sm:text-2xl font-bold text-[#0f1111]">
              {searchQuery
                ? `Search results for "${searchQuery}"`
                : 'Featured Products'}
            </h2>
            {!isLoading && !error && (
              <p className="text-xs sm:text-sm text-gray-600">
                {filteredGroups.length}{' '}
                {filteredGroups.length === 1 ? 'result' : 'results'}
              </p>
            )}
          </div>

          {/* Loading */}
          {isLoading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {[...Array(8)].map((_, i) => (
                <div
                  key={i}
                  className="bg-white rounded-lg overflow-hidden border border-gray-200"
                >
                  <div className="aspect-square bg-gray-200 animate-pulse"></div>
                  <div className="p-4 space-y-3">
                    <div className="h-3 bg-gray-200 rounded w-1/3 animate-pulse"></div>
                    <div className="h-4 bg-gray-200 rounded w-full animate-pulse"></div>
                    <div className="h-4 bg-gray-200 rounded w-2/3 animate-pulse"></div>
                    <div className="h-6 bg-gray-200 rounded w-1/3 animate-pulse"></div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Error */}
          {error && !isLoading && (
            <div className="border border-red-200 rounded-lg p-6 sm:p-8 text-center max-w-lg mx-auto">
              <p className="text-4xl mb-3">⚠️</p>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
               Something went wrong
              </h3>
              <p className="text-gray-600 text-sm mb-4">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="bg-[#ff9900] hover:bg-[#e88b00] text-[#0f1111] font-medium px-6 py-2 rounded-lg transition-colors"
              >
              Try Again
              </button>
            </div>
          )}

          {/* Empty */}
          {!isLoading && !error && groups.length === 0 && (
            <div className="text-center py-16">
              <p className="text-6xl mb-4">📦</p>
              <h2 className="text-xl font-bold text-gray-800 mb-2">
                No products yet
              </h2>
              <p className="text-gray-600">New products will be added soon.</p>
            </div>
          )}

          {/* No search results */}
          {!isLoading &&
            !error &&
            groups.length > 0 &&
            filteredGroups.length === 0 && (
              <div className="text-center py-16">
                <p className="text-5xl mb-4">🔍</p>
                <h2 className="text-xl font-bold text-gray-800 mb-2">
                  No products found
                </h2>
                <p className="text-gray-600 mb-4">
                No results for  "{searchQuery}" k
                </p>
                <a
                  href="/"
                  className="inline-block bg-[#ff9900] hover:bg-[#e88b00] text-[#0f1111] font-medium px-6 py-2 rounded-lg transition-colors"
                >
                  View All Products
                </a>
              </div>
            )}

          {/* Grid */}
          {!isLoading && !error && filteredGroups.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {filteredGroups.map((group) => (
                <ProductCard
                  key={group.parent_product.id}
                  product={group.parent_product}
                  totalVariants={group.total_variants}
                />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default Home