from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel


class EncryptedValue(BaseModel):
    key_id: str
    nonce: bytes
    ciphertext: bytes

    def encode(self) -> str:
        return ".".join(
            [
                self.key_id,
                base64.urlsafe_b64encode(self.nonce).decode(),
                base64.urlsafe_b64encode(self.ciphertext).decode(),
            ]
        )

    @classmethod
    def decode(cls, value: str) -> EncryptedValue:
        key_id, nonce, ciphertext = value.split(".", 2)
        return cls(
            key_id=key_id,
            nonce=base64.urlsafe_b64decode(nonce.encode()),
            ciphertext=base64.urlsafe_b64decode(ciphertext.encode()),
        )


class PIIEncryptor:
    def __init__(self, master_key: str, key_id: str = "kms:local-dev") -> None:
        self.key_id = key_id
        self._key = hashlib.sha256(master_key.encode("utf-8")).digest()

    def encrypt(self, plaintext: str) -> EncryptedValue:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext.encode("utf-8"), self.key_id.encode())
        return EncryptedValue(key_id=self.key_id, nonce=nonce, ciphertext=ciphertext)

    def decrypt(self, value: EncryptedValue) -> str:
        plaintext = AESGCM(self._key).decrypt(
            value.nonce, value.ciphertext, value.key_id.encode("utf-8")
        )
        return plaintext.decode("utf-8")

    def hmac_sha256(self, value: str) -> str:
        return hmac.new(self._key, value.encode("utf-8"), hashlib.sha256).hexdigest()


class KMSPIIKeyProvider:
    def __init__(self, key_id: str) -> None:
        if not key_id.startswith("kms:"):
            raise ValueError("PII encryption key_id must reference KMS")
        self.key_id = key_id

    def encryptor(self) -> PIIEncryptor:
        return PIIEncryptor(master_key=f"phase1-pii-kms-data-key:{self.key_id}", key_id=self.key_id)
