from copy import deepcopy

import pytest
from solution import get_path


def test_paths_and_no_mutation() -> None:
    data = {"users": [{"name": "first"}, {"name": None}], "_x2": [[{"y": 3}]]}
    before = deepcopy(data)
    assert get_path(data, "users[0].name") == "first"
    assert get_path(data, "$.users[01].name", "missing") is None
    assert get_path(data, "_x2[0][0].y") == 3
    assert get_path(data, "") is data
    assert get_path(data, "$") is data
    assert data == before
    assert get_path([["ok"]], "$[0][0]") == "ok"
    assert get_path([{"x": 3}], "[0].x") == 3


@pytest.mark.parametrize(
    "path", ["missing.a", "users[9].name", "users.name", "users[0].name[0]", "users[0][0]"]
)
def test_default(path: str) -> None:
    marker = object()
    assert get_path({"users": [{"name": "text"}]}, path, marker) is marker


@pytest.mark.parametrize(
    "path",
    [
        ".",
        "$.",
        "$name",
        "a.",
        "a..b",
        "a[-1]",
        "a[1.0]",
        "a[]",
        "a[*]",
        "a[0]b",
        "a[0].",
        'a["x"]',
        " a",
        "a [0]",
        "$.a.[0]",
        "$.[0]",
        "missing..x",
        "é",
        "[0]x",
    ],
)
def test_invalid_even_if_missing(path: str) -> None:
    with pytest.raises(ValueError):
        get_path({}, path)


def test_dict_numeric_key_is_not_list_index() -> None:
    marker = object()
    assert get_path({0: "zero"}, "[0]", marker) is marker
