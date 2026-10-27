# ============================================
# app/services/shopify_inventory.py
# Location finder and inventory quantity setter
# + ✅ FIXED: Online orders fulfill karne wali location prefer karta hai
# + ✅ FIXED: "not stocked at location" error handle
# ============================================

import logging
import uuid
from typing import Optional

from app.services.shopify.helpers import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# PRIMARY LOCATION DHUNDO
# ✅ FIXED: Online orders fulfill karne wali location prefer
# ============================================
async def get_primary_location(shop: str, access_token: str) -> Optional[str]:
    """
    Shopify ki primary location fetch karo.
    
    Priority:
    1. Woh location jo online orders fulfill karti hai (fulfillsOnlineOrders = true)
    2. Woh location jiska naam "shop location" ho
    3. isPrimary = true
    4. First active
    """
    query = """
    query {
      locations(first: 10) {
        edges {
          node {
            id
            name
            isActive
            isPrimary
            fulfillsOnlineOrders
          }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query)

    if "errors" in result:
        logger.error(f"Location query errors: {result['errors']}")
        return None

    edges = result.get("data", {}).get("locations", {}).get("edges", [])

    if not edges:
        logger.warning("No location found")
        return None

    # ✅ Priority 1: Online orders fulfill karne wali location
    for edge in edges:
        node = edge["node"]
        if node.get("isActive") and node.get("fulfillsOnlineOrders"):
            logger.info(
                f"✅ Location found (fulfills online): "
                f"{node.get('name')} ({node['id']})"
            )
            return node["id"]

    # Priority 2: Name mein "shop location"
    for edge in edges:
        node = edge["node"]
        name = node.get("name", "")
        if "shop location" in name.lower() and node.get("isActive"):
            logger.info(f"✅ Shop location found: {node['id']}")
            return node["id"]

    # Priority 3: isPrimary
    for edge in edges:
        node = edge["node"]
        if node.get("isPrimary") and node.get("isActive"):
            logger.info(f"✅ Primary location: {node['id']}")
            return node["id"]

    # Priority 4: First active
    for edge in edges:
        node = edge["node"]
        if node.get("isActive"):
            logger.info(f"✅ First active location: {node['id']}")
            return node["id"]

    # Fallback: pehli location
    location_id = edges[0]["node"]["id"]
    logger.info(f"✅ Fallback location: {location_id}")
    return location_id


# ============================================
# INVENTORY SET KARO
# + ✅ FIXED: "not stocked at location" error gracefully handle
# ============================================
async def set_inventory_quantity(
    shop: str,
    access_token: str,
    inventory_item_id: str,
    quantity: int,
) -> bool:
    location_id = await get_primary_location(shop, access_token)
    if not location_id:
        logger.warning("No location — inventory set nahi hoga")
        return False

    query_current = """
    query getInventoryLevel($inventoryItemId: ID!, $locationId: ID!) {
      inventoryItem(id: $inventoryItemId) {
        inventoryLevel(locationId: $locationId) {
          quantities(names: ["available"]) {
            name
            quantity
          }
        }
      }
    }
    """

    current_result = await shopify_graphql(
        shop,
        access_token,
        query_current,
        {"inventoryItemId": inventory_item_id, "locationId": location_id},
    )

    current_qty = 0
    try:
        quantities = (
            current_result.get("data", {})
            .get("inventoryItem", {})
            .get("inventoryLevel", {})
            .get("quantities", [])
        )
        for q in quantities:
            if q.get("name") == "available":
                current_qty = q.get("quantity", 0)
                break
    except Exception:
        current_qty = 0

    logger.info(f"   Current inventory: {current_qty}, target: {quantity}")

    idempotency_key = str(uuid.uuid4())

    mutation = """
    mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
      inventorySetQuantities(input: $input) @idempotent(key: "%s") {
        inventoryAdjustmentGroup {
          createdAt
          reason
        }
        userErrors {
          field
          message
        }
      }
    }
    """ % idempotency_key

    variables = {
        "input": {
            "name": "available",
            "reason": "correction",
            "quantities": [
                {
                    "inventoryItemId": inventory_item_id,
                    "locationId": location_id,
                    "quantity": quantity,
                    "changeFromQuantity": current_qty,
                }
            ],
        }
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Inventory set GraphQL errors: {result['errors']}")
        return False

    inv_errors = (
        result.get("data", {})
        .get("inventorySetQuantities", {})
        .get("userErrors", [])
    )

    if inv_errors:
        # ✅ "not stocked" error gracefully handle
        not_stocked = any(
            "not stocked" in (e.get("message") or "").lower()
            for e in inv_errors
        )
        if not_stocked:
            logger.warning(
                f"   ⚠️ Inventory item {inventory_item_id} is not stocked at "
                f"location {location_id}. Activating inventory first..."
            )

            # ✅ Fallback: inventory item ko activate karo us location pe
            activate_result = await _activate_inventory_at_location(
                shop, access_token, inventory_item_id, location_id
            )

            if activate_result:
                # Retry set
                result2 = await shopify_graphql(
                    shop, access_token, mutation, variables
                )
                inv_errors2 = (
                    result2.get("data", {})
                    .get("inventorySetQuantities", {})
                    .get("userErrors", [])
                )
                if not inv_errors2:
                    logger.info(f"✅ Inventory set to: {quantity} (after activation)")
                    return True
                else:
                    logger.error(
                        f"❌ Retry failed: {inv_errors2}"
                    )
                    return False
            else:
                logger.error("❌ Could not activate inventory at location")
                return False

        logger.error(f"❌ Inventory set user errors: {inv_errors}")
        return False

    logger.info(f"✅ Inventory set to: {quantity}")
    return True


# ============================================
# HELPER: Activate inventory item at location
# ============================================
async def _activate_inventory_at_location(
    shop: str,
    access_token: str,
    inventory_item_id: str,
    location_id: str,
) -> bool:
    """
    Inventory item ko kisi location pe activate karo.
    Yeh tab use hota hai jab "not stocked at location" error aaye.
    """
    mutation = """
    mutation inventoryActivate($inventoryItemId: ID!, $locationId: ID!) {
      inventoryActivate(
        inventoryItemId: $inventoryItemId,
        locationId: $locationId
      ) {
        inventoryLevel {
          id
          location { id name }
        }
        userErrors { field message }
      }
    }
    """

    variables = {
        "inventoryItemId": inventory_item_id,
        "locationId": location_id,
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Inventory activate errors: {result['errors']}")
        return False

    activate_errors = (
        result.get("data", {})
        .get("inventoryActivate", {})
        .get("userErrors", [])
    )

    if activate_errors:
        # "already active" error toh ignore karo
        already = any(
            "already" in (e.get("message") or "").lower()
            for e in activate_errors
        )
        if already:
            logger.info("   ✅ Inventory already active at location")
            return True
        logger.error(f"❌ Inventory activate user errors: {activate_errors}")
        return False

    logger.info(f"   ✅ Inventory activated at location {location_id}")
    return True
