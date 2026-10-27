# app/services/amazon/apify_scraper.py
# ============================================================
# Fetches a single Amazon product page via Apify.
# Returns the normalised product dict INCLUDING the raw
# variantDetails and variantAsins arrays so that the worker
# can extract child ASINs without a second Apify call.
# ============================================================
import logging
from apify_client import ApifyClient
from app.core.config import settings
from .exceptions import ApifyError
from .helpers import extract_asin_from_url, validate_parent_asin, parse_price
from .inventory_apify import check_availability_apify

logger = logging.getLogger(__name__)


def _is_valid_asin(value) -> bool:
    """Return True when value looks like a 10-char alphanumeric ASIN."""
    if not value or not isinstance(value, str):
        return False
    v = value.strip().upper()
    return len(v) == 10 and v.isalnum()


def _extract_child_asins_from_raw(item: dict, base_asin: str) -> tuple:
    """
    Collect child ASINs from the raw Apify item using every known field:
      • variantDetails[].asin  (primary – has attributes + price + image)
      • variantAsins[]         (secondary – bare ASIN list)
      • variants[].asin        (tertiary – actor-specific)

    NOTE: galleryThumbnails and highResolutionImages are presentation
    artefacts and are intentionally NOT used as variation sources.

    Returns:
        child_asins     – deduplicated list of ASINs that are NOT the base ASIN
        variant_details – the raw variantDetails list (may be empty)
    """
    raw_asins = []

    # 1. variantDetails (most informative – carry attributes/price/image)
    variant_details_raw = []
    for vd in (item.get("variantDetails") or item.get("variant_details") or []):
        if not isinstance(vd, dict):
            continue
        variant_details_raw.append(vd)
        asin_val = vd.get("asin") or vd.get("ASIN")
        if _is_valid_asin(asin_val):
            raw_asins.append(asin_val.strip().upper())

    # 2. variantAsins (plain list)
    for a in (item.get("variantAsins") or item.get("variant_asins") or []):
        if _is_valid_asin(a):
            raw_asins.append(a.strip().upper())

    # 3. variants[] (legacy / actor-specific)
    for v in (item.get("variants") or []):
        if isinstance(v, dict):
            a = v.get("asin") or v.get("ASIN")
            if _is_valid_asin(a):
                raw_asins.append(a.strip().upper())

    # Deduplicate, exclude base ASIN (base is handled separately)
    seen = set()
    child_asins = []
    for a in raw_asins:
        if a != base_asin and a not in seen:
            seen.add(a)
            child_asins.append(a)

    return child_asins, variant_details_raw


def fetch_product_from_apify(amazon_url: str) -> dict:
    """
    Fetch one Amazon product page via Apify and return a normalised dict.

    The returned dict now includes:
      • variant_asins   – deduplicated child ASINs (base ASIN excluded)
      • variant_details – raw variantDetails records from Apify
    so that the worker's extractor can build Shopify variants without
    making a redundant second call for products that already carry
    all the information inside the parent page response.
    """
    client = ApifyClient(settings.APIFY_API_TOKEN)
    actor_id = "delicious_zebu/amazon-product-details-scraper"
    run_input = {
        "Params": [amazon_url],
        "scrapeProductDetails": True,
        "country": "US",
        "zipCode": "30024",
    }

    try:
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = (
            run.get("defaultDatasetId")
            if isinstance(run, dict)
            else run.default_dataset_id
        )
        items = client.dataset(dataset_id).iterate_items()

        for item in items:
            if not isinstance(item, dict):
                continue

            asin = item.get("asin") or extract_asin_from_url(amazon_url)
            if asin:
                asin = asin.strip().upper()
            parent_asin = validate_parent_asin(item.get("parent_asin"), asin)

            # ── Availability ───────────────────────────────────────────
            is_available, avail_text, _reason = check_availability_apify(item)
            stock_qty = 100 if is_available else 0

            # ── Images (product images only, NOT galleryThumbnails) ────
            images_raw = item.get("images") or []
            if isinstance(images_raw, list):
                images = [img for img in images_raw if isinstance(img, str)]
            elif isinstance(images_raw, str):
                images = [images_raw]
            else:
                images = []

            # ── Price ──────────────────────────────────────────────────
            price = parse_price(item.get("buybox_price") or item.get("price"))

            # ── Feature bullets ────────────────────────────────────────
            bullets = item.get("about_item") or item.get("feature_bullets") or []
            if isinstance(bullets, str):
                bullets = [line.strip() for line in bullets.split("\n") if line.strip()]
            if not bullets:
                bullets = ["Check Amazon for full product details."]

            # ── Specifications ─────────────────────────────────────────
            specs = {}
            for detail in (item.get("product_details") or []):
                if isinstance(detail, dict) and detail.get("type") and detail.get("value"):
                    specs[detail["type"]] = str(detail["value"]).strip()

            # ── Breadcrumb categories ──────────────────────────────────
            categories = []
            breadcrumbs = item.get("breadCrumbs") or item.get("breadcrumbs") or ""
            if breadcrumbs and isinstance(breadcrumbs, str):
                categories = [
                    c.strip()
                    for c in breadcrumbs.replace("›", ">").split(">")
                    if c.strip()
                ]
            categories = list(dict.fromkeys(
                [str(c).strip() for c in categories
                 if c and str(c).strip() and len(str(c)) < 100]
            ))

            # ── Variant attributes for THIS (base) page ────────────────
            variant_attributes = []
            for v in (item.get("variants") or []):
                if isinstance(v, dict):
                    for attr in (v.get("attributes") or v.get("attributes_list") or []):
                        if isinstance(attr, str) and ":" in attr:
                            name, value = attr.split(":", 1)
                            name, value = name.strip(), value.strip()
                            if name and value:
                                variant_attributes.append({"name": name, "value": value})

            if not variant_attributes:
                for dv in (item.get("default_variant") or []):
                    if isinstance(dv, str) and ":" in dv:
                        name, value = dv.split(":", 1)
                        name, value = name.strip(), value.strip()
                        if name and value:
                            variant_attributes.append({"name": name, "value": value})

            # ── Child ASIN extraction ──────────────────────────────────
            child_asins, variant_details = _extract_child_asins_from_raw(item, asin)

            logger.info(
                f"[Apify] ASIN={asin} | "
                f"child_asins_found={len(child_asins)} | "
                f"variant_details_records={len(variant_details)}"
            )

            return {
                # Core identifiers
                "asin": asin,
                "parent_asin": parent_asin,
                "is_variation": bool(parent_asin),
                # Content
                "title": item.get("title") or "Untitled Product",
                "brand": item.get("brand") or item.get("manufacturer") or "",
                "description": "",
                "feature_bullets": bullets,
                # Pricing
                "amazon_price": price,
                "list_price": None,
                # Images (product images only, gallery excluded)
                "image_url": images[0] if images else None,
                "images": images,
                # Availability
                "availability": avail_text,
                "is_available": is_available,
                "stock_quantity": stock_qty,
                # Taxonomy
                "categories": categories,
                "tags": item.get("tags") or [],
                # Specs / details
                "specifications": specs,
                "product_details": item.get("product_details") or [],
                # Physical attributes
                "item_weight": item.get("item_weight") or item.get("weight"),
                "item_dimensions": item.get("item_dimensions") or item.get("dimensions"),
                "package_dimensions": item.get("package_dimensions"),
                "model_number": item.get("model_number"),
                "manufacturer": item.get("manufacturer"),
                # Variation data
                # variant_attributes: the options visible on THIS page
                "variant_attributes": variant_attributes,
                "variations": variant_attributes,          # legacy alias
                # child_asins: all OTHER ASINs in the same variation family
                "variant_asins": child_asins,
                # variant_details: raw Apify variantDetails records
                # (per-child attributes, prices, images)
                "variant_details": variant_details,
            }

        return {}

    except Exception as e:
        raise ApifyError(f"Apify Error: {str(e)}")