"""AES-256-GCM pre TG session a bot tokeny.

Kľúč žije len v env (ENCRYPTION_KEY, base64 32 bajtov) — únik databázy sám
o sebe session nevydá. Formát tokenu: base64(nonce):base64(ciphertext):base64(tag).
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(RuntimeError):
    pass


def _key_bytes(key_b64: str) -> bytes:
    try:
        raw = base64.b64decode(key_b64, validate=True)
    except Exception as exc:
        raise CryptoError("ENCRYPTION_KEY nie je platný base64") from exc
    if len(raw) != 32:
        raise CryptoError("ENCRYPTION_KEY musí byť 32 bajtov (AES-256)")
    return raw


def encrypt(plaintext: str, key_b64: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key_bytes(key_b64)).encrypt(nonce, plaintext.encode(), None)
    ct, tag = sealed[:-16], sealed[-16:]
    b64 = lambda b: base64.b64encode(b).decode()
    return f"{b64(nonce)}:{b64(ct)}:{b64(tag)}"


def decrypt(token: str, key_b64: str) -> str:
    try:
        n_b64, ct_b64, tag_b64 = token.split(":")
        nonce, ct, tag = (base64.b64decode(x) for x in (n_b64, ct_b64, tag_b64))
    except Exception as exc:
        raise CryptoError("Poškodený šifrovaný token") from exc
    try:
        return AESGCM(_key_bytes(key_b64)).decrypt(nonce, ct + tag, None).decode()
    except InvalidTag as exc:
        raise CryptoError("Dešifrovanie zlyhalo — zlý kľúč alebo poškodené dáta") from exc
