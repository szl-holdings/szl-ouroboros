"""Test-only recognizer for the finite GBNF subset this repo emits.

CI and the local pytest gate do not install llama-cpp-python, so unit tests
cannot call LlamaGrammar. This helper interprets the hand-written compact
review grammar and reports whether a string is in a named rule's language.
It is not an admission validator and is not used at review time.
"""
from __future__ import annotations

import re
from typing import Callable


class GbnfError(ValueError):
    """The grammar text is not in the supported GBNF subset."""


def gbnf_matches(grammar_text: str, rule: str, text: str) -> bool:
    """Return True iff `text` is a complete match of `rule` in `grammar_text`."""
    return _Grammar(grammar_text).matches(rule, text)


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_NUMBER = re.compile(r"\d+")


class _Grammar:
    def __init__(self, grammar_text: str) -> None:
        self.rules = _parse_rules(grammar_text)
        self._memo: dict[tuple[int, int], frozenset[int]] = {}

    def matches(self, rule: str, text: str) -> bool:
        if rule not in self.rules:
            raise GbnfError(f"unknown rule {rule!r}")
        self._memo.clear()
        return len(text) in self._ends(self.rules[rule], text, 0)

    def _ends(self, expr: tuple, text: str, pos: int) -> frozenset[int]:
        key = (id(expr), pos)
        if key in self._memo:
            return self._memo[key]
        kind = expr[0]
        if kind == "lit":
            literal = expr[1]
            result = (
                frozenset([pos + len(literal)])
                if text.startswith(literal, pos)
                else frozenset()
            )
        elif kind == "class":
            predicate: Callable[[str], bool] = expr[1]
            result = (
                frozenset([pos + 1])
                if pos < len(text) and predicate(text[pos])
                else frozenset()
            )
        elif kind == "ref":
            name = expr[1]
            if name not in self.rules:
                raise GbnfError(f"unknown rule {name!r}")
            result = self._ends(self.rules[name], text, pos)
        elif kind == "seq":
            current = frozenset([pos])
            for part in expr[1]:
                nxt: set[int] = set()
                for cur in current:
                    nxt.update(self._ends(part, text, cur))
                current = frozenset(nxt)
                if not current:
                    break
            result = current
        elif kind == "alt":
            nxt = set()
            for part in expr[1]:
                nxt.update(self._ends(part, text, pos))
            result = frozenset(nxt)
        elif kind == "rep":
            _, inner, minimum, maximum = expr
            current = frozenset([pos])
            found: set[int] = set()
            for count in range(maximum + 1):
                if count >= minimum:
                    found.update(current)
                if count == maximum or not current:
                    break
                nxt = set()
                for cur in current:
                    for end in self._ends(inner, text, cur):
                        if end != cur:
                            nxt.add(end)
                current = frozenset(nxt)
            result = frozenset(found)
        else:
            raise GbnfError(f"unsupported expression {kind!r}")
        self._memo[key] = result
        return result


def _parse_rules(grammar_text: str) -> dict[str, tuple]:
    rules: dict[str, tuple] = {}
    for raw in grammar_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "::=" not in line:
            raise GbnfError(f"unrecognized GBNF line: {raw!r}")
        name, rhs = line.split("::=", 1)
        name = name.strip()
        if not _IDENT.fullmatch(name):
            raise GbnfError(f"invalid rule name {name!r}")
        if name in rules:
            raise GbnfError(f"duplicate rule {name!r}")
        tokens = _tokenize(rhs)
        expr, index = _parse_alt(tokens, 0)
        if index != len(tokens):
            raise GbnfError(f"trailing tokens in {name!r}")
        rules[name] = expr
    if not rules:
        raise GbnfError("grammar has no rules")
    return rules


def _tokenize(rhs: str) -> list[tuple]:
    tokens: list[tuple] = []
    i = 0
    length = len(rhs)
    while i < length:
        char = rhs[i]
        if char.isspace():
            i += 1
            continue
        if char == '"':
            value, i = _read_string(rhs, i + 1)
            tokens.append(("str", value))
            continue
        if char == "[":
            predicate, i = _read_class(rhs, i + 1)
            tokens.append(("class", predicate))
            continue
        if char in "()|,{}*?+":
            tokens.append((char,))
            i += 1
            continue
        ident = _IDENT.match(rhs, i)
        if ident:
            tokens.append(("id", ident.group()))
            i = ident.end()
            continue
        number = _NUMBER.match(rhs, i)
        if number:
            tokens.append(("num", int(number.group())))
            i = number.end()
            continue
        raise GbnfError(f"unexpected GBNF token at {rhs[i:]!r}")
    return tokens


def _read_string(source: str, start: int) -> tuple[str, int]:
    chars: list[str] = []
    i = start
    while i < len(source):
        char = source[i]
        if char == '"':
            return "".join(chars), i + 1
        if char == "\\":
            escaped, i = _read_escape(source, i + 1)
            chars.append(escaped)
            continue
        chars.append(char)
        i += 1
    raise GbnfError("unterminated GBNF string")


def _read_class(source: str, start: int) -> tuple[Callable[[str], bool], int]:
    i = start
    negated = False
    if i < len(source) and source[i] == "^":
        negated = True
        i += 1
    items: list[tuple[str, str]] = []
    while i < len(source):
        char = source[i]
        if char == "]" and items:
            i += 1
            allowed = [(ord(lo), ord(hi)) for lo, hi in items]

            def predicate(candidate: str, *, _allowed=allowed, _neg=negated) -> bool:
                if len(candidate) != 1:
                    return False
                code = ord(candidate)
                inside = any(lo <= code <= hi for lo, hi in _allowed)
                return (not inside) if _neg else inside

            return predicate, i
        if char == "\\":
            atom, i = _read_escape(source, i + 1)
        else:
            atom, i = char, i + 1
        if i + 1 < len(source) and source[i] == "-" and source[i + 1] != "]":
            i += 1
            if source[i] == "\\":
                high, i = _read_escape(source, i + 1)
            else:
                high, i = source[i], i + 1
            items.append((atom, high))
        else:
            items.append((atom, atom))
    raise GbnfError("unterminated GBNF character class")


def _read_escape(source: str, start: int) -> tuple[str, int]:
    if start >= len(source):
        raise GbnfError("truncated GBNF escape")
    char = source[start]
    if char == "x" and start + 2 < len(source):
        return chr(int(source[start + 1 : start + 3], 16)), start + 3
    if char == "u" and start + 4 < len(source):
        return chr(int(source[start + 1 : start + 5], 16)), start + 5
    escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "]": "]", "-": "-"}
    if char in escapes:
        return escapes[char], start + 1
    return char, start + 1


def _parse_alt(tokens: list[tuple], index: int) -> tuple[tuple, int]:
    options = []
    expr, index = _parse_seq(tokens, index)
    options.append(expr)
    while index < len(tokens) and tokens[index][0] == "|":
        expr, index = _parse_seq(tokens, index + 1)
        options.append(expr)
    if len(options) == 1:
        return options[0], index
    return ("alt", tuple(options)), index


def _parse_seq(tokens: list[tuple], index: int) -> tuple[tuple, int]:
    parts = []
    while index < len(tokens) and tokens[index][0] not in {"|", ")"}:
        expr, index = _parse_repeat(tokens, index)
        parts.append(expr)
    if not parts:
        raise GbnfError("empty GBNF sequence")
    if len(parts) == 1:
        return parts[0], index
    return ("seq", tuple(parts)), index


def _parse_repeat(tokens: list[tuple], index: int) -> tuple[tuple, int]:
    atom, index = _parse_atom(tokens, index)
    if index >= len(tokens):
        return atom, index
    mark = tokens[index][0]
    if mark == "*":
        return ("rep", atom, 0, 10**9), index + 1
    if mark == "+":
        return ("rep", atom, 1, 10**9), index + 1
    if mark == "?":
        return ("rep", atom, 0, 1), index + 1
    if mark == "{":
        index += 1
        if index >= len(tokens) or tokens[index][0] != "num":
            raise GbnfError("GBNF repetition requires a number")
        minimum = tokens[index][1]
        index += 1
        maximum = minimum
        if index < len(tokens) and tokens[index][0] == ",":
            index += 1
            if index < len(tokens) and tokens[index][0] == "num":
                maximum = tokens[index][1]
                index += 1
            else:
                maximum = 10**9
        if index >= len(tokens) or tokens[index][0] != "}":
            raise GbnfError("unterminated GBNF repetition")
        if maximum < minimum:
            raise GbnfError("GBNF repetition maximum is below minimum")
        return ("rep", atom, minimum, maximum), index + 1
    return atom, index


def _parse_atom(tokens: list[tuple], index: int) -> tuple[tuple, int]:
    if index >= len(tokens):
        raise GbnfError("unexpected end of GBNF expression")
    token = tokens[index]
    kind = token[0]
    if kind == "str":
        return ("lit", token[1]), index + 1
    if kind == "class":
        return ("class", token[1]), index + 1
    if kind == "id":
        return ("ref", token[1]), index + 1
    if kind == "(":
        expr, index = _parse_alt(tokens, index + 1)
        if index >= len(tokens) or tokens[index][0] != ")":
            raise GbnfError("unterminated GBNF group")
        return expr, index + 1
    raise GbnfError(f"unexpected GBNF token {token!r}")
