from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# OWASP-recommended parameters: time_cost≥3, memory_cost≥64MB
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)


def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
