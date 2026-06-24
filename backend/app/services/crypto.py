"""
AES-256-GCM encryption for OAuth tokens and sensitive data.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    key_b64 = os.environ.get("ENCRYPTION_KEY", "")
    if not key_b64:
        raise ValueError("ENCRYPTION_KEY env var not set")
    key = base64.urlsafe_b64decode(key_b64 + "==")
    if len(key) != 32:
        raise ValueError("ENCRYPTION_KEY must be 32 bytes (URL-safe base64 of 32 bytes)")
    return key


def encrypt(plaintext: str) -> bytes:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return nonce + ct


def decrypt(ciphertext: bytes) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce, ct = ciphertext[:12], ciphertext[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()
