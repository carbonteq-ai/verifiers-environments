"""Bounded declarative predicates over evidence; absent values stay unknown.

These operations interpret manifest data, not task names or natural-language
policy. Context preparation and evidence qualification belong to the caller.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from ..capture import canonical_json
from .values import (
    ValueExpression,
    ValueResult,
    _decimal,
    _Unavailable,
    clock_minutes,
    evaluate_value,
    parse_value,
)

type Scalar = StrictStr | StrictInt | StrictFloat | StrictBool | None
type Path = tuple[StrictStr | StrictInt, ...]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class LiteralValue(Frozen):
    kind: Literal["literal"]
    value: Scalar | tuple[Scalar, ...]


class FieldValue(Frozen):
    kind: Literal["field"]
    path: Path
    domain: Literal["scalar", "string", "number", "integer", "boolean", "null", "sequence"] = "scalar"
    allowed: tuple[Scalar, ...] = ()

    @model_validator(mode="after")
    def nonempty_path(self):
        if not self.path or any(type(part) is int and part < 0 for part in self.path):
            raise ValueError("predicate_path_empty_or_negative")
        if any(type(part) is str and not part for part in self.path):
            raise ValueError("predicate_path_empty_component")
        if any(not _domain(value, self.domain) for value in self.allowed):
            raise ValueError("predicate_allowed_value_domain_mismatch")
        return self


class TextValue(Frozen):
    kind: Literal["text"]
    parts: tuple[StrictStr | FieldValue, ...]

    @model_validator(mode="after")
    def nonempty_parts(self):
        if not self.parts:
            raise ValueError("predicate_text_parts_empty")
        return self


class DerivedValue(Frozen):
    kind: Literal["derived"]
    expression: ValueExpression

    @field_validator("expression", mode="before")
    @classmethod
    def admit_expression(cls, value):
        return parse_value(value)


type Operand = Annotated[LiteralValue | FieldValue | TextValue | DerivedValue, Field(discriminator="kind")]


class Comparison(Frozen):
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in"]
    left: Operand
    right: Operand


class Junction(Frozen):
    op: Literal["all", "any"]
    args: tuple[Predicate, ...]

    @model_validator(mode="after")
    def nonempty_args(self):
        if not self.args:
            raise ValueError("predicate_junction_empty")
        return self


class Negation(Frozen):
    op: Literal["not"]
    arg: Predicate


class LabeledLine(Frozen):
    """One exact plain-text ``<label> <number>`` line equal to a typed decimal.

    Only unquoted, unindented lines outside code fences that begin with the
    exact label are readable. Any other line containing the label's words in
    order (ignoring case, punctuation and Unicode/zero-width spacing), an
    unparseable value or conflicting values is unknown; no such mention at all
    is known false. This is a numeric-line check, not report verification.
    """

    op: Literal["line_number_eq"]
    text: FieldValue
    label: StrictStr = Field(min_length=1, max_length=128)
    format: Literal["usd_string", "decimal_string"]
    expected: Operand

    @model_validator(mode="after")
    def plain_label(self):
        if self.text.domain != "string" or self.text.allowed:
            raise ValueError("predicate_line_text_requires_string_field")
        if self.label != self.label.strip() or any(char in self.label for char in "\r\n"):
            raise ValueError("predicate_line_label_invalid")
        return self


class MentionTerm(Frozen):
    """One value to find in message text; see ``Mentions`` for the modes."""

    value: Operand
    mode: Literal["words", "verbatim", "amount", "amount_reformatted", "clock_time"]
    format: Literal["usd_string", "usd_marked", "decimal_string"] | None = None
    excluding: tuple[StrictStr | FieldValue, ...] = ()
    # The value must be the only value of its kind in the matching unit
    # (see ``_rivals``); omitted when false so existing digests are unchanged.
    sole: StrictBool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def coherent_term(self):
        if (self.mode in {"amount", "amount_reformatted"}) != (self.format is not None):
            raise ValueError("predicate_mentions_amount_requires_format")
        if self.excluding and self.mode != "words":
            raise ValueError("predicate_mentions_excluding_requires_words")
        if self.sole and self.mode not in {"amount", "amount_reformatted", "clock_time"}:
            raise ValueError("predicate_mentions_sole_requires_amount_or_clock_time")
        return self


class Mentions(MentionTerm):
    """Whether readable message text mentions one value (report fact coverage).

    ``words``: the value's words appear as a contiguous whole-word sequence
    (case/Unicode-spacing insensitive); hyphenated and apostrophe words stay one
    word, and a match found only by splitting them is unknown unless a listed
    longer name in ``excluding`` explains it. ``verbatim``: the exact source
    string appears with word and digit-group boundaries. ``amount``: a
    standalone number (not a clock time, date or reference code) equals the
    typed decimal under ``format``. ``amount_reformatted``: such a number is
    written differently from the source string (e.g. "36000 USD" for a
    verbatim-required "$36,000"); use it in guards. ``clock_time``: a time of day in the text
    ("2:30 PM", "2pm", "14:30") equals the value; a meridiem-less one-digit hour
    ("2:30") is ambiguous.

    A magnitude suffix is read exactly ("$120k" is 120000; a bare "1.2m" only
    unknown near 1200000); values it could be rounded from stay unknown.

    Found in a readable line is known true. Found only in quoted (``>``) or
    fenced lines, an ambiguous form ("2:30", "$4.2k" for 4250) or an oversized
    text is unknown. Otherwise known false. Presence is not a positive assertion:
    negations ("not Acme") still mention the value.
    """

    op: Literal["mentions"]
    text: FieldValue

    @model_validator(mode="after")
    def coherent(self):
        if self.text.domain != "string" or self.text.allowed:
            raise ValueError("predicate_mentions_text_requires_string_field")
        return self


class MentionsTogether(Frozen):
    """All terms mentioned on one readable line (e.g. an amount beside its item).

    Per line, each term is true/false/unknown as in ``Mentions``; a line is true
    when every term is, false when any term is. Some readable line true is
    known true; a line that could still be true (unknown terms, or a true
    unreadable line) makes the result unknown; otherwise known false.

    ``excluding_values``: terms that must be absent from the same unit. A unit
    mentioning one is false; one whose presence is unknown (or only in an
    unreadable line) cannot be true. With them a single term is allowed.
    """

    op: Literal["mentions_together"]
    text: FieldValue
    terms: tuple[MentionTerm, ...] = Field(min_length=1, max_length=8)
    # ``block``: within one paragraph (blank-line separated) instead of one line;
    # ``text``: the whole text is one unit (e.g. a record's ``values_text``).
    scope: Literal["line", "block", "text"] = "line"
    excluding_values: tuple[MentionTerm, ...] = Field(default=(), max_length=16, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def coherent(self):
        if self.text.domain != "string" or self.text.allowed:
            raise ValueError("predicate_mentions_text_requires_string_field")
        if len(self.terms) < 2 and not self.excluding_values:
            raise ValueError("predicate_mentions_together_requires_two_terms_or_exclusions")
        return self


class Proven(Frozen):
    """Unknown counts as false: only a proven ``arg`` is true.

    For declared eligibility where unreadable data must not qualify (e.g.
    decoy rows nobody can parse); never use it to turn missing evidence of an
    agent's action into a pass or a failure.
    """

    op: Literal["proven"]
    arg: Predicate


class Exists(Frozen):
    """Some member of a declared closed population satisfies ``where``.

    ``where`` reads ``member.*`` (the population row) plus the enclosing
    context (``effect``, ``request``, lookups, joins...). True when some member
    is proven, false when every member is decided false (an empty closed
    population is false), unknown otherwise. The caller supplies closed
    populations under ``EXISTS_CONTEXT``; an absent or oversized one is unknown.
    """

    op: Literal["exists"]
    population: StrictStr = Field(min_length=1, pattern=r"\S")
    where: Predicate
    max_members: StrictInt = Field(default=4096, ge=1, le=65536)


type Predicate = Annotated[
    Comparison | Junction | Negation | LabeledLine | Mentions | MentionsTogether | Proven | Exists,
    Field(discriminator="op"),
]
Junction.model_rebuild()
Negation.model_rebuild()
Proven.model_rebuild()
Exists.model_rebuild()
PREDICATE = TypeAdapter(Predicate)


def context_paths(raw):
    """Context paths named by raw field/input operands anywhere in a structure.

    ``member.*`` inside an ``exists`` is bound to its population row, not to
    the enclosing context, and is not reported.
    """
    if isinstance(raw, dict):
        if raw.get("op") == "exists" and "where" in raw:
            yield from (path for path in context_paths(raw["where"]) if path[:1] != ("member",))
            return
        if raw.get("kind") in {"field", "input"} and raw.get("path") is not None:
            yield tuple(raw["path"])
        for value in raw.values():
            yield from context_paths(value)
    elif isinstance(raw, (list, tuple)):
        for value in raw:
            yield from context_paths(value)


@dataclass(frozen=True)
class PredicateResult:
    value: bool | None
    reason: str
    evidence_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ConditionalResult:
    status: Literal["valid", "inapplicable", "unavailable"]
    value: bool | None
    reason: str
    evidence_paths: tuple[Path, ...]


def _validate_tree(predicate: Predicate) -> None:
    pending = [(predicate, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 32 or count > 512:
            raise ValueError("predicate_structure_budget_exceeded")
        if isinstance(item, Junction):
            pending.extend((arg, depth + 1) for arg in item.args)
        elif isinstance(item, Negation):
            pending.append((item.arg, depth + 1))
        elif isinstance(item, Exists):
            pending.append((item.where, depth + 1))


def parse_predicate(raw: Any) -> Predicate:
    """Bound raw structure before recursive validation to avoid excessive trees."""
    raw = raw.model_dump(mode="python") if hasattr(raw, "model_dump") else raw
    pending = [(raw, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 96 or nodes > 4096:
            raise ValueError("predicate_structure_budget_exceeded")
        if isinstance(item, dict):
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, (tuple, list)):
            pending.extend((value, depth + 1) for value in item)
    predicate = PREDICATE.validate_python(raw)
    _validate_tree(predicate)
    return predicate


def resolve_operand(operand: Operand, context: Mapping) -> tuple[bool, Any, tuple[Path, ...]]:
    if isinstance(operand, DerivedValue):
        result = evaluate_value(operand.expression, context)
        return result.status == "qualified", result, result.evidence_paths
    if isinstance(operand, LiteralValue):
        return True, operand.value, ()
    if isinstance(operand, TextValue):
        values, paths = [], []
        for part in operand.parts:
            if isinstance(part, str):
                values.append(part)
                continue
            known, value, refs = resolve_operand(part, context)
            paths.extend(refs)
            if not known or not isinstance(value, str):
                return False, None, tuple(dict.fromkeys(paths))
            values.append(value)
        return True, "".join(values), tuple(dict.fromkeys(paths))
    value: Any = context
    for part in operand.path:
        if isinstance(part, int):
            if not isinstance(value, (list, tuple)) or part >= len(value):
                return False, None, (operand.path,)
            value = value[part]
        else:
            if not isinstance(value, Mapping) or part not in value:
                return False, None, (operand.path,)
            value = value[part]
    if not _domain(value, operand.domain) or (
        operand.allowed and not any(_equal(value, allowed) for allowed in operand.allowed)
    ):
        return False, None, (operand.path,)
    return True, value, (operand.path,)


def _scalar(value: Any) -> bool:
    return type(value) in {str, bool, int, type(None)} or (
        type(value) is float and math.isfinite(value)
    )


def _domain(value: Any, domain: str) -> bool:
    if domain == "scalar":
        return _scalar(value)
    if domain == "number":
        return type(value) in {int, float} and _scalar(value)
    if domain == "sequence":
        return isinstance(value, (list, tuple)) and all(_scalar(item) for item in value)
    return type(value) is {"string": str, "integer": int, "boolean": bool, "null": type(None)}[domain]


def _equal(left: Any, right: Any) -> bool:
    # bool is a distinct identity/value domain, despite Python's True == 1.
    if type(left) in {int, float} and type(right) in {int, float}:
        return left == right
    return type(left) is type(right) and left == right


def _paths(results) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(path for result in results for path in result.evidence_paths))


def evaluate_predicate(predicate: Predicate, context: Mapping) -> PredicateResult:
    """Three-valued logic: known false/true can settle conjunction/disjunction."""
    _validate_tree(predicate)
    return _evaluate(predicate, context)


def _evaluate(predicate: Predicate, context: Mapping) -> PredicateResult:
    if isinstance(predicate, Junction):
        results = tuple(_evaluate(arg, context) for arg in predicate.args)
        values = tuple(result.value for result in results)
        if predicate.op == "all":
            value = False if False in values else None if None in values else True
        else:
            value = True if True in values else None if None in values else False
        return PredicateResult(value, "predicate_decided" if value is not None else "predicate_input_unavailable", _paths(results))
    if isinstance(predicate, Negation):
        result = _evaluate(predicate.arg, context)
        return PredicateResult(None if result.value is None else not result.value, result.reason, result.evidence_paths)
    if isinstance(predicate, LabeledLine):
        return _labeled_line(predicate, context)
    if isinstance(predicate, Mentions):
        return _mentions_value(predicate, context)
    if isinstance(predicate, MentionsTogether):
        return _mentions_together(predicate, context)
    if isinstance(predicate, Exists):
        return _exists(predicate, context)
    if isinstance(predicate, Proven):
        result = _evaluate(predicate.arg, context)
        return PredicateResult(result.value is True, "predicate_proven" if result.value else "predicate_not_proven",
                               result.evidence_paths)
    left_known, left, left_paths = resolve_operand(predicate.left, context)
    right_known, right, right_paths = resolve_operand(predicate.right, context)
    paths = tuple(dict.fromkeys(left_paths + right_paths))
    if not left_known or not right_known:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    if isinstance(left, ValueResult) or isinstance(right, ValueResult):
        # A declared boolean result can be tested against a strict boolean.
        # Numeric 0/1 and strings still cannot stand in for truth values.
        boolean, raw = (left, right) if isinstance(left, ValueResult) else (right, left)
        if isinstance(boolean, ValueResult) and boolean.kind == "boolean" and type(raw) is bool:
            if predicate.op not in {"eq", "ne"}:
                return PredicateResult(None, "predicate_derived_operation_unavailable", paths)
            value = boolean.canonical_value == raw
            return PredicateResult(value if predicate.op == "eq" else not value, "predicate_decided", paths)
        # Typed derivations are compared explicitly on both sides. Raw strings
        # and numeric literals must not silently acquire date/money semantics.
        if not isinstance(left, ValueResult) or not isinstance(right, ValueResult) or left.kind != right.kind:
            return PredicateResult(None, "predicate_derived_type_unavailable", paths)
        if predicate.op == "in" or (predicate.op not in {"eq", "ne"} and left.kind == "boolean"):
            return PredicateResult(None, "predicate_derived_operation_unavailable", paths)
        a, b = left.canonical_value, right.canonical_value
        if predicate.op in {"eq", "ne"}:
            value = a == b
            if predicate.op == "ne":
                value = not value
            return PredicateResult(value, "predicate_decided", paths)
        if left.kind == "decimal":
            x, y = Decimal(str(a)), Decimal(str(b))
            ordering = (x > y) - (x < y)
        elif isinstance(a, str) and isinstance(b, str):
            ordering = (a > b) - (a < b)
        elif type(a) is int and type(b) is int:
            ordering = a - b
        else:
            return PredicateResult(None, "predicate_derived_type_unavailable", paths)
        value = {"lt": ordering < 0, "lte": ordering <= 0,
                 "gt": ordering > 0, "gte": ordering >= 0}[predicate.op]
        return PredicateResult(value, "predicate_decided", paths)
    if predicate.op == "in":
        if not _scalar(left) or not isinstance(right, (list, tuple)) or not all(_scalar(item) for item in right):
            return PredicateResult(None, "predicate_membership_type_unavailable", paths)
        value = any(_equal(left, item) for item in right)
    elif not _scalar(left) or not _scalar(right):
        return PredicateResult(None, "predicate_scalar_type_unavailable", paths)
    elif predicate.op in {"eq", "ne"}:
        value = _equal(left, right)
        if predicate.op == "ne":
            value = not value
    else:
        if type(left) not in {int, float} or type(right) not in {int, float}:
            return PredicateResult(None, "predicate_ordered_number_unavailable", paths)
        value = {"lt": lambda: left < right, "lte": lambda: left <= right,
                 "gt": lambda: left > right, "gte": lambda: left >= right}[predicate.op]()
    return PredicateResult(value, "predicate_decided", paths)


_LINE_TEXT_BUDGET = 65536
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), " ")


def _words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", text.translate(_INVISIBLE).casefold()))


def _mentions(line: str, label: tuple[str, ...]) -> bool:
    words = _words(line)
    return any(words[index:index + len(label)] == label for index in range(len(words) - len(label) + 1))


def _labeled_line(predicate: LabeledLine, context: Mapping) -> PredicateResult:
    text_known, text, text_paths = resolve_operand(predicate.text, context)
    expected_known, expected, expected_paths = resolve_operand(predicate.expected, context)
    paths = tuple(dict.fromkeys(text_paths + expected_paths))
    if not text_known or not expected_known:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    if not isinstance(expected, ValueResult) or expected.kind != "decimal":
        return PredicateResult(None, "predicate_line_expected_type_unavailable", paths)
    if len(text) > _LINE_TEXT_BUDGET:
        return PredicateResult(None, "predicate_line_text_budget_exceeded", paths)
    label = _words(predicate.label) or (predicate.label.casefold(),)
    values, fence, ambiguous = set(), None, False
    for line in text.splitlines():
        mention = _mentions(line, label) if _words(predicate.label) else predicate.label in line
        opener = _FENCE.match(line)
        if opener is not None:
            marker = opener.group(1)
            # A fence closes only on the same character, at least as long.
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not line.strip()[len(marker):]:
                fence = None
            ambiguous = ambiguous or mention
            continue
        if not mention:
            continue
        body = line.strip()
        indented = line.startswith(("    ", "\t"))
        if fence is not None or indented or not body.startswith(predicate.label):
            ambiguous = True
            continue
        try:
            values.add(_decimal(body[len(predicate.label):].strip(), predicate.format))
        except _Unavailable:
            ambiguous = True
    if ambiguous:
        return PredicateResult(None, "predicate_line_ambiguous", paths)
    if not values:
        return PredicateResult(False, "predicate_line_absent", paths)
    if len(values) > 1:
        return PredicateResult(None, "predicate_line_conflicting", paths)
    return PredicateResult(values.pop() == Fraction(str(expected.canonical_value)), "predicate_decided", paths)


_TOKEN = re.compile(r"\w+(?:['\u2019-]\w+)*")
_SPLIT_TOKEN = re.compile(r"\w+")
# A standalone number: not part of a word, clock time (11:30), reference or date
# (PMT-2026-0402, 2026-02-01) or fraction-like code (1/2). Digit groups end in
# a digit, so a trailing list comma ("$8,420, no") is punctuation. An adjacent
# k/m/b magnitude suffix is captured (see ``_magnitude``).
_NUMBER = re.compile(
    r"(?<![\w.,$:/-])(?<!\w-)-?\$?\d(?:[\d,]*\d)?(?:\.\d+)?([kKmMbB])?(?![\w:/])(?!-\d)(?![.,]\d)"
)
_MAGNITUDE = {"k": 1000, "m": 1000000, "b": 1000000000}


_POSSESSIVE = re.compile(r"['\u2019]s$")


def _tokens(text: str, *, split: bool = False) -> list[str]:
    pattern = _SPLIT_TOKEN if split else _TOKEN
    # A trailing possessive ("Hal's") is the word itself; "O'Brien" stays one word.
    return [_POSSESSIVE.sub("", token) for token in pattern.findall(text.translate(_INVISIBLE).casefold())]


def _readable_lines(text: str):
    """Yield (line, readable) with quoted and fenced lines marked unreadable."""
    fence = None
    for line in text.splitlines():
        opener = _FENCE.match(line)
        if opener is not None:
            marker = opener.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not line.strip()[len(marker):]:
                fence = None
            yield line, False
            continue
        yield line, fence is None and not line.lstrip().startswith(">")


def _word_hit(line: str, target: list[str], longer: list[list[str]], *, split: bool = False) -> bool:
    words = _tokens(line, split=split)
    size = len(target)
    covered = set()
    for other in longer:
        for start in range(len(words) - len(other) + 1):
            if words[start:start + len(other)] == other:
                covered.update(range(start, start + len(other)))
    return any(
        words[start:start + size] == target and not set(range(start, start + size)) <= covered
        for start in range(len(words) - size + 1)
    )


_CLOCK_12_TEXT = re.compile(r"(?<![\w:])(\d{1,2})(?::([0-5]\d))?\s*([ap])\.?\s*m\.?(?![a-z])", re.IGNORECASE)
_CLOCK_24_TEXT = re.compile(r"(?<![\w:])(0\d|1[3-9]|2[0-3]):([0-5]\d)(?![\w:])(?!-\w)(?!\s*[ap]\.?\s*m)", re.IGNORECASE)
_CLOCK_BARE_TEXT = re.compile(r"(?<![\w:])([1-9]|1[0-2]):([0-5]\d)(?![\w:])(?!-\w)(?!\s*[ap]\.?\s*m)", re.IGNORECASE)
# "1:00–1:15 PM" / "10-10:30am": a trailing meridiem applies to both ends.
_CLOCK_RANGE_TEXT = re.compile(
    r"(?<![\w:])(\d{1,2})(?::([0-5]\d))?\s*(?:-|\u2013|\u2014|to)\s*(\d{1,2})(?::([0-5]\d))?\s*([ap])\.?\s*m\.?(?![a-z])",
    re.IGNORECASE,
)
# "13:00-13:30" / "9:00-17:00": a range with one unambiguous 24-hour end is 24-hour.
_CLOCK_RANGE_24_TEXT = re.compile(
    r"(?<![\w:])([01]?\d|2[0-3]):([0-5]\d)\s*(?:-|\u2013|\u2014|to)\s*([01]?\d|2[0-3]):([0-5]\d)(?![\w:])"
    r"(?!\s*[ap]\.?\s*m)",
    re.IGNORECASE,
)
_NOON_TEXT = re.compile(r"(?<![\w])(?:12\s+)?(noon|midnight)(?![\w])", re.IGNORECASE)


@dataclass(frozen=True)
class _Term:
    mode: str
    format: str | None
    literal: str
    expected: Fraction | None
    target: tuple[str, ...]
    split_target: tuple[str, ...]
    longer: tuple[tuple[str, ...], ...]
    split_longer: tuple[tuple[str, ...], ...]
    pattern: re.Pattern | None
    sole: bool = False


def _prepare(term: MentionTerm, context: Mapping):
    """Return (_Term | None, reason, paths); None means the term is unknown."""
    known, value, paths = resolve_operand(term.value, context)
    if not known:
        return None, "predicate_field_unavailable", paths
    expected = None
    source_text = value if isinstance(value, str) else None
    if term.mode in {"amount", "amount_reformatted", "clock_time"}:
        if isinstance(value, ValueResult):
            if value.kind != "decimal":
                return None, "predicate_mentions_value_type_unavailable", paths
            expected = Fraction(str(value.canonical_value))
        else:
            try:
                expected = (clock_minutes(value) if term.mode == "clock_time"
                            else _decimal(value, term.format))
            except _Unavailable:
                return None, "predicate_mentions_value_unavailable", paths
        literal = ""
    elif type(value) in {int, float} and term.mode == "verbatim":
        literal = canonical_json(value)  # a numeric source value's own text form
    elif type(value) is not str or not value.strip():
        return None, "predicate_mentions_value_unavailable", paths
    else:
        literal = value
    if term.mode == "amount_reformatted":
        if source_text is None:
            return None, "predicate_mentions_reformatted_requires_source_text", paths
        literal = source_text.strip()
    target = tuple(_tokens(literal)) if term.mode == "words" else ()
    if term.mode == "words" and not target:
        return None, "predicate_mentions_value_unavailable", paths
    longer, split_longer = [], []
    for item in term.excluding:
        if isinstance(item, str):
            item_known, other = True, item
        else:
            item_known, other, refs = resolve_operand(item, context)
            paths = tuple(dict.fromkeys(paths + refs))
        if not item_known or type(other) is not str:
            return None, "predicate_mentions_excluding_unavailable", paths
        split_other = _tokens(other, split=True)
        if len(split_other) > len(_tokens(literal, split=True)):
            longer.append(tuple(_tokens(other)))
            split_longer.append(tuple(split_other))
    pattern = (
        re.compile(r"(?<![\w$])(?<!\d[.,])" + re.escape(literal) + r"(?!\w)(?![.,]\d)")
        if term.mode == "verbatim" else None
    )
    return _Term(term.mode, term.format, literal, expected, target,
                 tuple(_tokens(literal, split=True)) if term.mode == "words" else (),
                 tuple(longer), tuple(split_longer), pattern, term.sole), "prepared", paths


def _term_in_line(term: _Term, line: str) -> bool | None:
    if term.mode == "words":
        if _word_hit(line, list(term.target), [list(item) for item in term.longer]):
            return True
        split = _word_hit(line, list(term.split_target), [list(item) for item in term.split_longer], split=True)
        return None if split else False
    if term.pattern is not None:
        return term.pattern.search(line) is not None
    if term.mode == "clock_time":
        times, bare = _clock_times(line)
        if term.expected in times:
            return True
        return None if bare else False
    ambiguous = reformatted = False
    for match in _NUMBER.finditer(line):
        suffix = match.group(1)
        body = match.group(0)[:-1] if suffix else match.group(0)
        try:
            value = _decimal(body, term.format)
        except _Unavailable:
            if term.mode != "amount_reformatted":
                continue
            try:  # e.g. "36000" under a usd_marked source: compare loosely
                value = _decimal(body, "usd_string")
            except _Unavailable:
                continue
        equal = _magnitude(value, suffix, body, term.expected) if suffix else value == term.expected
        if equal is None:
            ambiguous = True
            continue
        if not equal:
            continue
        if term.mode == "amount":
            return True
        if match.group(0) != term.literal:
            reformatted = True
    if reformatted:
        return True
    return None if ambiguous else False


def _clock_times(line: str) -> tuple[list[Fraction], bool]:
    """Readable times of day (both ends of ranges) and whether a bare hour remains."""
    def twelve(hour, minute, meridiem):
        return Fraction((int(hour) % 12 + (12 if meridiem.lower() == "p" else 0)) * 60 + int(minute or 0))
    times, rest = [], line
    for m in _CLOCK_RANGE_TEXT.finditer(line):
        if 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(3)) <= 12:
            times += [twelve(m.group(1), m.group(2), m.group(5)), twelve(m.group(3), m.group(4), m.group(5))]
            rest = rest.replace(m.group(0), " ")
    for m in _CLOCK_RANGE_24_TEXT.finditer(rest):
        if any(hour.startswith("0") or int(hour) >= 13 for hour in (m.group(1), m.group(3))):
            times += [Fraction(int(m.group(1)) * 60 + int(m.group(2))), Fraction(int(m.group(3)) * 60 + int(m.group(4)))]
            rest = rest.replace(m.group(0), " ")
    times += [twelve(m.group(1), m.group(2), m.group(3))
              for m in _CLOCK_12_TEXT.finditer(rest) if 1 <= int(m.group(1)) <= 12]
    times += [Fraction(int(m.group(1)) * 60 + int(m.group(2))) for m in _CLOCK_24_TEXT.finditer(rest)]
    times += [Fraction(720 if m.group(1).lower() == "noon" else 0) for m in _NOON_TEXT.finditer(rest)]
    return times, _CLOCK_BARE_TEXT.search(rest) is not None


# Number kinds for ``sole``; a rival of a "fail" kind sinks the unit, an
# "open" kind keeps it unknown, others (counts, years, percents) are unrelated.
_RANGE_JOIN = re.compile(r"\s*,?\s*(?:-|\u2013|\u2014|/|~|to|or|through|thru)\s*", re.IGNORECASE)
_SOLE_KINDS = {
    "money": ({"money", "grouped"}, {"decimal", "integer"}),
    "decimal": ({"decimal"}, set()),
    "integer": ({"money", "grouped", "integer"}, {"decimal"}),
    "count": (set(), {"count", "integer"}),
}


def _number_kind(line: str, match) -> str:
    body = match.group(0)
    if line[match.end():].lstrip().startswith("%") or re.match(r"\s*percent\b", line[match.end():], re.IGNORECASE):
        return "percent"
    if "$" in body:
        return "money"
    if "." in body:
        return "decimal"
    if "," in body or match.group(1):
        return "grouped"
    digits = body.lstrip("-")
    if len(digits) == 4 and 1900 <= int(digits) <= 2100:
        return "year"
    return "count" if int(digits) < 1000 else "integer"


def _target_kind(term: _Term) -> str:
    if term.format in {"usd_string", "usd_marked"}:
        return "money"
    expected = term.expected
    if expected is None or expected.denominator != 1:
        return "decimal"
    return "integer" if abs(expected) >= 1000 else "count"


def _rivals(term: _Term, line: str) -> bool | None:
    """Another value of the target's kind in the line: True, unknown or False.

    Clock times: any other time (both ends of a range). Amounts: kinds are
    money ($-marked) / grouped / decimal / integer (>= 1000) / count / year /
    percent; ``_SOLE_KINDS`` says which sink or open the unit for the target's
    kind. A number joined to a target occurrence by a range or alternative
    ("to", "-", "/", "or") is always a rival. Repeats of the value are fine.
    """
    if term.mode == "clock_time":
        times, bare = _clock_times(line)
        if any(time != term.expected for time in times):
            return True
        return None if bare else False
    fail, open_ = _SOLE_KINDS[_target_kind(term)]
    matches = list(_NUMBER.finditer(line))
    values = []
    for match in matches:
        suffix = match.group(1)
        body = match.group(0)[:-1] if suffix else match.group(0)
        try:
            value = _decimal(body, "usd_string" if "$" in body or "," in body else "decimal_string")
        except _Unavailable:
            values.append(None)
            continue
        values.append(_magnitude(value, suffix, body, term.expected) if suffix else value == term.expected)
    verdict = False
    for index, (match, equal) in enumerate(zip(matches, values, strict=True)):
        if equal is True:
            continue
        partner = any(
            values[other] is True and _RANGE_JOIN.fullmatch(
                line[min(match.end(), matches[other].end()):max(match.start(), matches[other].start())])
            for other in (index - 1, index + 1) if 0 <= other < len(matches)
        )
        kind = _number_kind(line, match)
        if equal is False and (partner or kind in fail):
            return True
        if partner or kind in fail or kind in open_:
            verdict = None
    return verdict


def _magnitude(value: Fraction, suffix: str, body: str, expected) -> bool | None:
    """"$120k" is 120000; only values it could round from stay unknown.

    ``k`` (or a dollar-marked ``m``/``b``) equal to the value is true; a value
    within the token's rounding is unknown (approximation or unit reading);
    anything else is false, so the token never blocks unrelated amounts.
    """
    scale = _MAGNITUDE[suffix.lower()]
    decimals = len(body.partition(".")[2])
    if abs(expected - value * scale) > Fraction(scale, 2 * 10 ** decimals):
        return False
    if expected == value * scale and (suffix in "kK" or "$" in body):
        return True
    return None


def _scan(text: str, judge) -> tuple[bool | None, str]:
    found_hidden = unknown = False
    for line, readable in _readable_lines(text):
        verdict = judge(line)
        if verdict is True and readable:
            return True, "predicate_decided"
        if verdict is True or verdict is None:
            found_hidden = found_hidden or verdict is True
            unknown = unknown or verdict is None
    if found_hidden or unknown:
        return None, "predicate_mentions_unreadable_or_ambiguous"
    return False, "predicate_mentions_absent"


def _mentions_value(predicate: Mentions, context: Mapping) -> PredicateResult:
    text_known, text, paths = resolve_operand(predicate.text, context)
    term, reason, term_paths = _prepare(predicate, context)
    paths = tuple(dict.fromkeys(paths + term_paths))
    if not text_known:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    if term is None:
        return PredicateResult(None, reason, paths)
    if len(text) > _LINE_TEXT_BUDGET:
        return PredicateResult(None, "predicate_mentions_text_budget_exceeded", paths)
    judge = (lambda line: _presence(term, [(line, True)])) if term.sole else (lambda line: _term_in_line(term, line))
    value, reason = _scan(text, judge)
    return PredicateResult(value, reason, paths)


def _mentions_together(predicate: MentionsTogether, context: Mapping) -> PredicateResult:
    text_known, text, paths = resolve_operand(predicate.text, context)
    prepared, excluded = [], []
    for target, items in ((prepared, predicate.terms), (excluded, predicate.excluding_values)):
        for item in items:
            term, reason, term_paths = _prepare(item, context)
            paths = tuple(dict.fromkeys(paths + term_paths))
            if term is None:
                return PredicateResult(None, reason, paths)
            target.append(term)
    if not text_known:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    if len(text) > _LINE_TEXT_BUDGET:
        return PredicateResult(None, "predicate_mentions_text_budget_exceeded", paths)
    value, reason = _scan_units(_units(text, predicate.scope), prepared, excluded)
    return PredicateResult(value, reason, paths)


def _units(text: str, scope: str) -> list[list[tuple[str, bool]]]:
    lines = list(_readable_lines(text))
    if scope == "line":
        return [[line] for line in lines]
    if scope == "text":
        return [lines]
    blocks, current = [], []
    for line, readable in lines:
        if not line.strip():
            if current:
                blocks.append(current)
            current = []
        else:
            current.append((line, readable))
    if current:
        blocks.append(current)
    return blocks


def _presence(term, unit) -> bool | None:
    seen = [(_term_in_line(term, line), readable) for line, readable in unit]
    if any(value is True and readable for value, readable in seen):
        found = True
    else:
        return None if any(value is None or value is True for value, _ in seen) else False
    if term.sole:
        rivals = [(_rivals(term, line), readable) for line, readable in unit]
        if any(value is True and readable for value, readable in rivals):
            return False
        if any(value is not False for value, _ in rivals):
            return None
    return found


def _scan_units(units, prepared, excluded) -> tuple[bool | None, str]:
    """Every term somewhere in one unit (line/block/text), no excluded value there."""
    unknown = False
    for unit in units:
        verdicts = [_presence(term, unit) for term in prepared]
        if False in verdicts:
            continue
        absent = [_presence(term, unit) for term in excluded]
        if True in absent:
            continue
        if all(verdict is True for verdict in verdicts) and None not in absent:
            return True, "predicate_decided"
        unknown = True
    if unknown:
        return None, "predicate_mentions_unreadable_or_ambiguous"
    return False, "predicate_mentions_absent"


def evaluate_conditional(
    predicate: Predicate, context: Mapping, *, when: Predicate | None = None,
) -> ConditionalResult:
    """An unknown condition cannot be treated as a false/inapplicable branch."""
    condition = evaluate_predicate(when, context) if when is not None else PredicateResult(True, "unconditional")
    if condition.value is None:
        return ConditionalResult("unavailable", None, "predicate_condition_unavailable", condition.evidence_paths)
    if not condition.value:
        return ConditionalResult("inapplicable", None, "predicate_condition_false", condition.evidence_paths)
    result = evaluate_predicate(predicate, context)
    return ConditionalResult(
        "valid" if result.value is not None else "unavailable", result.value,
        result.reason, _paths((condition, result)),
    )


# Context key under which callers publish closed populations for ``exists``.
EXISTS_CONTEXT = "population"


def exists_populations(raw):
    """Population names read by ``exists`` predicates anywhere in a raw structure."""
    if isinstance(raw, dict):
        if raw.get("op") == "exists" and type(raw.get("population")) is str:
            yield raw["population"]
        for value in raw.values():
            yield from exists_populations(value)
    elif isinstance(raw, (list, tuple)):
        for value in raw:
            yield from exists_populations(value)


def _exists(predicate: Exists, context: Mapping) -> PredicateResult:
    root = (EXISTS_CONTEXT, predicate.population)
    published = context.get(EXISTS_CONTEXT)
    members = published.get(predicate.population) if isinstance(published, Mapping) else None
    if not isinstance(members, (list, tuple)) or len(members) > predicate.max_members:
        return PredicateResult(None, "predicate_exists_population_unavailable", (root,))
    paths: list[tuple] = [root]
    unknown = False
    for index, member in enumerate(members):
        result = _evaluate(predicate.where, {**context, "member": member})
        # Member reads are reported against the row they came from.
        paths.extend((*root, index, *path[1:]) if path[:1] == ("member",) else path
                     for path in result.evidence_paths)
        if result.value is True:
            return PredicateResult(True, "predicate_decided", tuple(dict.fromkeys(paths)))
        unknown = unknown or result.value is None
    return PredicateResult(None if unknown else False,
                           "predicate_input_unavailable" if unknown else "predicate_decided",
                           tuple(dict.fromkeys(paths)))
