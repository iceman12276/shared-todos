
from app.auth.tokens import generate_reset_token, hash_token, verify_token_hash


def test_generate_reset_token_length() -> None:
    token = generate_reset_token()
    # secrets.token_urlsafe(32) produces 43 url-safe base64 chars
    assert len(token) >= 43


def test_two_tokens_differ() -> None:
    assert generate_reset_token() != generate_reset_token()


def test_hash_token_not_plaintext() -> None:
    token = generate_reset_token()
    hashed = hash_token(token)
    assert token not in hashed
    assert len(hashed) > 0


def test_verify_token_hash_correct() -> None:
    token = generate_reset_token()
    hashed = hash_token(token)
    assert verify_token_hash(token, hashed) is True


def test_verify_token_hash_wrong() -> None:
    token = generate_reset_token()
    hashed = hash_token(token)
    assert verify_token_hash("tampered" + token, hashed) is False


def test_two_different_tokens_produce_different_hashes() -> None:
    token_a = generate_reset_token()
    token_b = generate_reset_token()
    assert hash_token(token_a) != hash_token(token_b)
