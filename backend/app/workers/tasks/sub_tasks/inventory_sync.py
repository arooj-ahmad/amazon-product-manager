# app/workers/tasks/sub_tasks/inventory_sync.py
import logging
from app.services.shopify import shopify_graphql, set_inventory_quantity

logger = logging.getLogger(__name__)

async def sync_product_inventory(
    shop, 
    access_token, 
    shopify_product_id, 
    stock_quantity, 
    is_available,
    sku=None  # ✅ NAYA: SKU parameter add kiya
):
    """Shopify product ke specific variant ka inventory update karta hai."""
    
    # 1. Product ke saare variants fetch karein (SKU ke saath)
    inv_query = """
    query getProductInventory($id: ID!) {
      product(id: $id) {
        variants(first: 50) {
          edges {
            node {
              id
              sku
              inventoryItem {
                id
              }
            }
          }
        }
      }
    }
    """

    inv_result = await shopify_graphql(shop, access_token, inv_query, {"id": shopify_product_id})

    if "errors" in inv_result:
        logger.error(f"[INVENTORY] Query error: {inv_result['errors']}")
        return False

    inv_edges = inv_result.get("data", {}).get("product", {}).get("variants", {}).get("edges", [])
    
    if not inv_edges:
        logger.warning(f"[INVENTORY] No variants found for product {shopify_product_id}")
        return False

    # ✅ FIX: Sirf target SKU ka variant dhundein
    target_variant = None
    if sku:
        for edge in inv_edges:
            node = edge.get("node", {})
            if str(node.get("sku")).strip() == str(sku).strip():
                target_variant = node
                break
    else:
        # Fallback: agar sku nahi diya to pehla variant
        if inv_edges:
            target_variant = inv_edges[0].get("node", {})

    if not target_variant:
        logger.warning(f"[INVENTORY] No variant found for SKU: {sku}")
        return False

    # 2. Sirf us specific variant ka inventory update karein
    inv_item_id = target_variant.get("inventoryItem", {}).get("id")
    if not inv_item_id:
        logger.warning(f"[INVENTORY] No inventory item found for SKU: {sku}")
        return False

    qty = stock_quantity or 0
    if qty == 0 and is_available:
        qty = 100  # Fallback (Business rule)

    inv_ok = await set_inventory_quantity(
        shop=shop,
        access_token=access_token,
        inventory_item_id=inv_item_id,
        quantity=qty,
    )

    if inv_ok:
        logger.info(f"[INVENTORY] ✅ Inventory synced: SKU={sku}, qty={qty}")
        return True
    else:
        logger.error(f"[INVENTORY] ❌ Inventory update FAILED for SKU={sku}")
        return False