from collections.abc import Iterable, Sequence


def merge_intervals(intervals: Iterable[Sequence[int]]) -> list[tuple[int, int]]:
    ordered = []
    for pair in intervals:
        if len(pair) != 2:
            raise ValueError("expected two endpoints")
        a, b = pair
        if type(a) is not int or type(b) is not int or a > b:
            raise ValueError("invalid endpoints")
        ordered.append((a, b))
    ordered.sort()
    merged: list[tuple[int, int]] = []
    for a, b in ordered:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged
