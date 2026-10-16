# ============================================
# app/services/shopify_taxonomy.py
# Shopify taxonomy search and best category finder
# + ✅ FIXED v2: Exact match priority + relevance scoring
# + ✅ FIXED v2: Categories ko pehle priority (title se nahi)
# + ✅ FIXED v2: Level 4+ prefer karo
# ============================================

import logging
from typing import Optional

from app.services.shopify_helpers import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# TAXONOMY SEARCH
# ✅ FIXED v2: Exact match + relevance scoring
# ============================================
async def search_shopify_taxonomy(
    shop: str,
    access_token: str,
    search_query: str,
    original_keywords: list = None,
) -> Optional[str]:
    """
    Shopify taxonomy query se category ID dhundho.

    ✅ FIXED v2:
    - Exact match ko priority do
    - Relevance score calculate karo
    - Level 4+ prefer karo
    """
    if not search_query or not isinstance(search_query, str):
        return None

    query_str = search_query.strip()
    if len(query_str) < 3:
        return None

    query = """
    query searchTaxonomy($query: String!) {
      taxonomy {
        categories(first: 10, search: $query) {
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

    # ✅ FIXED v2: Relevance scoring
    query_lower = query_str.lower()
    query_words = set(query_lower.split())
    keywords = set((original_keywords or []) + list(query_words))

    scored = []
    for edge in edges:
        node = edge["node"]
        full_name = (node.get("fullName") or "").lower()
        name = (node.get("name") or "").lower()
        level = node.get("level", 0)

        # ❌ Bad keywords skip karo
        bad_keywords = [
            "minibus", "bus", "vehicle", "transportation",
            "closet", "closets", "squeegee", "squeegees",
            "cleaning supplies", "household cleaning",
        ]
        if any(bad in full_name for bad in bad_keywords):
            continue

        # ✅ Score calculate karo
        score = 0

        # Level 4+ ko zyada score
        score += level * 10

        # Query words match karo
        full_words = set(full_name.split())
        matched_words = query_words & full_words
        score += len(matched_words) * 5

        # Original keywords match karo
        keyword_matches = keywords & full_words
        score += len(keyword_matches) * 3

        # Exact match bonus
        if query_lower in full_name or name == query_lower:
            score += 50

        scored.append((score, node))

    if not scored:
        logger.warning(f"   ⚠️ No good taxonomy match for: {query_str}")
        return None

    # ✅ Highest score wala le lo
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_node = scored[0]

    logger.info(
        f"   ✅ Taxonomy match (score={best_score}, "
        f"L{best_node.get('level')}): "
        f"{best_node.get('fullName')} → {best_node.get('id')}"
    )
    return best_node.get("id")


# ============================================
# BEST CATEGORY — Product Title + Categories
# ✅ FIXED v2: Categories ko pehle priority
# ============================================
async def find_best_category(
    shop: str,
    access_token: str,
    product_title: str,
    categories: list,
) -> Optional[str]:
    """
    Best category dhundho — multiple queries try karo.

    ✅ FIXED v2:
    - Categories ko PEHLE try karo (title se nahi)
    - Original keywords pass karo
    - Exact match prefer karo
    """
    queries_to_try = []
    original_keywords = []

    # ✅ FIXED v2: Categories ko pehle priority do
    if categories:
        # Sabse specific category (last one)
        for cat in reversed(categories):
            if cat and isinstance(cat, str) and len(cat.strip()) >= 3:
                original_keywords.append(cat.strip())

        # Last 2 categories combine
        if len(categories) >= 2:
            queries_to_try.append(
                f"{categories[-2]} {categories[-1]}"
            )

        # Last category
        queries_to_try.append(categories[-1])

        # Last 3 categories combine
        if len(categories) >= 3:
            queries_to_try.append(
                f"{categories[-3]} {categories[-2]} {categories[-1]}"
            )

    # ✅ Title ko LAST priority do
    if product_title and isinstance(product_title, str):
        # Title ke pehle 4 words (kam words = kam fuzzy)
        title_words = product_title.split()[:4]
        title_query = " ".join(title_words)
        if len(title_query) >= 5:
            queries_to_try.append(title_query)
            original_keywords.extend(title_words)

    # ✅ Duplicates hatao
    queries_to_try = list(dict.fromkeys([
        q.strip() for q in queries_to_try if q and len(q.strip()) >= 3
    ]))

    logger.info(f"   🔍 Taxonomy queries to try: {queries_to_try}")

    for query_str in queries_to_try:
        logger.info(f"   🔍 Taxonomy search: '{query_str}'")
        category_id = await search_shopify_taxonomy(
            shop=shop,
            access_token=access_token,
            search_query=query_str,
            original_keywords=original_keywords,
        )
        if category_id:
            return category_id

    logger.info(f"   ⚠️ No category found for: {product_title[:50]}...")
    return None