from app.models import Admin, Product


def test_models():
    print("Models imported successfully!")
    print(f"Product table: {Product.__tablename__}")
    print(f"Admin table:   {Admin.__tablename__}")

    print("\nProduct columns:")
    for col in Product.__table__.columns:
        print(f"  - {col.name} ({col.type})")

    print("\nAdmin columns:")
    for col in Admin.__table__.columns:
        print(f"  - {col.name} ({col.type})")

    print("\nSab kuch perfect chal raha hai!")


if __name__ == "__main__":
    test_models()