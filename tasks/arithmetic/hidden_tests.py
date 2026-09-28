import pytest
from solution import evaluate, tokenize


def test_tokens() -> None:
    assert tokenize(" 001 + 2.50*(3 - -4)\n") == [
        "001",
        "+",
        "2.50",
        "*",
        "(",
        "3",
        "-",
        "-",
        "4",
        ")",
    ]
    assert tokenize("  ") == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1+2*3", 7),
        ("(1+2)*3", 9),
        ("8/4/2", 1),
        ("8-4-2", 2),
        ("--2 + -(3)", -1),
        ("2*-3 + +4", -2),
        ("10 / (2 + 3)", 2),
        ("0.25+0.5", 0.75),
        ("-(-(-2))", -2),
    ],
)
def test_evaluation(text: str, expected: float) -> None:
    assert evaluate(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text", ["", " ", "1 2", "()", "(1", "1)", "2(3)", "1+", "*2", "1//2", "1**2", "1+(2*)"]
)
def test_syntax(text: str) -> None:
    with pytest.raises(ValueError):
        evaluate(text)


@pytest.mark.parametrize("text", [".1", "1.", "1.2.3", "x", "1e2", "1_0", "[1]", "２"])
def test_bad_tokens(text: str) -> None:
    with pytest.raises(ValueError):
        tokenize(text)


def test_zero() -> None:
    with pytest.raises(ZeroDivisionError):
        evaluate("1/(3-3)")
