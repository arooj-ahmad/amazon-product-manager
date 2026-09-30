// ============================================
// frontend/src/pages/admin/ProductEdit.jsx
// Product edit form
// ============================================

import { useEffect, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { getProductById, adminUpdateProduct } from '../../api/products'

function ProductEdit() {
    const { id } = useParams()
    const navigate = useNavigate()

    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [error, setError] = useState(null)
    const [successMessage, setSuccessMessage] = useState(null)

    // Form fields
    const [formData, setFormData] = useState({
        title: '',
        brand: '',
        description: '',
        image_url: '',
        price: '',
        markup: '',
    })

    // Original product (for read-only fields)
    const [product, setProduct] = useState(null)

    // ----------------------------------------
    // Product load karo
    // ----------------------------------------
    useEffect(() => {
        const fetchProduct = async () => {
            try {
                setIsLoading(true)
                const data = await getProductById(id)
                setProduct(data)
                setFormData({
                    title: data.title || '',
                    brand: data.brand || '',
                    description: data.description || '',
                    image_url: data.image_url || '',
                    price: data.price ?? '',
                    markup: data.markup ?? '',
                })
            } catch (err) {
                setError('Failed to load product')
            } finally {
                setIsLoading(false)
            }
        }

        fetchProduct()
    }, [id])

    // ----------------------------------------
    // Input change handler
    // ----------------------------------------
    const handleChange = (field, value) => {
        setFormData((prev) => ({ ...prev, [field]: value }))
    }

    // ----------------------------------------
    // Submit handler
    // ----------------------------------------
    const handleSubmit = async (e) => {
        e.preventDefault()
        setIsSaving(true)
        setError(null)
        setSuccessMessage(null)

        try {
            // Sirf changed fields bhejo
            const updates = {}
            if (formData.title !== product.title) updates.title = formData.title
            if (formData.brand !== product.brand) updates.brand = formData.brand
            if (formData.description !== product.description)
                updates.description = formData.description
            if (formData.image_url !== product.image_url)
                updates.image_url = formData.image_url

            // Price change
            const newPrice = parseFloat(formData.price)
            if (!isNaN(newPrice) && newPrice !== product.price) {
                updates.price = newPrice
            }

            // Markup change
            const newMarkup = parseFloat(formData.markup)
            if (!isNaN(newMarkup) && newMarkup !== product.markup) {
                updates.markup = newMarkup
            }

            if (Object.keys(updates).length === 0) {
                setSuccessMessage('No changes made')
                setIsSaving(false)
                return
            }

            const result = await adminUpdateProduct(id, updates)
            setProduct(result)
            setSuccessMessage('✅  Product updated successfully!')

            // 2 second baad dashboard par wapas
            setTimeout(() => {
                navigate('/admin/dashboard')
            }, 1500)
        } catch (err) {
            setError(err.response?.data?.detail || 'Update failed')
        } finally {
            setIsSaving(false)
        }
    }

    // ----------------------------------------
    // Loading
    // ----------------------------------------
    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <div className="inline-block w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin-slow"></div>
                    <p className="mt-4 text-gray-600">Loading product...</p>
                </div>
            </div>
        )
    }

    if (error && !product) {
        return (
            <div className="max-w-4xl mx-auto px-4 py-16 text-center">
                <p className="text-4xl mb-3">😕</p>
                <p className="text-red-600 mb-4">{error}</p>
                <Link
                    to="/admin/dashboard"
                    className="inline-block bg-blue-500 text-white px-6 py-3 rounded-lg"
                >
                    ← Back to dashboard
                </Link>
            </div>
        )
    }

    return (
        <div className="max-w-4xl mx-auto px-4 py-8">
            {/* Back button */}
            <Link
                to="/admin/dashboard"
                className="inline-flex items-center text-gray-600 hover:text-blue-600 mb-6 transition-colors"
            >
                ← Back to dashboard
            </Link>

            <div className="bg-white rounded-2xl shadow-md p-6 lg:p-8">
                <h1 className="text-2xl font-bold text-gray-800 mb-6">
                    ✏️ Edit Product
                </h1>

                {/* Success */}
                {successMessage && (
                    <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-4">
                        {successMessage}
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
                        {error}
                    </div>
                )}

                {/* Read-only info */}
                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                    <p className="text-sm text-gray-600">
                        <span className="font-medium">ASIN:</span>{' '}
                        <span className="font-mono">{product.asin}</span>
                    </p>
                    {product.parent_asin && (
                        <p className="text-sm text-gray-600 mt-1">
                            <span className="font-medium">Parent ASIN:</span>{' '}
                            <span className="font-mono">{product.parent_asin}</span>
                        </p>
                    )}
                    <p className="text-sm text-gray-600 mt-1">
                        <span className="font-medium">Amazon Price:</span> $
                        {product.amazon_price?.toFixed(2)}
                    </p>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-5">
                    {/* Title */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Title
                        </label>
                        <input
                            type="text"
                            value={formData.title}
                            onChange={(e) => handleChange('title', e.target.value)}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                    </div>

                    {/* Brand */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Brand
                        </label>
                        <input
                            type="text"
                            value={formData.brand}
                            onChange={(e) => handleChange('brand', e.target.value)}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                    </div>

                    {/* Image URL */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Image URL
                        </label>
                        <input
                            type="url"
                            value={formData.image_url}
                            onChange={(e) => handleChange('image_url', e.target.value)}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                        {/* Image preview */}
                        {formData.image_url && (
                            <div className="mt-2 w-24 h-24 bg-gray-50 rounded border border-gray-200 overflow-hidden">
                                <img
                                    src={formData.image_url}
                                    alt="Preview"
                                    className="w-full h-full object-contain"
                                />
                            </div>
                        )}
                    </div>

                    {/* Description */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Description
                        </label>
                        <textarea
                            value={formData.description}
                            onChange={(e) => handleChange('description', e.target.value)}
                            rows={6}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none resize-y"
                        />
                    </div>

                    {/* Price + Markup */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Website Price ($)
                            </label>
                            <input
                                type="number"
                                step="0.01"
                                min="0"
                                value={formData.price}
                                onChange={(e) => handleChange('price', e.target.value)}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                ⚠️ Changing the price will enable <strong>manual override</strong>. The scheduler will no longer update this product's price.
                            </p>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Markup ($)
                            </label>
                            <input
                                type="number"
                                step="0.01"
                                min="0"
                                value={formData.markup}
                                onChange={(e) => handleChange('markup', e.target.value)}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                        </div>
                    </div>

                    {/* Submit */}
                    <div className="flex gap-3 pt-4">
                        <button
                            type="submit"
                            disabled={isSaving}
                            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium px-6 py-3 rounded-lg transition-colors"
                        >
                            {isSaving ? 'Saving...' : 'Save Changes'}
                        </button>
                        <Link
                            to="/admin/dashboard"
                            className="bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium px-6 py-3 rounded-lg transition-colors"
                        >
                            Cancel
                        </Link>
                    </div>
                </form>
            </div>
        </div>
    )
}

export default ProductEdit