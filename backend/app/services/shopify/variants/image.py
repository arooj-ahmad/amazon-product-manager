# app/services/shopify/variants/image.py
import logging
import asyncio
from app.services.shopify.helpers import shopify_graphql

logger = logging.getLogger(__name__)

async def _assign_image_to_variant(shop: str, access_token: str, product_id: str, variant_id: str, image_url: str):
    logger.info(f"   Assigning image to variant: {image_url[:50]}...")
    
    query_media = """query getProductMedia($id: ID!) { product(id: $id) { media(first: 50) { edges { node { id ... on MediaImage { image { url } } } } } } }"""
    res_existing = await shopify_graphql(shop, access_token, query_media, {"id": product_id})
    existing_media_id = None
    
    if "errors" not in res_existing:
        edges = res_existing.get("data", {}).get("product", {}).get("media", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            img_data = node.get("image") or {}
            if img_data.get("url") == image_url:
                existing_media_id = node.get("id")
                break

    media_id = existing_media_id

    if not media_id:
        mutation_media = """mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) { productCreateMedia(productId: $productId, media: $media) { media { id } mediaUserErrors { field message } } }"""
        media_input = [{"originalSource": image_url, "mediaContentType": "IMAGE"}]
        result_media = await shopify_graphql(shop, access_token, mutation_media, {"productId": product_id, "media": media_input})
        
        if "errors" not in result_media:
            created_media = result_media.get("data", {}).get("productCreateMedia", {}).get("media", [])
            if created_media:
                media_id = created_media[0].get("id")
                await asyncio.sleep(2)

    if not media_id: return
    
    mutation_variant = """mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $productId, variants: $variants) { productVariants { id image { id url } } userErrors { field message } } }"""
    variant_input = {"id": variant_id, "mediaId": media_id}
    result_var = await shopify_graphql(shop, access_token, mutation_variant, {"productId": product_id, "variants": [variant_input]})
    
    if "errors" not in result_var:
        logger.info(f"Image assigned to variant successfully")
