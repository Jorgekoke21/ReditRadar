"""Symmetric encryption for Reddit OAuth tokens at rest (spec section 19:
'No guardar secretos OAuth en texto plano'). Uses Fernet (AES-128-CBC + HMAC).
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import Settings


def _fernet(settings: Settings) -> Fernet:
    key_material = settings.reddit_token_encryption_key or "dev-only-insecure-key-change-me"
    # Derive a valid 32-byte urlsafe-base64 Fernet key from arbitrary input so
    # operators can set any secret string in REDDIT_TOKEN_ENCRYPTION_KEY.
    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(settings: Settings, plaintext: str) -> str:
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(settings: Settings, ciphertext: str) -> str:
    return _fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
