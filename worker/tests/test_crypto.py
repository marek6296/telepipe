"""Šifrovanie session stringov — roundtrip, zlý kľúč, formát."""
import pytest
from crypto import encrypt, decrypt, CryptoError

KEY = "u" * 43 + "="  # 32 bajtov base64 — testovací

def test_roundtrip():
    token = encrypt("1BVtsOH4Bu...session", KEY)
    assert decrypt(token, KEY) == "1BVtsOH4Bu...session"

def test_token_format_three_parts():
    assert encrypt("x", KEY).count(":") == 2

def test_wrong_key_fails_cleanly():
    token = encrypt("secret", KEY)
    with pytest.raises(CryptoError):
        decrypt(token, "v" * 43 + "=")

def test_tampered_ciphertext_fails():
    token = encrypt("secret", KEY)
    parts = token.split(":")
    parts[1] = parts[1][:-4] + "AAAA"
    with pytest.raises(CryptoError):
        decrypt(":".join(parts), KEY)

def test_empty_plaintext_roundtrip():
    assert decrypt(encrypt("", KEY), KEY) == ""
