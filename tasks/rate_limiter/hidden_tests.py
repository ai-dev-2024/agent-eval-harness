import pytest
from solution import SlidingWindowLimiter


@pytest.mark.parametrize(
    "limit,window",
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, float("inf")), (1, float("nan"))],
)
def test_invalid(limit: int, window: float) -> None:
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit, window)


def test_boundary_and_denials() -> None:
    limiter = SlidingWindowLimiter(2, 10)
    assert limiter.allow("a", 0)
    assert limiter.allow("a", 1)
    assert not limiter.allow("a", 9)
    assert limiter.allow("a", 10)
    assert not limiter.allow("a", 10)
    assert limiter.allow("a", 11)


def test_keys_and_equal_times() -> None:
    limiter = SlidingWindowLimiter(2, 1)
    assert limiter.allow("a", 10)
    assert limiter.allow("a", 10)
    assert not limiter.allow("a", 10)
    assert limiter.allow(("b", 1), -10)
    assert limiter.allow("a", 11)


def test_denied_time_counts_and_invalid_does_not_mutate() -> None:
    limiter = SlidingWindowLimiter(1, 10)
    assert limiter.allow("a", 0)
    assert not limiter.allow("a", 5)
    with pytest.raises(ValueError):
        limiter.allow("a", 4)
    for bad in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValueError):
            limiter.allow("a", bad)
    assert limiter.allow("a", 10)


def test_long_stream_against_simple_history() -> None:
    limiter = SlidingWindowLimiter(3, 4)
    accepted: list[float] = []
    for i in range(100):
        now = i / 3
        expected = sum(t > now - 4 for t in accepted) < 3
        assert limiter.allow("x", now) == expected
        if expected:
            accepted.append(now)
