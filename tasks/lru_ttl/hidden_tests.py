import pytest
from solution import LRUCache


@pytest.mark.parametrize(
    "capacity,ttl",
    [(0, 1), (-1, 1), (True, 1), (1, 0), (1, -1), (1, float("inf")), (1, float("nan"))],
)
def test_invalid(capacity: int, ttl: float) -> None:
    with pytest.raises(ValueError):
        LRUCache(capacity, ttl)


def test_lru_update_none_and_hashable_keys() -> None:
    c = LRUCache(2, 10, lambda: 0)
    c.put(("a", 1), None)
    c.put("b", 2)
    assert c.get(("a", 1), "missing") is None
    c.put("c", 3)
    assert c.get("b", "missing") == "missing"
    c.put(("a", 1), 4)
    assert len(c) == 2
    c.put("d", 5)
    assert c.get("c") is None
    assert c.get(("a", 1)) == 4


def test_expiry_boundary_and_reads_do_not_refresh() -> None:
    now = [0.0]
    c = LRUCache(2, 5, lambda: now[0])
    c.put("a", 1)
    now[0] = 4.999
    assert c.get("a") == 1
    now[0] = 5
    assert c.get("a", "gone") == "gone"
    assert len(c) == 0


def test_update_resets_expiry() -> None:
    now = [0.0]
    c = LRUCache(1, 5, lambda: now[0])
    c.put("a", 1)
    now[0] = 4
    c.put("a", 2)
    now[0] = 5
    assert c.get("a") == 2
    now[0] = 9
    assert len(c) == 0


def test_expired_mru_does_not_evict_live_lru() -> None:
    now = [0.0]
    c = LRUCache(2, 5, lambda: now[0])
    c.put("a", 1)
    now[0] = 2
    c.put("b", 2)
    c.get("a")
    now[0] = 5
    c.put("c", 3)
    assert c.get("b") == 2
    assert len(c) == 2
