# app/services/shopify/product_extras.py
# Publish + Collections + Images + Tags

import logging

from app.services.shopify.helpers import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# ✅ PUBLISH PRODUCT TO CHANNELS
# ============================================
async def publish_product_to_channels(
    shop: str,
    access_token: str,
    shopify_product_id: str,
) -> bool:
    """Product ko saare sales channels pe publish karo."""
    if not shopify_product_id:
        return False

    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    publications_query = """
    query getPublications {
      publications(first: 10) {
        edges {
          node { id name }
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, publications_query)

    if "errors" in result:
        logger.error(f"❌ Failed to fetch publications: {result['errors']}")
        return False

    edges = result.get("data", {}).get("publications", {}).get("edges", [])

    if not edges:
        logger.warning("⚠️ No publications found")
        return False

    publication_ids = []
    for edge in edges:
        pub = edge["node"]
        pub_id = pub.get("id")
        pub_name = pub.get("name", "")
        if pub_id:
            publication_ids.append(pub_id)
            logger.info(f"   📢 Publishing to: {pub_name}")

    if not publication_ids:
        return False

    mutation = """
    mutation publishablePublish(
      $id: ID!
      $input: [PublicationInput!]!
    ) {
      publishablePublish(id: $id, input: $input) {
        publishable {
          availablePublicationsCount { count }
        }
        userErrors { field message }
      }
    }
    """

    input_data = [{"publicationId": pid} for pid in publication_ids]

    variables = {"id": product_gid, "input": input_data}

    publish_result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in publish_result:
        logger.error(f"❌ Publish errors: {publish_result['errors']}")
        return False

    user_errors = (
        publish_result.get("data", {})
        .get("publishablePublish", {})
        .get("userErrors", [])
    )

    if user_errors:
        logger.error(f"❌ Publish user errors: {user_errors}")
        return False

    count = (
        publish_result.get("data", {})
        .get("publishablePublish", {})
        .get("publishable", {})
        .get("availablePublicationsCount", {})
        .get("count", 0)
    )

    logger.info(f"✅ Product published to {count} channel(s)")
    return True


# ============================================
# ✅ ADD PRODUCT TO COLLECTIONS
# ============================================
async def add_product_to_collections(
    shop: str,
    access_token: str,
    product_id: str,
    collection_ids: list,
) -> bool:
    """Product ko multiple collections mein add karo."""
    if not collection_ids:
        logger.info("   No collections to add")
        return True

    if not product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{product_id}"
    else:
        product_gid = product_id

    mutation = """
    mutation collectionAddProducts(
      $id: ID!,
      $productIds: [ID!]!
    ) {
      collectionAddProducts(id: $id, productIds: $productIds) {
        collection {
          id
          title
          productsCount { count }
        }
        userErrors { field message }
      }
    }
    """

    success_count = 0
    failed = []

    for collection_id in collection_ids:
        if not collection_id:
            continue

        if not collection_id.startswith("gid://"):
            collection_gid = f"gid://shopify/Collection/{collection_id}"
        else:
            collection_gid = collection_id

        variables = {
            "id": collection_gid,
            "productIds": [product_gid],
        }

        result = await shopify_graphql(shop, access_token, mutation, variables)

        if "errors" in result:
            logger.error(
                f"   ❌ Collection {collection_id} add errors: {result['errors']}"
            )
            failed.append(collection_id)
            continue

        add_errors = (
            result.get("data", {})
            .get("collectionAddProducts", {})
            .get("userErrors", [])
        )

        if add_errors:
            already = any(
                "already" in (e.get("message") or "").lower()
                or "in the collection" in (e.get("message") or "").lower()
                for e in add_errors
            )
            if already:
                logger.info(f"   ℹ️ Product already in collection {collection_id}")
                success_count += 1
                continue

            logger.error(f"   ❌ Collection {collection_id} user errors: {add_errors}")
            failed.append(collection_id)
            continue

        success_count += 1
        logger.info(f"   ✅ Product added to collection {collection_id}")

    logger.info(f"✅ Added to {success_count}/{len(collection_ids)} collections")

    if failed:
        logger.warning(f"⚠️ Failed collections: {failed}")

    return len(failed) == 0


# ============================================
# ADD PRODUCT IMAGES
# ============================================
async def add_product_images(
    shop: str,
    access_token: str,
    product_id: str,
    image_urls: list,
) -> dict:
    mutation = """
    mutation productCreateMedia(
      $productId: ID!,
      $media: [CreateMediaInput!]!
    ) {
      productCreateMedia(productId: $productId, media: $media) {
        media { ... on MediaImage { id image { url } } }
        mediaUserErrors { field message }
      }
    }
    """

    media_input = [
        {"originalSource": url, "mediaContentType": "IMAGE"}
        for url in image_urls
        if url
    ]

    if not media_input:
        return {}

    variables = {"productId": product_id, "media": media_input}

    return await shopify_graphql(shop, access_token, mutation, variables)


# ============================================
# UPDATE PRODUCT TAGS AND TYPE
# ============================================
async def update_shopify_product_tags_and_type(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    tags: list[str],
    product_type: str = "",
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id title tags productType }
        userErrors { field message }
      }
    }
    """

    input_data = {"id": product_gid, "tags": tags}
    if product_type:
        input_data["productType"] = product_type

    variables = {"input": input_data}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Tags update GraphQL errors: {result['errors']}")
        return False

    update_data = result.get("data", {}).get("productUpdate", {})
    user_errors = update_data.get("userErrors", [])

    if user_errors:
        logger.error(f"❌ Tags update user errors: {user_errors}")
        return False

    updated = update_data.get("product", {})
    logger.info(f"✅ Tags updated: {len(updated.get('tags', []))} tags")
    return True


# ============================================
# PRODUCT STATUS UPDATE
# ============================================
async def update_shopify_product_status(
    shop: str,
    access_token: str,
    shopify_product_id: str,
    is_available: bool,
) -> bool:
    if not shopify_product_id.startswith("gid://"):
        product_gid = f"gid://Shopify/Product/{shopify_product_id}"
    else:
        product_gid = shopify_product_id

    new_status = "ACTIVE" if is_available else "DRAFT"

    mutation = """
    mutation updateProductStatus($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id title status }
        userErrors { field message }
      }
    }
    """

    variables = {"input": {"id": product_gid, "status": new_status}}

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"❌ Status update errors: {result['errors']}")
        return False

    return True