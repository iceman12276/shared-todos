from app.auth.password import hash_password, verify_password


def test_hash_password_returns_string() -> None:
    result = hash_password("correcthorsebatterystaple")
    assert isinstance(result, str)
    assert len(result) > 0


def test_hash_is_not_plaintext() -> None:
    pw = "correcthorsebatterystaple"
    result = hash_password(pw)
    assert pw not in result


def test_verify_password_correct() -> None:
    pw = "correcthorsebatterystaple"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True


def test_verify_password_wrong() -> None:
    hashed = hash_password("correcthorsebatterystaple")
    assert verify_password("wrongpassword", hashed) is False


def test_two_hashes_of_same_password_differ() -> None:
    pw = "correcthorsebatterystaple"
    assert hash_password(pw) != hash_password(pw)
