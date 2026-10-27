# app/services/amazon/brightdata_scraper.py
import logging
import httpx
from app.core.config import settings
from .exceptions import BrightDataError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price, parse_standard_fields
from .availability import check_availability

logger = logging.getLogger(__name__)

async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    api_url = f"{settings.BRIGHT_DATA_API_URL}?dataset_id={settings.BRIGHT_DATA_DATASET_ID}&include_errors=true"
    headers = {"Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}", "Content-Type": "application/json"}
    body = [{"url": amazon_url}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise BrightDataError(f"Bright Data API Error: {str(e)}")

    raw = data[0] if isinstance(data, list) and len(data) > 0 else data
    if "error" in raw: raise BrightDataError(f"Bright Data error: {raw['error']}")

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin: raise BrightDataError("ASIN nahi mila")

    parent_asin = validate_parent_asin(raw.get("parent_asin"), asin)
    is_available, availability_text, _ = check_availability(raw)
    stock_quantity = 100 if is_available else 0

    variations = [{"name": str(v["variation_name"]).strip(), "value": str(v["variation_value"]).strip()} for v in (raw.get("variations") or []) if isinstance(v, dict) and v.get("variation_name") and v.get("variation_value")]
    variant_attributes = [{"name": str(a["name"]).strip(), "value": str(a["value"]).strip()} for a in (raw.get("variant_attributes") or []) if isinstance(a, dict) and a.get("name") and a.get("value")]

    images_list = raw.get("images") or []
    main_image = raw.get("image_url") or raw.get("image")
    unique_images = [main_image] if main_image else []
    if isinstance(images_list, list):
        for img in images_list:
            if isinstance(img, str) and img not in unique_images: unique_images.append(img)

    specs = {}
    for item in (raw.get("product_details") or []):
        if isinstance(item, dict) and item.get("type") and item.get("value"):
            if item["type"] not in specs: specs[item["type"]] = str(item["value"]).strip()

    feature_bullets = raw.get("feature_bullets") or []
    if not feature_bullets:
        desc_text = raw.get("description", "") or raw.get("product_description", "") or raw.get("about_this_item", "")
        if desc_text:
            bullets_text = desc_text.split("About this item")[-1].strip() if "About this item" in desc_text else desc_text
            feature_bullets = [line.strip() for line in bullets_text.split('\n') if line.strip()]
    if not feature_bullets: feature_bullets = ["Check Amazon for full product details."]

    return {
        "asin": asin, "parent_asin": parent_asin, "is_variation": bool(parent_asin),
        "title": raw.get("title"), "brand": raw.get("brand"),
        "amazon_price": parse_price(raw.get("final_price") or raw.get("price")), "list_price": parse_price(raw.get("list_price")),
        "image_url": main_image, "images": unique_images, "specifications": specs, "description": "",
        "feature_bullets": feature_bullets, "availability": availability_text, "is_available": is_available,
        "stock_quantity": stock_quantity, "variations": variations, "variant_attributes": variant_attributes,
        "categories": raw.get("categories") or [], "tags": raw.get("tags") or [],
        **parse_standard_fields(raw), "product_details": raw.get("product_details") or [],
    }
