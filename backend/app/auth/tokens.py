import hashlib
import hmac
import secrets


def generate_reset_token() -> str:
    """Generate a cryptographically random URL-safe token with ≥32 bytes entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Store a SHA-256 hash of the token — never the raw token."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, stored_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(hash_token(token), stored_hash)
