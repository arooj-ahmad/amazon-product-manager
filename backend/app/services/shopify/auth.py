# ============================================
# app/services/shopify_auth.py
# OAuth flow, HMAC verify, JWT ID token verify,
# access token exchange and refresh
# ============================================

import hashlib
import hmac
import logging
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================
# OAUTH: AUTH URL BANAO
# ============================================
def build_auth_url(shop: str, state: str = "default") -> str:
    """Shopify OAuth authorize URL banata hai."""
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": settings.SHOPIFY_SCOPES,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "state": state,
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


# ============================================
# OAUTH: HMAC VERIFY KARO
# ============================================
def verify_hmac(query_params: dict) -> bool:
    """Shopify OAuth callback ka HMAC verify karta hai."""
    received_hmac = query_params.get("hmac")
    if not received_hmac:
        return False

    params = {k: v for k, v in query_params.items() if k != "hmac"}
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    computed_hmac = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, received_hmac)


# ============================================
# ID TOKEN VERIFY
# ============================================
def verify_id_token(token: str) -> dict:
    """Shopify App Bridge session token (ID token) verify karta hai."""
    secret = (settings.SHOPIFY_API_SECRET or "").strip().strip('"').strip("'")
    api_key = (settings.SHOPIFY_API_KEY or "").strip().strip('"').strip("'")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=api_key,
            leeway=10,
        )

        now = int(time.time())

        if payload.get("exp", 0) < now:
            raise ValueError("Token expired")

        if payload.get("nbf", 0) > now:
            raise ValueError("Token not yet valid")

        iss = payload.get("iss", "")
        if not iss.startswith("https://"):
            raise ValueError("Invalid issuer")

        iss_domain = iss.replace("https://", "").split("/")[0]
        dest_domain = (
            payload.get("dest", "").replace("https://", "").split("/")[0]
        )

        if iss_domain != dest_domain:
            raise ValueError("Domain mismatch")

        if not iss_domain.endswith(".myshopify.com"):
            raise ValueError("Not a valid Shopify store")

        logger.info(f"ID token verified for: {iss_domain}")
        return payload

    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")

    except jwt.InvalidTokenError as e:
        # Debugging ke liye unverified payload log karo
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logger.warning(
                f"ID token diag | token aud={unverified.get('aud')} "
                f"iss={unverified.get('iss')} | server api_key={api_key} "
                f"secret_prefix={secret[:10]}... secret_len={len(secret)}"
            )
        except Exception:
            pass
        raise ValueError(f"Invalid token: {e}")


# ============================================
# OAUTH: ACCESS TOKEN EXCHANGE (authorization code se)
# ============================================
async def exchange_code_for_token(shop: str, code: str) -> Optional[dict]:
    """Authorization code ko access token me exchange karta hai."""
    url = f"https://{shop}/admin/oauth/access_token"

    payload = {
        "client_id": settings.SHOPIFY_API_KEY,
        "client_secret": settings.SHOPIFY_API_SECRET,
        "code": code,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ Token exchanged for {shop}")
            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Token exchange HTTP error for {shop}: "
            f"{e.response.status_code} - {e.response.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"Token exchange fail for {shop}: {e}")
        return None


# ============================================
# TOKEN EXCHANGE (ID token → Offline access token)
# ============================================
async def exchange_id_token_for_offline_token(
    shop: str, id_token: str
) -> Optional[dict]:
    """
    App Bridge ke ID token ko offline access token me exchange karta hai.
    Ye Shopify ke naye token exchange flow ke liye hai.
    """
    url = f"https://{shop}/admin/oauth/access_token"

    payload = {
        "client_id": (settings.SHOPIFY_API_KEY or "").strip(),
        "client_secret": (settings.SHOPIFY_API_SECRET or "").strip(),
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": id_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "requested_token_type": (
            "urn:shopify:params:oauth:token-type:offline-access-token"
        ),
        "expiring": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                logger.error(
                    f"❌ Token exchange (id_token) failed for {shop}: "
                    f"{response.status_code} {response.text[:200]}"
                )
                return None

            data = response.json()
            logger.info(f"✅ Offline token obtained via token exchange: {shop}")
            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }
    except Exception as e:
        logger.error(f"Token exchange (id_token) error for {shop}: {e}")
        return None


# ============================================
# TOKEN REFRESH
# ============================================
async def refresh_shopify_token(
    shop_domain: str,
    refresh_token: str,
) -> Optional[dict]:
    """
    Refresh token se naya access token le kar aata hai.
    
    Returns:
        dict with keys: access_token, scope, expires_in, 
                        refresh_token, refresh_token_expires_in
        None agar refresh fail ho jaye.
    """
    if not refresh_token:
        logger.warning(f"No refresh_token provided for {shop_domain}")
        return None

    url = f"https://{shop_domain}/admin/oauth/access_token"

    payload = {
        "client_id": (settings.SHOPIFY_API_KEY or "").strip(),
        "client_secret": (settings.SHOPIFY_API_SECRET or "").strip(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                logger.error(
                    f"❌ Token refresh failed for {shop_domain}: "
                    f"{response.status_code} {response.text[:200]}"
                )
                return None

            data = response.json()
            logger.info(f"✅ Access token refreshed for {shop_domain}")

            return {
                "access_token": data.get("access_token"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token": data.get("refresh_token"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            }

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Token refresh HTTP error for {shop_domain}: "
            f"{e.response.status_code} - {e.response.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"Token refresh error for {shop_domain}: {e}")
        return None