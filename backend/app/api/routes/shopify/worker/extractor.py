# app/api/routes/shopify/worker/extractor.py
# ============================================================
# Extracts and normalises all variation data from the Apify
# response before Shopify product creation.
#
# Strategy:
#  1. Collect child ASINs from variant_asins + variant_details
#     (already deduplicated by apify_scraper.py).
#  2. Always prepend the base ASIN so it is Variant #1.
#  3. For each child ASIN, check the variantDetails records
#     first (free — already in the response).  Only perform a
#     separate Apify fetch when price OR attributes are still
#     missing after inspecting variantDetails.
#  4. Map attributes → Shopify option name/value pairs.
#  5. Fall back to base product data for any field that
#     remains empty after all sources are exhausted.
# ============================================================
import logging
from app.services.amazon import ApifyError, fetch_product_from_apify, parse_price
from ..helpers import _extract_weight, extract_all_variations

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _parse_variant_detail_attrs(vd: dict) -> list:
    """
    Extract option attributes from a single variantDetails record.
    The actor may use different key names depending on its version.
    """
    attrs = []

    # Priority 1: dedicated attributes list
    for attr in (vd.get("attributes") or vd.get("variationAttributes") or []):
        if isinstance(attr, dict):
            name = (attr.get("name") or attr.get("attributeName") or "").strip()
            value = str(attr.get("value") or attr.get("attributeValue") or "").strip()
            if name and value:
                attrs.append({"name": name, "value": value})
        elif isinstance(attr, str) and ":" in attr:
            name, value = attr.split(":", 1)
            name, value = name.strip(), value.strip()
            if name and value:
                attrs.append({"name": name, "value": value})

    if attrs:
        return attrs

    # Priority 2: flat key/value pairs on the record itself
    for key in ("color", "size", "style", "flavor", "scent", "configuration"):
        val = vd.get(key) or vd.get(key.capitalize())
        if val and str(val).strip():
            attrs.append({"name": key.capitalize(), "value": str(val).strip()})

    return attrs


def _build_variant_details_map(variant_details: list) -> dict:
    """Build a dict keyed by ASIN for O(1) lookups."""
    mapping = {}
    for vd in (variant_details or []):
        if not isinstance(vd, dict):
            continue
        asin = (vd.get("asin") or vd.get("ASIN") or "").strip().upper()
        if asin:
            mapping[asin] = vd
    return mapping


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

async def extract_variants_data(amazon_url: str, data: dict,
                                 variant_details_map_unused: dict,
                                 loop) -> list:
    """
    Build a normalised list of variant dicts, one per child ASIN
    (plus the base ASIN as the first entry), ready for DB + Shopify.

    Logging summary:
      - Number of variation sources discovered
      - Unique child ASINs after deduplication
      - How many required an individual Apify fetch
      - Per-variant result (success / partial / failure)
    """
    base_asin = (data.get("asin") or "").strip().upper()

    # ── Step 1: Collect all known child ASINs ─────────────────────────
    # apify_scraper.py already merged and deduplicated variant_asins;
    # we re-read the raw sources here to build a variant_details map
    # that includes ALL records, even those without a valid ASIN.
    raw_variant_asins = [
        a.strip().upper()
        for a in (data.get("variant_asins") or [])
        if a and isinstance(a, str) and a.strip()
    ]
    raw_variant_details = data.get("variant_details") or []
    vd_map = _build_variant_details_map(raw_variant_details)

    logger.info(
        f"[Extractor] ASIN={base_asin} | "
        f"variant_asins_from_scraper={len(raw_variant_asins)} | "
        f"variant_details_records={len(raw_variant_details)}"
    )

    # ── Step 2: Build ordered, deduplicated ASIN list ─────────────────
    # Base ASIN always comes first; child ASINs follow in discovery order.
    seen: set = {base_asin} if base_asin else set()
    ordered_asins: list = [base_asin] if base_asin else []

    for a in raw_variant_asins:
        if a and a not in seen:
            seen.add(a)
            ordered_asins.append(a)

    # Also pick up any ASINs present only in variant_details
    for asin_key in vd_map:
        if asin_key not in seen:
            seen.add(asin_key)
            ordered_asins.append(asin_key)

    logger.info(
        f"[Extractor] unique_asins_total={len(ordered_asins)} "
        f"(base={base_asin}, children={len(ordered_asins) - 1})"
    )

    # ── Step 3: Build prepared data for each ASIN ─────────────────────
    prepared_data: list = []
    fetch_count = 0
    failure_count = 0

    for index, v_asin in enumerate(ordered_asins):
        try:
            # ── Base ASIN: use the already-fetched parent page data ────
            if v_asin == base_asin:
                v_attrs = data.get("variant_attributes") or []
                v_price = data.get("amazon_price")
                v_imgs = data.get("images") or []
                v_thumb = data.get("image_url")
                v_name = data.get("title") or ""
                v_availability = data.get("availability") or "In Stock"
                v_is_available = data.get("is_available", True)
                v_stock = data.get("stock_quantity", 100) if v_is_available else 0
                v_weight = _extract_weight(data)
                v_data = data

            # ── Child ASIN ─────────────────────────────────────────────
            else:
                vd = vd_map.get(v_asin) or {}
                v_attrs = _parse_variant_detail_attrs(vd)
                v_price = parse_price(
                    vd.get("price") or vd.get("buybox_price") or vd.get("salePrice")
                )
                # images: prefer a dedicated images list, then thumbnail field
                v_imgs = vd.get("images") or []
                v_thumb = (
                    vd.get("thumbnail")
                    or vd.get("image")
                    or vd.get("imageUrl")
                    or vd.get("mainImage")
                )
                v_name = vd.get("name") or vd.get("title") or ""
                v_availability = vd.get("availability") or data.get("availability") or "In Stock"
                v_is_available = (
                    vd.get("is_available")
                    if vd.get("is_available") is not None
                    else data.get("is_available", True)
                )
                v_stock = (
                    int(vd.get("stock_quantity") or 0)
                    if not v_is_available
                    else int(vd.get("stock_quantity") or data.get("stock_quantity") or 100)
                )
                v_weight = _extract_weight(vd) or _extract_weight(data)
                v_data = None

                # ── Conditional fetch: only when essential data is missing ─
                needs_fetch = v_price is None or not v_attrs
                if needs_fetch:
                    logger.info(
                        f"[Extractor] Fetching child ASIN {v_asin} "
                        f"(missing: {'price' if v_price is None else ''}"
                        f"{'|attrs' if not v_attrs else ''})"
                    )
                    try:
                        v_data = await loop.run_in_executor(
                            None,
                            fetch_product_from_apify,
                            f"https://www.amazon.com/dp/{v_asin}",
                        )
                        fetch_count += 1
                        if v_data:
                            if v_data.get("amazon_price") is not None:
                                v_price = v_data["amazon_price"]
                            if v_data.get("variant_attributes"):
                                v_attrs = v_data["variant_attributes"]
                            if v_data.get("images"):
                                v_imgs = v_data["images"]
                            if v_data.get("image_url"):
                                v_thumb = v_data["image_url"]
                            if v_data.get("title"):
                                v_name = v_data["title"]
                            if v_data.get("availability"):
                                v_availability = v_data["availability"]
                            if v_data.get("is_available") is not None:
                                v_is_available = v_data["is_available"]
                            if v_data.get("stock_quantity") is not None:
                                v_stock = v_data["stock_quantity"]
                            if not v_weight:
                                v_weight = _extract_weight(v_data)
                    except Exception as fetch_err:
                        failure_count += 1
                        logger.warning(
                            f"[Extractor] Child fetch failed for {v_asin}: {fetch_err}"
                        )

                # If still no price after fetch, inherit from base product
                if v_price is None:
                    v_price = data.get("amazon_price")
                    logger.warning(
                        f"[Extractor] {v_asin}: price still missing — "
                        f"inheriting base price {v_price}"
                    )

            # ── Attribute fallback chain ──────────────────────────────
            if not v_attrs:
                v_attrs = extract_all_variations(v_data or {})
                if not v_attrs or (
                    len(v_attrs) == 1 and v_attrs[0].get("value") == "Default"
                ):
                    # Use the variant name (title) as a Style label so the
                    # variant is still distinguishable in Shopify.
                    v_attrs = [
                        {"name": "Style", "value": v_name or f"Variant {index + 1}"}
                    ]

            # ── Resolve image URL ──────────────────────────────────────
            img_url = (
                (v_imgs[0] if v_imgs else None)
                or v_thumb
                or (v_data.get("image_url") if v_data else None)
                or data.get("image_url")
            )

            prepared_data.append({
                "asin": v_asin,
                "title": v_name or v_asin,
                "amazon_price": v_price,
                # "attributes" drives Shopify option mapping
                "attributes": v_attrs,
                "weight": v_weight,
                "image_url": img_url,
                "images": v_imgs or data.get("images", []),
                "availability": v_availability,
                "is_available": v_is_available,
                "stock_quantity": v_stock,
                # raw fetched data (used by db_sync.py for extra fields)
                "raw_v_data": v_data,
            })

            logger.info(
                f"[Extractor] variant[{index}] ASIN={v_asin} "
                f"price={v_price} attrs={[a['name'] for a in v_attrs]} "
                f"img={'yes' if img_url else 'no'}"
            )

        except Exception as variant_err:
            failure_count += 1
            logger.error(
                f"[Extractor] Unexpected error processing {v_asin}: {variant_err}"
            )
            # Do NOT silently discard — append a minimal fallback entry
            prepared_data.append({
                "asin": v_asin,
                "title": f"Variant {index + 1}",
                "amazon_price": data.get("amazon_price"),
                "attributes": [{"name": "Style", "value": f"Variant {index + 1}"}],
                "weight": None,
                "image_url": data.get("image_url"),
                "images": data.get("images", []),
                "availability": "In Stock",
                "is_available": True,
                "stock_quantity": 0,
                "raw_v_data": None,
            })

    logger.info(
        f"[Extractor] DONE | base={base_asin} | "
        f"total_variants={len(prepared_data)} | "
        f"individual_fetches={fetch_count} | "
        f"fetch_failures={failure_count}"
    )
    return prepared_data

