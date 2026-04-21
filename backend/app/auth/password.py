import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# OWASP-recommended parameters: time_cost≥3, memory_cost≥64MB
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)

# Precomputed at module load — used for timing equalization in the login path.
# Calling verify_password(input, _DUMMY_HASH) runs the same argon2 verify()
# operation as a normal wrong-password check, preventing timing side-channels.
_DUMMY_HASH: str = _ph.hash(secrets.token_urlsafe(16))


def make_dummy_hash() -> str:
    """Return the module-level dummy hash for timing-safe user-not-found path."""
    return _DUMMY_HASH


def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
