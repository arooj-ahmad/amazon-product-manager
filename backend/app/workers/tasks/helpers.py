# app/workers/tasks/helpers.py
import logging

logger = logging.getLogger(__name__)

def _get_store_for_product(db, product, fallback_store_id: int = None):
    from app.models import ShopifyStore
    store = None
    if product and product.shopify_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == product.shopify_store_id).first()
    if not store and fallback_store_id:
        store = db.query(ShopifyStore).filter(ShopifyStore.id == fallback_store_id).first()
    if not store:
        store = db.query(ShopifyStore).first()
    return store
