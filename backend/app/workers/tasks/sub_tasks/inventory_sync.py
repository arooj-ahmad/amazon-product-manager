# app/workers/tasks/sub_tasks/inventory_sync.py
import logging
from app.services.shopify import shopify_graphql, set_inventory_quantity

logger = logging.getLogger(__name__)

async def sync_product_inventory(shop, access_token, shopify_product_id, stock_quantity, is_available):
    """Shopify product ke saare variants ka inventory update karta hai."""
    inv_query = """
    query getProductInventory($id: ID!) {
      product(id: $id) {
        variants(first: 50) {
          edges {
            node {
              id
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

    all_updated = True
    for edge in inv_edges:
        inv_item_id = edge.get("node", {}).get("inventoryItem", {}).get("id")
        if inv_item_id:
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
                logger.info(f"[INVENTORY] ? Inventory synced: qty={qty}")
            else:
                logger.error(f"[INVENTORY] ? Inventory update FAILED")
                all_updated = False

    return all_updated
