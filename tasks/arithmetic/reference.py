import re


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        match = re.match(r"[0-9]+(?:\.[0-9]+)?|[+*/()-]", text[pos:])
        if not match:
            raise ValueError("invalid token")
        tokens.append(match.group())
        pos += len(match.group())
    return tokens


def evaluate(text: str) -> float:
    tokens = tokenize(text)
    pos = 0

    def factor() -> float:
        nonlocal pos
        if pos == len(tokens):
            raise ValueError("missing operand")
        token = tokens[pos]
        pos += 1
        if token in ("+", "-"):
            value = factor()
            return -value if token == "-" else value
        if token == "(":
            value = expression()
            if pos == len(tokens) or tokens[pos] != ")":
                raise ValueError("missing close")
            pos += 1
            return value
        if token in (")", "*", "/"):
            raise ValueError("unexpected token")
        return float(token)

    def term() -> float:
        nonlocal pos
        value = factor()
        while pos < len(tokens) and tokens[pos] in ("*", "/"):
            op = tokens[pos]
            pos += 1
            other = factor()
            value = value * other if op == "*" else value / other
        return value

    def expression() -> float:
        nonlocal pos
        value = term()
        while pos < len(tokens) and tokens[pos] in ("+", "-"):
            op = tokens[pos]
            pos += 1
            other = term()
            value = value + other if op == "+" else value - other
        return value

    value = expression()
    if pos != len(tokens):
        raise ValueError("trailing tokens")
    return value
