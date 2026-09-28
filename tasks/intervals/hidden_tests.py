from copy import deepcopy

import pytest
from solution import merge_intervals


@pytest.mark.parametrize(
    "values,expected",
    [
        ([], []),
        ([(1, 1)], [(1, 1)]),
        ([(5, 7), (1, 3), (3, 5)], [(1, 7)]),
        ([(1, 8), (2, 3), (1, 8)], [(1, 8)]),
        ([(-9, -4), (-4, 0), (2, 2)], [(-9, 0), (2, 2)]),
        ([(0, 1), (2, 3)], [(0, 1), (2, 3)]),
    ],
)
def test_cases(values: list[tuple[int, int]], expected: list[tuple[int, int]]) -> None:
    assert merge_intervals(values) == expected


def test_no_mutation_and_generator() -> None:
    source = [[4, 8], [0, 5], [10, 11]]
    old = deepcopy(source)
    assert merge_intervals(iter(source)) == [(0, 8), (10, 11)]
    assert source == old


@pytest.mark.parametrize("value", [[(2, 1)], [(1,)], [(1, 2, 3)], [(True, 2)], [(1, 2.0)]])
def test_invalid(value: object) -> None:
    with pytest.raises(ValueError):
        merge_intervals(value)


def test_coverage_property() -> None:
    import random

    rng = random.Random(12)
    for _ in range(40):
        pairs = [tuple(sorted((rng.randrange(-20, 20), rng.randrange(-20, 20)))) for _ in range(10)]
        result = merge_intervals(pairs)
        assert all(a <= b for a, b in result)
        assert all(left[1] < right[0] for left, right in zip(result, result[1:], strict=False))
        assert {x for a, b in pairs for x in range(a, b + 1)} == {
            x for a, b in result for x in range(a, b + 1)
        }
