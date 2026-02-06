from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
import secrets
import string
from typing import Tuple
from config import settings


class PasswordHasher:
    """Argon2 password hasher with OWASP-recommended parameters"""

    def __init__(self):
        self.ph = Argon2PasswordHasher(
            time_cost=settings.ARGON2_TIME_COST,
            memory_cost=settings.ARGON2_MEMORY_COST,
            parallelism=settings.ARGON2_PARALLELISM,
            hash_len=settings.ARGON2_HASH_LENGTH,
            salt_len=settings.ARGON2_SALT_LENGTH,
        )

    def hash_password(self, password: str) -> str:
        return self.ph.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            self.ph.verify(password_hash, password)
            return True
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self.ph.check_needs_rehash(password_hash)
        except (VerificationError, InvalidHash):
            return True

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_secure_password(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits + string.punctuation
        while True:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
            # Ensure password meets requirements
            if (any(c.islower() for c in password) and
                any(c.isupper() for c in password) and
                any(c.isdigit() for c in password) and
                any(c in string.punctuation for c in password)):
                return password


# Global password hasher instance
pwd_hasher = PasswordHasher()

