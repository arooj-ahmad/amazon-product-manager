# ============================================
# app/services/amazon/brightdata_scraper.py
# ============================================

import httpx

from app.config import settings
from .exceptions import BrightDataError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price, parse_standard_fields
from .inventory import check_availability

async def fetch_product_from_brightdata(amazon_url: str) -> dict:
    api_url = (
        f"{settings.BRIGHT_DATA_API_URL}"
        f"?dataset_id={settings.BRIGHT_DATA_DATASET_ID}"
        f"&include_errors=true"
    )
    headers = {
        "Authorization": f"Bearer {settings.BRIGHT_DATA_API_KEY}",
        "Content-Type": "application/json",
    }
    body = [{"url": amazon_url}]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise BrightDataError(f"Bright Data API Error: {str(e)}")

    raw = data[0] if isinstance(data, list) and len(data) > 0 else data
    if "error" in raw:
        raise BrightDataError(f"Bright Data error: {raw['error']}")

    asin = raw.get("asin") or extract_asin_from_url(amazon_url)
    if not asin:
        raise BrightDataError("ASIN nahi mila")

    parent_asin = validate_parent_asin(raw.get("parent_asin"), asin)
    is_variation = bool(parent_asin)

    variations = []
    if isinstance(raw.get("variations"), list):
        for v in raw.get("variations"):
            if isinstance(v, dict) and v.get("variation_name") and v.get("variation_value"):
                variations.append({"name": str(v["variation_name"]).strip(), "value": str(v["variation_value"]).strip()})

    variant_attributes = []
    if isinstance(raw.get("variant_attributes"), list):
        for attr in raw.get("variant_attributes"):
            if isinstance(attr, dict) and attr.get("name") and attr.get("value"):
                variant_attributes.append({"name": str(attr["name"]).strip(), "value": str(attr["value"]).strip()})

    images_list = raw.get("images") or []
    main_image = raw.get("image_url") or raw.get("image")
    unique_images = [main_image] if main_image else []
    if isinstance(images_list, list):
        for img in images_list:
            if isinstance(img, str) and img not in unique_images:
                unique_images.append(img)
    if not main_image and unique_images:
        main_image = unique_images[0]

    # Bright data ke liye bhi check_availability use karte hain
    is_available, availability_text, _ = check_availability(raw)
    stock_quantity = 100 if is_available else 0

    specs = {}
    product_details = raw.get("product_details") or []
    if isinstance(product_details, list):
        for item in product_details:
            if isinstance(item, dict) and item.get("type") and item.get("value"):
                if item["type"] not in specs:
                    specs[item["type"]] = str(item["value"]).strip()

    categories = raw.get("categories") or []
    feature_bullets = []
    if isinstance(raw.get("feature_bullets"), list) and len(raw["feature_bullets"]) > 0:
        feature_bullets = [str(b).strip() for b in raw["feature_bullets"] if b]

    if not feature_bullets:
        desc_text = raw.get("description", "") or raw.get("product_description", "") or raw.get("about_this_item", "")
        if desc_text:
            if "About this item" in desc_text:
                bullets_text = desc_text.split("About this item")[-1].strip()
                lines = bullets_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        feature_bullets.append(line)
            else:
                lines = desc_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        feature_bullets.append(line)

    if not feature_bullets:
        feature_bullets = ["Check Amazon for full product details."]

    return {
        "asin": asin,
        "parent_asin": parent_asin,
        "is_variation": is_variation,
        "title": raw.get("title"),
        "brand": raw.get("brand"),
        "amazon_price": parse_price(raw.get("final_price") or raw.get("price")),
        "list_price": parse_price(raw.get("list_price")),
        "image_url": main_image,
        "images": unique_images,
        "specifications": specs,
        "description": "",
        "feature_bullets": feature_bullets,
        "availability": availability_text,
        "is_available": is_available,
        "stock_quantity": stock_quantity,
        "variations": variations,
        "variant_attributes": variant_attributes,
        "categories": categories,
        "tags": raw.get("tags") or [],
        **parse_standard_fields(raw),
        "product_details": product_details,
    }