// ============================================
// frontend/src/components/Footer.jsx
// Amazon-style footer
// ============================================

import { Link } from 'react-router-dom'

function Footer() {
  // "Back to top" scroll
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <footer className="bg-[#232f3e] text-white mt-16">
      {/* ========================================
          BACK TO TOP
      ======================================== */}
      <button
        onClick={scrollToTop}
        className="w-full bg-[#37475a] hover:bg-[#485769] text-white text-sm font-medium py-4 transition-colors"
      >
        Back to top
      </button>

      {/* ========================================
          MAIN FOOTER
      ======================================== */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {/* Column 1: Get to Know Us */}
          <div>
            <h3 className="text-base font-bold mb-4">Get to Know Us</h3>
            <ul className="space-y-2 text-sm text-gray-300">
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  About Us
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Careers
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Press Releases
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Blog
                </a>
              </li>
            </ul>
          </div>

          {/* Column 2: Make Money with Us */}
          <div>
            <h3 className="text-base font-bold mb-4">Make Money with Us</h3>
            <ul className="space-y-2 text-sm text-gray-300">
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Sell products
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Become an Affiliate
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Advertise Your Products
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Self-Publish with Us
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Payment Products */}
          <div>
            <h3 className="text-base font-bold mb-4">Payment Products</h3>
            <ul className="space-y-2 text-sm text-gray-300">
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Business Card
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Shop with Points
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Reload Your Balance
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Currency Converter
                </a>
              </li>
            </ul>
          </div>

          {/* Column 4: Let Us Help You */}
          <div>
            <h3 className="text-base font-bold mb-4">Let Us Help You</h3>
            <ul className="space-y-2 text-sm text-gray-300">
              <li>
                <Link to="/admin/login" className="hover:underline hover:text-white transition-colors">
                  Your Account
                </Link>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Your Orders
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Shipping Rates & Policies
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Returns & Replacements
                </a>
              </li>
              <li>
                <a href="#" className="hover:underline hover:text-white transition-colors">
                  Help
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* ========================================
            DIVIDER
        ======================================== */}
        <div className="border-t border-gray-600 mt-10 pt-8">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <span className="text-3xl">🛒</span>
              <div className="leading-tight">
                <span className="text-xl font-bold">Amazon</span>
                <span className="text-xs text-[#ff9900] block -mt-1">
                  Product Manager
                </span>
              </div>
            </Link>

            {/* Language / Country */}
            <div className="flex flex-wrap items-center justify-center gap-3 text-sm">
              <button className="border border-gray-500 hover:border-white rounded px-3 py-1.5 transition-colors flex items-center gap-2">
                🌐 English
              </button>
              <button className="border border-gray-500 hover:border-white rounded px-3 py-1.5 transition-colors">
                $ USD - U.S. Dollar
              </button>
              <button className="border border-gray-500 hover:border-white rounded px-3 py-1.5 transition-colors">
                🇺🇸 United States
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================
          BOTTOM BAR
      ======================================== */}
      <div className="bg-[#131921] py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center gap-3 text-xs text-gray-400">
            {/* Links */}
            <div className="flex flex-wrap justify-center gap-4">
              <a href="#" className="hover:underline hover:text-white transition-colors">
                Conditions of Use
              </a>
              <a href="#" className="hover:underline hover:text-white transition-colors">
                Privacy Notice
              </a>
              <a href="#" className="hover:underline hover:text-white transition-colors">
                Consumer Health Data Privacy Disclosure
              </a>
              <a href="#" className="hover:underline hover:text-white transition-colors">
                Your Ads Privacy Choices
              </a>
            </div>

            {/* Copyright */}
            <p className="text-center">
              © 2026 Amazon Product Manager. All rights reserved.
            </p>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer