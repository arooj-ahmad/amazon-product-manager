# ============================================
# backend/migrate_extra_percent.py
# Database migration — extra_percent column add karo
# Ek baar chalao, phir delete kar sakte hain
# ============================================

import sys
import os

# Project root ko path mein add karo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text, inspect
from app.database import engine


def migrate():
    """extra_percent column add karo products table mein."""

    print("=" * 60)
    print("🔧 Migration: Add extra_percent to products")
    print("=" * 60)

    # 1. Check karo column already exists?
    inspector = inspect(engine)
    existing_columns = [col['name'] for col in inspector.get_columns('products')]

    print(f"\n📋 Current products columns ({len(existing_columns)}):")
    for col in existing_columns:
        print(f"   - {col}")

    if 'extra_percent' in existing_columns:
        print("\n✅ extra_percent column ALREADY EXISTS — skipping migration")
        return True

    # 2. Column add karo
    print("\n➕ Adding extra_percent column...")

    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE products "
                "ADD COLUMN extra_percent FLOAT DEFAULT 0.0 NOT NULL"
            ))
        print("✅ Column added successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # 3. Verify karo
    print("\n🔍 Verifying...")
    inspector = inspect(engine)
    new_columns = [col['name'] for col in inspector.get_columns('products')]

    if 'extra_percent' in new_columns:
        print("✅ VERIFIED: extra_percent column exists!")
        print(f"\n📋 Total columns now: {len(new_columns)}")

        # Column details
        for col in inspector.get_columns('products'):
            if col['name'] == 'extra_percent':
                print(f"\n📌 extra_percent column details:")
                print(f"   - Type:     {col['type']}")
                print(f"   - Nullable: {col['nullable']}")
                print(f"   - Default:  {col['default']}")

        print("\n" + "=" * 60)
        print("🎉 Migration complete!")
        print("=" * 60)
        return True
    else:
        print("❌ VERIFICATION FAILED")
        return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)