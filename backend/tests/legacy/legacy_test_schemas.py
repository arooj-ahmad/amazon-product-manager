# ============================================
# test_schemas.py
# Verify karein ke schemas sahi load ho rahe hain
# ============================================

from datetime import datetime

from app.schemas import (
    AdminLogin,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    Token,
)


def test_schemas():
    print("Schemas imported successfully!")

    # 1. ProductCreate test
    print("\n1. ProductCreate test:")
    create = ProductCreate(amazon_url="https://amazon.com/dp/B0B2RM68G2")
    print(f"   URL: {create.amazon_url}")

    # 2. ProductUpdate test
    print("\n2. ProductUpdate test:")
    update = ProductUpdate(title="New Title", price=99.99)
    print(f"   Title: {update.title}, Price: {update.price}")
    print(f"   Brand (not provided): {update.brand}")

    # 3. ProductResponse test (SQLAlchemy-style object)
    print("\n3. ProductResponse test:")
    response = ProductResponse(
        id=1,
        asin="B0B2RM68G2",
        parent_asin=None,
        is_variation=False,
        title="Test Product",
        brand="Test Brand",
        description="Test description",
        image_url="https://example.com/image.jpg",
        amazon_price=99.99,
        price=101.99,
        markup=2.0,
        is_manual_override=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    print(f"   ID: {response.id}")
    print(f"   Title: {response.title}")
    print(f"   Price: {response.price}")

    # 4. AdminLogin test
    print("\n4. AdminLogin test:")
    login = AdminLogin(username="admin", password="admin123")
    print(f"   Username: {login.username}")

    # 5. Token test
    print("\n5. Token test:")
    token = Token(access_token="dummy.jwt.token")
    print(f"   Token type: {token.token_type}")

    # 6. Validation test (should fail)
    print("\n6. Validation test (expecting error):")
    try:
        ProductUpdate(price=-5)  # Negative price not allowed
        print("   ERROR: Should have failed!")
    except Exception as e:
        print(f"   Correctly rejected: {type(e).__name__}")

    print("\nSab kuch perfect chal raha hai!")


if __name__ == "__main__":
    test_schemas()