# ============================================
# test_auth.py
# Auth service test
# ============================================

from app.services.auth import (
    create_access_token,
    decode_access_token,
    get_username_from_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    print("=" * 60)
    print("TEST 1: Password Hashing")
    print("=" * 60)

    password = "admin123"
    hashed = hash_password(password)

    print(f"Plain:    {password}")
    print(f"Hashed:   {hashed[:50]}...")
    print(f"Length:   {len(hashed)}")

    assert verify_password(password, hashed) is True
    print("Correct password: verified")

    assert verify_password("wrongpass", hashed) is False
    print("Wrong password: rejected")


def test_jwt_tokens():
    print("\n" + "=" * 60)
    print("TEST 2: JWT Tokens")
    print("=" * 60)

    token = create_access_token(data={"sub": "admin"})
    print(f"Token: {token[:60]}...")

    payload = decode_access_token(token)
    print(f"Payload: {payload}")

    assert payload is not None
    assert payload["sub"] == "admin"
    print("Token valid aur decode hua")

    username = get_username_from_token(token)
    assert username == "admin"
    print(f"Username from token: {username}")

    invalid_username = get_username_from_token("invalid.token.here")
    assert invalid_username is None
    print("Invalid token correctly rejected")


def test_existing_hash():
    """Verify karein ke Supabase wala hash admin123 se match karta hai"""
    print("\n" + "=" * 60)
    print("TEST 3: Supabase Hash Verify")
    print("=" * 60)

    supabase_hash = "$2b$12$R/aO2KzSdnmWbgE5YRX9QehoLgGS5mjzjizT5hqSdfBnKxxEluzXy"

    assert verify_password("admin123", supabase_hash) is True
    print("Supabase hash + admin123: match")

    assert verify_password("wrongpass", supabase_hash) is False
    print("Supabase hash + wrongpass: rejected")


if __name__ == "__main__":
    test_password_hashing()
    test_jwt_tokens()
    test_existing_hash()
    print("\nSab kuch perfect chal raha hai!")