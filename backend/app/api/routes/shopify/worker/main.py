# app/api/routes/shopify/worker/main.py
import asyncio
import logging
from app.core.database import SessionLocal
from app.models import Product, ShopifyStore
from app.services.amazon import ApifyError, fetch_product_from_apify
from ..helpers import _resolve_markup, apply_markup_cap, _get_valid_access_token
from .extractor import extract_variants_data
from .db_sync import save_or_update_db_product
from .shopify_sync import push_to_shopify

logger = logging.getLogger(__name__)

async def _background_fetch_and_push(
    amazon_url: str,
    shop_domain: str,
    store_id: int,
    markup,
    markup_type,
    extra_percent,
    collection_ids: list,
):
    db = SessionLocal()
    try:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == store_id).first()
        if not store:
            return

        loop = asyncio.get_running_loop()

        # ── 1. Fetch parent product page via Apify ─────────────────────
        try:
            data = await loop.run_in_executor(None, fetch_product_from_apify, amazon_url)
        except ApifyError as e:
            logger.error(f"[Worker] Apify fetch failed for {amazon_url}: {e}")
            return

        if not data or not data.get("asin"):
            logger.error(f"[Worker] No ASIN returned for {amazon_url}")
            return

        base_asin = data["asin"]

        # ── 2. Log variation discovery stats ──────────────────────────
        variant_asins = data.get("variant_asins") or []
        variant_details = data.get("variant_details") or []
        logger.info(
            f"[Worker] base_asin={base_asin} | "
            f"variant_asins_discovered={len(variant_asins)} | "
            f"variant_details_records={len(variant_details)}"
        )

        # Build the variant_details_map (ASIN → detail record).
        # The extractor rebuilds this internally, but we pass it for
        # backward-compat with any future callers that use the map directly.
        raw_details = variant_details
        variant_details_map = {
            vd["asin"].strip().upper(): vd
            for vd in raw_details
            if isinstance(vd, dict) and vd.get("asin")
        }

        # ── 3. Extract and normalise all variant data ──────────────────
        prepared_variants = await extract_variants_data(
            amazon_url, data, variant_details_map, loop
        )
        logger.info(
            f"[Worker] prepared_variants={len(prepared_variants)} "
            f"for base_asin={base_asin}"
        )

        # ── 4. Check for existing Shopify product ──────────────────────
        existing_shopify_product_id = None
        existing_parent_db = (
            db.query(Product)
            .filter(
                Product.asin == base_asin,
                Product.shopify_product_id.isnot(None),
            )
            .first()
        )
        if existing_parent_db:
            existing_shopify_product_id = existing_parent_db.shopify_product_id

        # ── 5. Apply markup ────────────────────────────────────────────
        user_markup, user_markup_type, user_extra, user_tax_rate = _resolve_markup(
            store, markup, markup_type, extra_percent
        )
        user_markup = apply_markup_cap(user_markup, user_markup_type)
        access_token = await _get_valid_access_token(store, db)

        # ── 6. Persist each variant to DB ──────────────────────────────
        for vp in prepared_variants:
            vp = save_or_update_db_product(
                db, data, base_asin, vp,
                user_markup, user_markup_type, user_extra, user_tax_rate,
                store.id, existing_shopify_product_id,
            )

        # ── 7. Push one Shopify product with all variants ──────────────
        pushed, failed, new_id = await push_to_shopify(
            shop_domain, access_token, data,
            prepared_variants, existing_shopify_product_id,
            collection_ids, base_asin,
        )

        # ── 8. Back-fill shopify_product_id on newly created product ──
        if new_id and not existing_shopify_product_id:
            for vp in prepared_variants:
                if vp.get("db_product"):
                    vp["db_product"].shopify_product_id = new_id
            db.commit()

        logger.info(
            f"[Worker] DONE | base_asin={base_asin} | "
            f"shopify_id={new_id or existing_shopify_product_id} | "
            f"variants_pushed={pushed} | "
            f"variants_failed={failed}"
        )

    except Exception as e:
        logger.exception(f"[Worker] Background task crashed: {e}")
    finally:
        db.close()

