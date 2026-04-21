"""Unit test: make_dummy_hash() timing invariant (MEDIUM-12).

Verifies that verifying against the dummy hash runs an equivalent argon2
operation — not a short-circuit — so the login path cannot be used to
enumerate registered emails via response timing.
"""

import time

from app.auth.password import hash_password, make_dummy_hash, verify_password

_TRIALS = 3
_RATIO_THRESHOLD = 10.0  # dummy must not be >10x faster than real hash verify


def test_dummy_hash_is_not_trivially_fast() -> None:
    """make_dummy_hash() must take similar time to verify as a real hash."""
    real_hash = hash_password("some-password-for-timing")

    dummy_times = []
    real_times = []

    for _ in range(_TRIALS):
        t0 = time.perf_counter()
        verify_password("wrong-password", make_dummy_hash())
        dummy_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        verify_password("wrong-password", real_hash)
        real_times.append(time.perf_counter() - t0)

    avg_dummy = sum(dummy_times) / _TRIALS
    avg_real = sum(real_times) / _TRIALS

    # Dummy must not be more than 10x faster than real — if it is, it means
    # the dummy hash is not running a real argon2 verify.
    assert avg_real / avg_dummy < _RATIO_THRESHOLD, (
        f"Dummy verify ({avg_dummy:.4f}s) is suspiciously faster than real "
        f"verify ({avg_real:.4f}s) by ratio {avg_real / avg_dummy:.1f}x"
    )
