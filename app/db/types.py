# Iridium-main/app/db/types.py

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import String, TypeDecorator

from app.core.config import settings

# --- Key Derivation ---
# We derive a stable encryption key from the app's SECRET_KEY.
# This ensures the key is consistent across restarts and is the correct format for Fernet.
SALT = b"iridium_encryption_salt"

kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=SALT,
    iterations=480000,  # Number of iterations recommended by OWASP as of 2023
)
# The key must be url-safe base64-encoded.
key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
fernet = Fernet(key)


class EncryptedString(TypeDecorator):
    """
    A SQLAlchemy TypeDecorator to transparently encrypt and decrypt string values
    when storing and retrieving them from the database.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        """
        Encrypt the value before sending it to the database.
        """
        if value is None:
            return None
        # The value must be encoded to bytes before encryption
        encoded_value = value.encode()
        encrypted_value = fernet.encrypt(encoded_value)
        # The encrypted value is bytes, so we decode it to a string for DB storage
        return encrypted_value.decode("utf-8")

    def process_result_value(self, value: str | None, dialect) -> str | None:
        """
        Decrypt the value after retrieving it from the database.
        """
        if value is None:
            return None
        # The value from the DB is a string, so we encode it back to bytes
        encrypted_value = value.encode("utf-8")
        decrypted_value = fernet.decrypt(encrypted_value)
        # The decrypted value is bytes, so we decode it back to a string
        return decrypted_value.decode("utf-8")
        return decrypted_value.decode('utf-8')
