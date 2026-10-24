# ============================================
# app/services/amazon/inventory.py
# ============================================

def check_availability(raw: dict) -> tuple[bool, str, str]:
    """
    Sirf Apify ke 'inStock' field ko check karta hai.
    Agar true hai to 100, warna 0.
    """
    
    # 1. Apify ka direct inStock field check karo
    in_stock = raw.get("inStock")
    
    # Agar boolean True hai -> Stock 100
    if in_stock is True:
        return True, "In Stock", "in_stock_true"
        
    # Agar string "true" hai (kabhi kabhi data string mein aata hai) -> Stock 100
    if isinstance(in_stock, str) and in_stock.lower() == "true":
        return True, "In Stock", "in_stock_string_true"

    # Agar inStock false hai, ya kuch aur hai, ya mojood hi nahi hai -> Stock 0
    # (Baqi koi cheez check nahi karni)
    return False, "Out of Stock", "in_stock_false_or_missing"