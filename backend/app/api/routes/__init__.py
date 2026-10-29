# ============================================
# app/api/routes/__init__.py
# ============================================

from app.api.routes import products
from app.api.routes.shopify import shopify_router  # ✅ Naya router import kiya

# Purane imports ko break hone se bachane ke liye __all__ define kiya hai
__all__ = [
    "products", 
    "shopify_router", 
    "shopify_routes" # Agar purane naam se koi import ho raha ho to error na aaye
]

# ✅ Ek alias bana diya hai taake purana code 'shopify_routes' likh kar bhi kaam kare
shopify_routes = shopify_router