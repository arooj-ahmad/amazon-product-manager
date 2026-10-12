# ============================================
# app/services/shopify_inventory.py
# Location finder and inventory quantity setter
# ============================================

import logging
import uuid
from typing import Optional

from app.services.shopify_helpers import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# PRIMARY LOCATION DHUNDO
# ============================================
async def get_primary_location(shop: str, access_token: str) -> Optional[str]:
    query = """
    query {
      locations(first: 10) {
        edges {
          node {
            id
            name
            isActive
            isPrimary
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

    for edge in edges:
        node = edge["node"]
        name = node.get("name", "")
        if "shop location" in name.lower():
            logger.info(f"✅ Shop location found: {node['id']}")
            return node["id"]

    for edge in edges:
        node = edge["node"]
        if node.get("isPrimary"):
            logger.info(f"✅ Primary location: {node['id']}")
            return node["id"]

    for edge in edges:
        node = edge["node"]
        if node.get("isActive"):
            logger.info(f"✅ First active location: {node['id']}")
            return node["id"]

    location_id = edges[0]["node"]["id"]
    logger.info(f"✅ Fallback location: {location_id}")
    return location_id


# ============================================
# INVENTORY SET KARO
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
        logger.error(f"❌ Inventory set user errors: {inv_errors}")
        return False

    logger.info(f"✅ Inventory set to: {quantity}")
    return True
