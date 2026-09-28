from collections import OrderedDict
from collections.abc import Callable, Hashable
from math import isfinite
from time import monotonic
from typing import Any


class LRUCache:
    def __init__(self, capacity: int, ttl: float, clock: Callable[[], float] = monotonic) -> None:
        if type(capacity) is not int or capacity <= 0 or not isfinite(ttl) or ttl <= 0:
            raise ValueError("invalid capacity or ttl")
        self.capacity = capacity
        self.ttl = ttl
        self.clock = clock
        self.items: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    def _purge(self, now: float) -> None:
        for key in list(self.items):
            if self.items[key][1] <= now:
                del self.items[key]

    def put(self, key: Hashable, value: Any) -> None:
        now = self.clock()
        self._purge(now)
        self.items[key] = (value, now + self.ttl)
        self.items.move_to_end(key)
        if len(self.items) > self.capacity:
            self.items.popitem(last=False)

    def get(self, key: Hashable, default: Any = None) -> Any:
        self._purge(self.clock())
        if key not in self.items:
            return default
        self.items.move_to_end(key)
        return self.items[key][0]

    def __len__(self) -> int:
        self._purge(self.clock())
        return len(self.items)
