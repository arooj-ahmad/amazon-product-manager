# app/api/routes/shopify/worker/extractor.py
import logging
from app.services.amazon import ApifyError, fetch_product_from_apify, parse_price
from ..helpers import _extract_weight, extract_all_variations

logger = logging.getLogger(__name__)

async def extract_variants_data(amazon_url, data, variant_details_map, loop):
    """Amazon data se saare variants extract karke list banata hai."""
    base_asin = data["asin"]
    raw_asins = []
    
    for a in (data.get("variant_asins") or data.get("variantAsins") or []):
        if a and isinstance(a, str): raw_asins.append(a.strip())
    for vd in (data.get("variant_details") or data.get("variantDetails") or []):
        if isinstance(vd, dict) and vd.get("asin"): raw_asins.append(vd["asin"].strip())
    for v in (data.get("variants") or []):
        if isinstance(v, dict) and v.get("asin"): raw_asins.append(v["asin"].strip())
    
    if base_asin and isinstance(base_asin, str): raw_asins.insert(0, base_asin.strip())

    seen, variant_asins = set(), []
    for a in raw_asins:
        if a and a not in seen:
            seen.add(a)
            variant_asins.append(a)

    prepared_data = []
    for index, v_asin in enumerate(variant_asins):
        vd = variant_details_map.get(v_asin) or {}
        v_data = None
        if v_asin == base_asin:
            v_data = data
            v_attrs = data.get("variant_attributes") or []
            v_price = data.get("amazon_price")
            v_imgs = data.get("images") or []
            v_thumb = data.get("image_url")
            v_name = data.get("title", "")
        else:
            v_attrs = vd.get("attributes") or []
            v_price = parse_price(vd.get("price"))
            v_imgs = vd.get("images") or []
            v_thumb = vd.get("thumbnail")
            v_name = vd.get("name", "")

            needs_fetch = (v_price is None or not v_attrs)
            if needs_fetch:
                try:
                    v_data = await loop.run_in_executor(None, fetch_product_from_apify, f"https://www.amazon.com/dp/{v_asin}")
                    if v_data:
                        if v_data.get("amazon_price") is not None: v_price = v_data["amazon_price"]
                        if v_data.get("variant_attributes"): v_attrs = v_data["variant_attributes"]
                        if v_data.get("images"): v_imgs = v_data["images"]
                        if v_data.get("image_url"): v_thumb = v_data["image_url"]
                        if v_data.get("title"): v_name = v_data["title"]
                except Exception as e:
                    logger.warning(f"Fetch child details failed for {v_asin}: {e}")

            if v_price is None: v_price = data.get("amazon_price")

        if not v_attrs:
            v_attrs = extract_all_variations(v_data or {"variant_attributes": []})
            if not v_attrs or (len(v_attrs) == 1 and v_attrs[0].get("value") == "Default"):
                v_attrs = [{"name": "Style", "value": v_name or f"Variant {index+1}"}]

        weight_str = _extract_weight(v_data) if v_data else _extract_weight(data)
        img_url = (v_imgs[0] if v_imgs else None) or v_thumb or (v_data.get("image_url") if v_data else None) or data.get("image_url")

        prepared_data.append({
            "asin": v_asin,
            "title": v_name or v_asin,
            "amazon_price": v_price,
            "attributes": v_attrs,
            "weight": weight_str,
            "image_url": img_url,
            "images": v_imgs or data.get("images", []),
            "availability": (v_data.get("availability") if v_data else None) or data.get("availability") or "In Stock",
            "is_available": (v_data.get("is_available") if v_data else None) if (v_data and v_data.get("is_available") is not None) else data.get("is_available", True),
            "stock_quantity": (v_data.get("stock_quantity") if v_data else None) or (data.get("stock_quantity", 100) if data.get("is_available", True) else 0),
            "raw_v_data": v_data
        })

    return prepared_data
