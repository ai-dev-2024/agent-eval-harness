from collections import deque
from collections.abc import Hashable
from math import isfinite


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        if type(limit) is not int or limit <= 0 or not isfinite(window_s) or window_s <= 0:
            raise ValueError("invalid limit or window")
        self.limit = limit
        self.window = window_s
        self.history: dict[Hashable, deque[float]] = {}
        self.last: dict[Hashable, float] = {}

    def allow(self, key: Hashable, now: float) -> bool:
        if not isfinite(now) or (key in self.last and now < self.last[key]):
            raise ValueError("invalid time")
        self.last[key] = now
        queue = self.history.setdefault(key, deque())
        while queue and queue[0] <= now - self.window:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        return True
