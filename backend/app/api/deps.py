# app/api/deps.py
# Shared FastAPI dependencies (get_db, current_user, etc.)

from app.core.database import get_db  # noqa

# Future additions:
# - get_current_admin
# - get_shopify_store
# - get_current_subscription
