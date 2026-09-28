import pytest
from solution import from_roman, to_roman


@pytest.mark.parametrize(
    "value,text",
    [
        (1, "I"),
        (4, "IV"),
        (9, "IX"),
        (40, "XL"),
        (90, "XC"),
        (400, "CD"),
        (900, "CM"),
        (1984, "MCMLXXXIV"),
        (3999, "MMMCMXCIX"),
    ],
)
def test_known(value: int, text: str) -> None:
    assert to_roman(value) == text
    assert from_roman(text) == value


def test_exhaustive_round_trip() -> None:
    seen: set[str] = set()
    for value in range(1, 4000):
        text = to_roman(value)
        assert text not in seen
        seen.add(text)
        assert from_roman(text) == value


@pytest.mark.parametrize("value", [0, -1, 4000, True, 1.0, "1", None])
def test_invalid_number(value: object) -> None:
    with pytest.raises(ValueError):
        to_roman(value)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "IIII",
        "VV",
        "IL",
        "IC",
        "VX",
        "IIV",
        "IXIX",
        "MCMC",
        "MMMM",
        "iv",
        " IX",
        "IX ",
        "ABC",
        None,
        10,
    ],
)
def test_invalid_text(text: object) -> None:
    with pytest.raises(ValueError):
        from_roman(text)
