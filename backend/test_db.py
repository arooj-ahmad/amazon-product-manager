# ============================================
# test_models.py
# Verify karein ke models sahi load ho rahe hain
# ============================================

from app.models import Admin, Product


def test_models():
    print("✅ Models imported successfully!")
    print(f"   - Product table: {Product.__tablename__}")
    print(f"   - Admin table:   {Admin.__tablename__}")

    # Columns check
    print("\n📋 Product columns:")
    for col in Product.__table__.columns:
        print(f"   - {col.name} ({col.type})")

    print("\n📋 Admin columns:")
    for col in Admin.__table__.columns:
        print(f"   - {col.name} ({col.type})")

    print("\n🎉 Sab kuch perfect chal raha hai!")


if __name__ == "__main__":
    test_models()