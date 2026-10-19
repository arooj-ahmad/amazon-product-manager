# register_webhooks.py
# ✅ FIXED: Latest store use karo (first store expired tha)
# ✅ FIXED: WEBHOOK_URL apna actual URL
# ✅ FIXED: Debug ke liye store info print

import asyncio
import sys

from sqlalchemy import desc

from app.database import SessionLocal
from app.models import ShopifyStore
from app.services.shopify import shopify_graphql


# ✅ FIXED: Apna actual deployed URL yahan daalo
WEBHOOK_URL = "https://amazon-product-manager-production.up.railway.app/api/webhooks/shopify"


async def register_webhooks():
    db = SessionLocal()
    try:
        # ✅ FIXED: Sabse recent store use karo (first nahi)
        store = (
            db.query(ShopifyStore)
            .order_by(desc(ShopifyStore.installed_at))
            .first()
        )

        if not store:
            print("❌ No store found")
            return

        # ✅ Debug info
        print(f"🛒 Store: {store.shop_domain}")
        print(f"🆔 Store ID: {store.id}")
        print(f"📅 Installed: {store.installed_at}")
        print(f"⏰ Expires: {store.expires_at}")
        print(f"🔗 Webhook URL: {WEBHOOK_URL}")
        print("-" * 60)

        # Register webhooks
        topics = [
            "PRODUCTS_DELETE",
            "PRODUCTS_UPDATE",
        ]

        for topic in topics:
            mutation = """
            mutation webhookSubscriptionCreate(
              $topic: WebhookSubscriptionTopic!,
              $webhookSubscription: WebhookSubscriptionInput!
            ) {
              webhookSubscriptionCreate(
                topic: $topic,
                webhookSubscription: $webhookSubscription
              ) {
                webhookSubscription {
                  id
                  topic
                  endpoint {
                    __typename
                    ... on WebhookHttpEndpoint {
                      callbackUrl
                    }
                  }
                }
                userErrors {
                  field
                  message
                }
              }
            }
            """

            variables = {
                "topic": topic,
                "webhookSubscription": {
                    "callbackUrl": WEBHOOK_URL,
                    "format": "JSON",
                },
            }

            result = await shopify_graphql(
                store.shop_domain,
                store.access_token,
                mutation,
                variables,
            )

            if "errors" in result:
                print(f"❌ {topic}: {result['errors']}")
            else:
                sub = (
                    result.get("data", {})
                    .get("webhookSubscriptionCreate", {})
                )
                user_errors = sub.get("userErrors", [])
                if user_errors:
                    print(f"⚠️ {topic}: {user_errors}")
                else:
                    webhook = sub.get("webhookSubscription", {})
                    print(f"✅ {topic} webhook registered")
                    print(f"   ID: {webhook.get('id')}")
                    print(f"   URL: {webhook.get('endpoint', {}).get('callbackUrl')}")

    finally:
        db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(register_webhooks())