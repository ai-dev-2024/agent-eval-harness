PAIRS = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]


def to_roman(value: int) -> str:
    if type(value) is not int or not 1 <= value <= 3999:
        raise ValueError("out of range")
    result = ""
    for number, symbol in PAIRS:
        count, value = divmod(value, number)
        result += symbol * count
    return result


def from_roman(text: str) -> int:
    if not isinstance(text, str) or not text:
        raise ValueError("expected Roman numeral")
    rest = text
    value = 0
    for number, symbol in PAIRS:
        while rest.startswith(symbol):
            value += number
            rest = rest[len(symbol) :]
    if rest or not 1 <= value <= 3999 or to_roman(value) != text:
        raise ValueError("not canonical")
    return value
