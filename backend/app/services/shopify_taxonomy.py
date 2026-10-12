# ============================================
# app/services/shopify_taxonomy.py
# Shopify taxonomy search and best category finder
# ============================================

import logging
from typing import Optional

from app.services.shopify_helpers import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# TAXONOMY SEARCH
# ============================================
async def search_shopify_taxonomy(
    shop: str,
    access_token: str,
    search_query: str,
) -> Optional[str]:
    """Shopify taxonomy query se category ID dhundho."""
    if not search_query or not isinstance(search_query, str):
        return None

    query_str = search_query.strip()
    if len(query_str) < 3:
        return None

    query = """
    query searchTaxonomy($query: String!) {
      taxonomy {
        categories(first: 5, search: $query) {
          edges {
            node {
              id
              name
              fullName
              level
            }
          }
        }
      }
    }
    """

    result = await shopify_graphql(
        shop=shop,
        access_token=access_token,
        query=query,
        variables={"query": query_str},
    )

    if "errors" in result:
        logger.warning(f"   ⚠️ Taxonomy search failed: {result['errors']}")
        return None

    edges = (
        result.get("data", {})
        .get("taxonomy", {})
        .get("categories", {})
        .get("edges", [])
    )

    if not edges:
        return None

    best = None
    best_level = 0

    for edge in edges:
        node = edge["node"]
        level = node.get("level", 0)

        full_name = (node.get("fullName") or "").lower()
        bad_keywords = ["minibus", "bus", "vehicle", "transportation"]
        if any(bad in full_name for bad in bad_keywords):
            continue

        if level >= 3:
            logger.info(
                f"   ✅ Taxonomy match (L{level}): "
                f"{node.get('fullName')} → {node.get('id')}"
            )
            return node.get("id")

        if level == 2 and level > best_level:
            best_level = level
            best = node

    if best:
        logger.info(
            f"   ✅ Taxonomy match (L{best_level}): "
            f"{best.get('fullName')} → {best.get('id')}"
        )
        return best.get("id")

    first = edges[0]["node"]
    logger.info(
        f"   ✅ Taxonomy fallback: "
        f"{first.get('fullName')} → {first.get('id')}"
    )
    return first.get("id")


# ============================================
# BEST CATEGORY — Product Title + Categories
# ============================================
async def find_best_category(
    shop: str,
    access_token: str,
    product_title: str,
    categories: list,
) -> Optional[str]:
    """Best category dhundho — multiple queries try karo."""
    queries_to_try = []

    if product_title and isinstance(product_title, str):
        title_words = product_title.split()[:6]
        title_query = " ".join(title_words)
        if len(title_query) >= 5:
            queries_to_try.append(title_query)

    if categories and len(categories) >= 2:
        queries_to_try.append(f"{categories[-2]} {categories[-1]}")

    if categories:
        queries_to_try.append(categories[-1])

    if categories and len(categories) >= 2:
        queries_to_try.append(categories[-2])

    queries_to_try = list(dict.fromkeys([
        q.strip() for q in queries_to_try if q and len(q.strip()) >= 3
    ]))

    for query_str in queries_to_try:
        logger.info(f"   🔍 Taxonomy search: '{query_str}'")
        category_id = await search_shopify_taxonomy(
            shop=shop,
            access_token=access_token,
            search_query=query_str,
        )
        if category_id:
            return category_id

    logger.info(f"   ⚠️ No category found for: {product_title[:50]}...")
    return None
