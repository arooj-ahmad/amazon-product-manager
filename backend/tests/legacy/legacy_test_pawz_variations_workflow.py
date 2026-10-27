# ============================================
# test_pawz_variations_workflow.py
# Tests for Amazon-to-Shopify all-variants workflow
# using actual Apify PAWZ scraper response schema
# ============================================

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.amazon.helpers import parse_price
from app.services.amazon.apify_scraper import fetch_product_from_apify
from app.services.shopify.product_core import create_shopify_product_with_variants
from app.api.routes.shopify.background_worker import _background_fetch_and_push


class TestPawzVariationsWorkflow(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.pawz_file = os.path.join(os.path.dirname(__file__), "apify_pawz_actual.json")
        with open(self.pawz_file, "r", encoding="utf-8") as f:
            self.pawz_raw = json.load(f)

    def test_01_parse_price_dict_and_formats(self):
        """Test parse_price handles numbers, strings, and Apify dict formats."""
        self.assertEqual(parse_price({"value": 39.99, "currency": "$"}), 39.99)
        self.assertEqual(parse_price({"amount": "54.99"}), 54.99)
        self.assertEqual(parse_price("$39.99"), 39.99)
        self.assertEqual(parse_price(39.99), 39.99)
        self.assertIsNone(parse_price(None))
        self.assertIsNone(parse_price(""))
        self.assertIsNone(parse_price({"other": "none"}))

    def test_02_pawz_extraction_and_deduplication(self):
        """
        Verify that child ASINs are extracted from variantAsins and/or variantDetails,
        merged, deduplicated, and ensure the input ASIN is included.
        Verify galleryThumbnails and highResolutionImages are not treated as variations.
        """
        mock_run = MagicMock()
        mock_run.default_dataset_id = "test_dataset"
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [self.pawz_raw]

        mock_actor = MagicMock()
        mock_actor.call.return_value = mock_run

        mock_client = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_client.dataset.return_value = mock_dataset

        with patch("app.services.amazon.apify_scraper.ApifyClient", return_value=mock_client), \
             patch("app.services.amazon.apify_scraper.settings") as mock_settings:
            mock_settings.APIFY_API_TOKEN = "test_token"
            mock_settings.APIFY_ACTOR_ID = "junglee/amazon-crawler"

            url = "https://www.amazon.com/dp/B0H2G36YMB"
            parsed = fetch_product_from_apify(url)

        # 1. Base product data
        self.assertEqual(parsed["asin"], "B0H2G36YMB")
        self.assertEqual(parsed["brand"], "PAWZ")
        self.assertEqual(parsed["amazon_price"], 39.99)
        self.assertEqual(parsed["list_price"], 54.99)
        self.assertTrue(parsed["is_available"])

        # 2. Images: highResolutionImages used as product images, NOT variations
        self.assertEqual(len(parsed["images"]), 8)
        self.assertTrue(all("https://m.media-amazon.com/images/I/" in img for img in parsed["images"]))

        # 3. Variations: Exactly 18 unique ASINs
        variant_asins = parsed["variant_asins"]
        self.assertEqual(len(variant_asins), 18)
        self.assertEqual(len(set(variant_asins)), 18)  # deduplicated
        self.assertIn("B0H2G36YMB", variant_asins)     # input ASIN included

        # 4. Variant details list matches 18 entries
        variant_details = parsed["variant_details"]
        self.assertEqual(len(variant_details), 18)

        # Check that attributes are mapped
        for vd in variant_details:
            self.assertTrue(vd["asin"])
            self.assertTrue(len(vd["attributes"]) >= 1)
            # Either Size/Color or Style
            attr_names = [a["name"] for a in vd["attributes"]]
            self.assertTrue("Size" in attr_names or "Style" in attr_names)

    async def test_03_create_shopify_product_with_variants_structure(self):
        """
        Verify that create_shopify_product_with_variants builds:
        - 1 Shopify product
        - productOptions matching attributes (e.g. Size, Color) <= 3
        - 18 Shopify variants (within limits)
        - Preserves each child ASIN in SKU and variant metafield custom.asin
        """
        product_data = {
            "title": "PAWZ Womens Ariel Boots",
            "description": "Cozy boots",
            "brand": "PAWZ",
            "price": "39.99",
            "amazon_price": 39.99,
            "images": ["https://example.com/img1.jpg"],
            "categories": ["Shoes", "Boots"],
            "tags": ["Women's Boots"],
            "is_available": True,
            "variant_attributes": [
                {"name": "Size", "value": "6"},
                {"name": "Color", "value": "Cognac"},
            ],
        }

        # 18 variants like PAWZ
        sizes = ["5", "6", "7", "8", "9", "10", "11", "12", "13"]
        colors = ["Cognac", "Black II"]
        variants = []
        idx = 0
        for s in sizes:
            for c in colors:
                asin = f"B0H2VAR{idx:03d}"
                variants.append({
                    "asin": asin,
                    "title": f"{s} {c}",
                    "price": 45.99,
                    "amazon_price": 39.99,
                    "stock": 100,
                    "weight": "16 ounces",
                    "image_url": "https://example.com/boot.jpg",
                    "options": [
                        {"name": "Size", "value": s},
                        {"name": "Color", "value": c},
                    ],
                })
                idx += 1

        self.assertEqual(len(variants), 18)

        captured_graphql = {}

        async def mock_graphql(shop, token, query, variables):
            captured_graphql["query"] = query
            captured_graphql["variables"] = variables
            # Mock Shopify response for productSet
            return {
                "data": {
                    "productSet": {
                        "product": {
                            "id": "gid://shopify/Product/99887766",
                            "title": "PAWZ Womens Ariel Boots",
                            "variants": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": f"gid://shopify/ProductVariant/{1000 + i}",
                                            "inventoryItem": {"id": f"gid://shopify/InventoryItem/{2000 + i}", "sku": v["asin"]},
                                        }
                                    }
                                    for i, v in enumerate(variants)
                                ]
                            },
                        },
                        "userErrors": [],
                    }
                }
            }

        with patch("app.services.shopify.product_core.shopify_graphql", side_effect=mock_graphql), \
             patch("app.services.shopify.product_core.publish_product_to_channels", new_callable=AsyncMock), \
             patch("app.services.shopify.product_core.set_product_metafields", new_callable=AsyncMock), \
             patch("app.services.shopify.product_core.set_inventory_quantity", new_callable=AsyncMock) as mock_inventory, \
             patch("app.services.shopify.product_core._assign_image_to_variant", new_callable=AsyncMock) as mock_assign_img, \
             patch("app.services.shopify.product_core.add_product_images", new_callable=AsyncMock), \
             patch("app.services.shopify.product_core._find_category_from_breadcrumbs", new_callable=AsyncMock, return_value=None), \
             patch("app.services.shopify.product_core._get_compare_at_settings_from_store", return_value=(False, "none", 0.0)):

            result = await create_shopify_product_with_variants(
                shop="test.myshopify.com",
                access_token="shpat_test",
                product_data=product_data,
                variants=variants,
            )

        self.assertNotIn("errors", result)
        created_prod = result["data"]["productSet"]["product"]
        self.assertEqual(created_prod["id"], "gid://shopify/Product/99887766")

        # Verify variables sent to productSet
        inp = captured_graphql["variables"]["input"]
        self.assertEqual(inp["title"], "PAWZ Womens Ariel Boots")

        # Options verification: max 3 options, correctly populated
        options = inp["productOptions"]
        self.assertEqual(len(options), 2)
        opt_names = [o["name"] for o in options]
        self.assertIn("Size", opt_names)
        self.assertIn("Color", opt_names)

        size_opt = next(o for o in options if o["name"] == "Size")
        self.assertEqual(len(size_opt["values"]), 9)  # 9 unique sizes

        color_opt = next(o for o in options if o["name"] == "Color")
        self.assertEqual(len(color_opt["values"]), 2)  # 2 unique colors

        # Variants verification: exactly 18 variants in productSet
        created_variants = inp["variants"]
        self.assertEqual(len(created_variants), 18)

        # Check each variant preserves ASIN as SKU and in variant metafield custom.asin
        for i, cv in enumerate(created_variants):
            orig_v = variants[i]
            self.assertEqual(cv["inventoryItem"]["sku"], orig_v["asin"])
            self.assertEqual(cv["price"], "45.99")

            # Check variant metafield
            asin_mf = next((mf for mf in cv.get("metafields", []) if mf["key"] == "asin"), None)
            self.assertIsNotNone(asin_mf)
            self.assertEqual(asin_mf["value"], orig_v["asin"])
            self.assertEqual(asin_mf["namespace"], "custom")

        # Inventory updated for all 18 variants
        self.assertEqual(mock_inventory.call_count, 18)

        # Image assigned for all 18 variants
        self.assertEqual(mock_assign_img.call_count, 18)

    async def test_04_full_background_worker_workflow(self):
        """
        Verify end-to-end background worker workflow with the PAWZ example:
        - 1 input URL discovers 18 unique variations
        - Child ASIN details fetched only when needed (missing prices/attributes)
        - Safe price fallback if child fetch fails (do not silently discard)
        - Creates 1 Shopify product with all 18 variants
        - Preserves existing markup and tax calculations
        - Logs stats
        """
        parsed_pawz = fetch_product_from_apify.__wrapped__(
            "https://www.amazon.com/dp/B0H2G36YMB"
        ) if hasattr(fetch_product_from_apify, "__wrapped__") else None

        # Build parsed item from raw
        with patch("app.services.amazon.apify_scraper.settings") as mock_settings, \
             patch("app.services.amazon.apify_scraper.ApifyClient") as mock_client_cls:
            mock_run = MagicMock()
            mock_run.default_dataset_id = "ds_123"
            mock_client = MagicMock()
            mock_client.actor.return_value.call.return_value = mock_run
            mock_client.dataset.return_value.iterate_items.return_value = [self.pawz_raw]
            mock_client_cls.return_value = mock_client
            mock_settings.APIFY_API_TOKEN = "tok"
            mock_settings.APIFY_ACTOR_ID = "junglee/amazon-crawler"

            initial_data = fetch_product_from_apify("https://www.amazon.com/dp/B0H2G36YMB")

        self.assertEqual(len(initial_data["variant_asins"]), 18)

        # Mock DB
        mock_db = MagicMock()
        mock_store = MagicMock()
        mock_store.id = 1
        mock_store.shop_domain = "pawz-store.myshopify.com"
        mock_store.default_markup = 15.0
        mock_store.default_markup_type = "percent"
        mock_store.default_extra_percent = 0.0
        mock_store.default_tax_rate = 5.0
        mock_store.access_token = "shpat_test"

        # Mock query return values
        from app.models import ShopifyStore, Product
        q_store = MagicMock()
        q_store.filter.return_value.first.return_value = mock_store

        q_prod = MagicMock()
        q_prod.filter.return_value.first.return_value = None

        def query_side_effect(model):
            if model == ShopifyStore:
                return q_store
            return q_prod

        mock_db.query.side_effect = query_side_effect

        # Mock fetch_product_from_apify for child fetches
        # Simulate fetch failure for 1 child, success for others
        child_fetch_call_count = 0

        def mock_child_fetch(url):
            nonlocal child_fetch_call_count
            child_fetch_call_count += 1
            if "B0H2FXT24P" in url:
                raise Exception("Network timeout on Apify")
            return {
                "asin": url.split("/")[-1],
                "amazon_price": 42.99,
                "variant_attributes": [{"name": "Size", "value": "13"}, {"name": "Color", "value": "Cognac"}],
                "images": ["https://example.com/child.jpg"],
                "is_available": True,
                "stock_quantity": 50,
            }

        # Mock Shopify creation
        created_shopify_payload = {}
        async def mock_create_with_variants(shop, access_token, product_data, variants):
            created_shopify_payload["variants"] = variants
            created_shopify_payload["product_data"] = product_data
            return {
                "data": {
                    "productSet": {
                        "product": {
                            "id": "gid://shopify/Product/12345678",
                            "title": product_data["title"],
                            "variants": {
                                "edges": [
                                    {"node": {"id": f"gid://shopify/ProductVariant/{i}", "inventoryItem": {"id": f"gid://shopify/InventoryItem/{i}", "sku": v["asin"]}}}
                                    for i, v in enumerate(variants)
                                ]
                            }
                        },
                        "userErrors": [],
                    }
                }
            }

        def fetch_side_effect(url):
            if url == "https://www.amazon.com/dp/B0H2G36YMB":
                return initial_data
            return mock_child_fetch(url)

        with patch("app.api.routes.shopify.background_worker.SessionLocal", return_value=mock_db), \
             patch("app.api.routes.shopify.background_worker.fetch_product_from_apify", side_effect=fetch_side_effect), \
             patch("app.api.routes.shopify.background_worker.create_shopify_product_with_variants", side_effect=mock_create_with_variants), \
             patch("app.api.routes.shopify.background_worker._get_valid_access_token", new_callable=AsyncMock, return_value="shpat_valid"), \
             patch("app.api.routes.shopify.background_worker.add_product_to_collections", new_callable=AsyncMock) as mock_add_col:

            await _background_fetch_and_push(
                amazon_url="https://www.amazon.com/dp/B0H2G36YMB",
                shop_domain="pawz-store.myshopify.com",
                store_id=1,
                markup=10.0,
                markup_type="percent",
                extra_percent=0.0,
                collection_ids=["gid://shopify/Collection/1"],
            )

        # Verify exactly 1 Shopify product was created with 18 variants
        self.assertEqual(len(created_shopify_payload["variants"]), 18)

        # Verify child ASINs are preserved in payload
        created_asins = [v["asin"] for v in created_shopify_payload["variants"]]
        self.assertEqual(len(created_asins), 18)
        self.assertIn("B0H2G36YMB", created_asins)
        self.assertIn("B0H2FXT24P", created_asins)  # Even the one that failed fetch was preserved!

        # Verify price calculation was preserved (base price was $39.99, markup=10%, tax=5% -> 39.99 * 1.10 * 1.05 = 46.19)
        base_variant = next(v for v in created_shopify_payload["variants"] if v["asin"] == "B0H2G36YMB")
        self.assertAlmostEqual(base_variant["price"], 46.19, places=2)

        # Verify collection add called once for the created product
        mock_add_col.assert_called_once_with(
            shop="pawz-store.myshopify.com",
            access_token="shpat_valid",
            product_id="gid://shopify/Product/12345678",
            collection_ids=["gid://shopify/Collection/1"],
        )

    def test_05_shopify_option_and_variant_limits(self):
        """Verify Shopify 3-option limit and 100-variant limit enforcement."""
        product_data = {
            "title": "Complex Product",
            "price": "10.00",
            "variant_attributes": [
                {"name": "Size", "value": "S"},
                {"name": "Color", "value": "Red"},
                {"name": "Material", "value": "Cotton"},
                {"name": "Pattern", "value": "Striped"},  # 4th option should be ignored
            ],
        }

        # 105 variants
        many_variants = []
        for i in range(105):
            many_variants.append({
                "asin": f"ASIN{i:04d}",
                "title": f"Var {i}",
                "price": 10.0,
                "options": [
                    {"name": "Size", "value": f"S{i}"},
                    {"name": "Color", "value": "Red"},
                    {"name": "Material", "value": "Cotton"},
                    {"name": "Pattern", "value": "Striped"},
                ],
            })

        captured = {}
        async def mock_graphql(shop, token, query, variables):
            captured["vars"] = variables
            return {
                "data": {
                    "productSet": {
                        "product": {"id": "gid://shopify/Product/1", "variants": {"edges": []}},
                        "userErrors": [],
                    }
                }
            }

        with patch("app.services.shopify.product_core.shopify_graphql", side_effect=mock_graphql), \
             patch("app.services.shopify.product_core._get_compare_at_settings_from_store", return_value=(False, "none", 0.0)):

            import asyncio
            asyncio.run(create_shopify_product_with_variants(
                shop="test.myshopify.com",
                access_token="tok",
                product_data=product_data,
                variants=many_variants,
            ))

        inp = captured["vars"]["input"]
        # Exactly 3 options maximum allowed by Shopify
        self.assertEqual(len(inp["productOptions"]), 3)
        self.assertEqual([o["name"] for o in inp["productOptions"]], ["Size", "Color", "Material"])

        # Exactly 100 variants maximum allowed by Shopify
        self.assertEqual(len(inp["variants"]), 100)


if __name__ == "__main__":
    unittest.main()
