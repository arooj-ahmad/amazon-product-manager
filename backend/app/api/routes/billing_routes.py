# ============================================
# app/services/billing.py
# Shopify Billing API integration
# ============================================

import logging

from app.services.shopify import shopify_graphql

logger = logging.getLogger(__name__)


# ============================================
# BILLING PLANS CONFIGURATION
# ============================================
BILLING_PLANS = {
    "basic": {
        "name": "Basic Plan",
        "price": 9.99,
        "currency": "USD",
        "interval": "EVERY_30_DAYS",
        "trial_days": 7,
        "features": [
            "Unlimited product imports",
            "Auto price sync",
            "Multi-image support",
            "Email support",
        ],
    },
    "pro": {
        "name": "Pro Plan",
        "price": 29.99,
        "currency": "USD",
        "interval": "EVERY_30_DAYS",
        "trial_days": 7,
        "features": [
            "Everything in Basic",
            "Bulk imports",
            "Priority support",
            "Advanced analytics",
        ],
    },
}


# ============================================
# CREATE SUBSCRIPTION
# ============================================
async def create_subscription(
    shop: str,
    access_token: str,
    plan_key: str,
    return_url: str,
) -> dict:
    """
    Naya subscription create karta hai.
    Merchant ko Shopify confirmation page par redirect karta hai.
    """
    plan = BILLING_PLANS.get(plan_key)
    if not plan:
        return {"error": f"Invalid plan: {plan_key}"}

    mutation = """
    mutation appSubscriptionCreate(
      $name: String!
      $returnUrl: URL!
      $trialDays: Int!
      $test: Boolean!
      $lineItems: [AppSubscriptionLineItemInput!]!
    ) {
      appSubscriptionCreate(
        name: $name
        returnUrl: $returnUrl
        trialDays: $trialDays
        test: $test
        lineItems: $lineItems
      ) {
        confirmationUrl
        appSubscription {
          id
          status
          name
          trialDays
          currentPeriodEnd
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "name": plan["name"],
        "returnUrl": return_url,
        "trialDays": plan["trial_days"],
        "test": True,  # ⚠️ Production mein False karein
        "lineItems": [
            {
                "plan": {
                    "appRecurringPricingDetails": {
                        "price": {
                            "amount": plan["price"],
                            "currencyCode": plan["currency"],
                        },
                        "interval": plan["interval"],
                    }
                }
            }
        ],
    }

    result = await shopify_graphql(shop, access_token, mutation, variables)

    if "errors" in result:
        logger.error(f"Subscription create error: {result['errors']}")
        return result

    sub_data = result.get("data", {}).get("appSubscriptionCreate", {})
    user_errors = sub_data.get("userErrors", [])

    if user_errors:
        logger.error(f"Subscription user errors: {user_errors}")
        return {"errors": user_errors}

    return {
        "confirmation_url": sub_data.get("confirmationUrl"),
        "subscription": sub_data.get("appSubscription"),
    }


# ============================================
# CHECK ACTIVE SUBSCRIPTION
# ============================================
async def get_active_subscription(
    shop: str,
    access_token: str,
) -> dict:
    """
    Shop ke active subscriptions check karta hai.
    """
    query = """
    query {
      currentAppInstallation {
        activeSubscriptions {
          id
          name
          status
          currentPeriodEnd
          trialDays
          createdAt
        }
      }
    }
    """

    result = await shopify_graphql(shop, access_token, query)

    if "errors" in result:
        logger.error(f"Subscription query error: {result['errors']}")
        return {"active": False, "error": result["errors"]}

    subscriptions = (
        result.get("data", {})
        .get("currentAppInstallation", {})
        .get("activeSubscriptions", [])
    )

    if not subscriptions:
        return {"active": False, "subscription": None}

    sub = subscriptions[0]

    return {
        "active": sub.get("status") == "ACTIVE",
        "subscription": {
            "id": sub.get("id"),
            "name": sub.get("name"),
            "status": sub.get("status"),
            "current_period_end": sub.get("currentPeriodEnd"),
            "trial_days": sub.get("trialDays"),
        },
    }