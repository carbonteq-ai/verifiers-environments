"""Bounded declarative predicates over evidence; absent values stay unknown.

These operations interpret manifest data, not task names or natural-language
policy. Context preparation and evidence qualification belong to the caller.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
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
    MONTH_NUMBERS,
    WEEKDAY_NUMBERS,
    ValueExpression,
    ValueResult,
    _decimal,
    _Unavailable,
    calendar_day,
    clock_minutes,
    evaluate_exact_decimal,
    evaluate_value,
    parse_value,
    round_places,
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


class TextLength(Frozen):
    """Length of an explicitly projected string, without trimming or coercion."""

    kind: Literal["text_length"]
    text: FieldValue
    unit: Literal["unicode_codepoints"]

    @model_validator(mode="after")
    def string_field(self):
        if self.text.domain != "string":
            raise ValueError("predicate_text_length_requires_string_field")
        return self


type Operand = Annotated[LiteralValue | FieldValue | TextValue | DerivedValue | TextLength, Field(discriminator="kind")]


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


class DecimalPrecision(Frozen):
    """Declared acceptable written precision for an exact derived amount.

    A written number with ``p`` decimal places matches when it equals the
    exact value, or when ``min_places <= p <= max_places`` and it equals the
    exact value rounded to ``p`` places (``ties``: ``half_up``,
    ``half_even`` or ``either``). Coarser or wrongly rounded/truncated
    numbers are false. Only for arithmetic derivations: a verbatim source
    value is never matched by a rounded rewrite.
    """

    min_places: StrictInt = Field(ge=0, le=20)
    max_places: StrictInt | None = Field(default=None, ge=0, le=20, exclude_if=lambda value: value is None)
    ties: Literal["half_up", "half_even", "either"] = "either"

    @model_validator(mode="after")
    def ordered(self):
        if self.max_places is not None and self.max_places < self.min_places:
            raise ValueError("predicate_precision_places_unordered")
        return self


class MentionTerm(Frozen):
    """One value to find in message text; see ``Mentions`` for the modes."""

    value: Operand
    mode: Literal["words", "verbatim", "prefix", "amount", "amount_reformatted", "clock_time", "date"]
    format: Literal["usd_string", "usd_marked", "decimal_string"] | None = None
    # ``date`` only: the year of year-less prose dates ("March 5"); see _date_facts.
    assume_year: StrictInt | None = Field(default=None, ge=1900, le=2999, exclude_if=lambda value: value is None)
    excluding: tuple[StrictStr | FieldValue, ...] = ()
    # The value must be the only value of its kind in the matching unit
    # (see ``_rivals``); omitted when false so existing digests are unchanged.
    sole: StrictBool = Field(default=False, exclude_if=lambda value: not value)
    # ``amount`` of an arithmetic derivation only: accepted written precision.
    precision: DecimalPrecision | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def coherent_precision(self):
        if self.precision is not None and (
            self.mode != "amount" or not isinstance(self.value, DerivedValue)
            or getattr(self.value.expression, "kind", None) != "decimal"
        ):
            raise ValueError("predicate_precision_requires_derived_arithmetic_amount")
        return self

    @model_validator(mode="after")
    def coherent_term(self):
        if (self.mode in {"amount", "amount_reformatted"}) != (self.format is not None):
            raise ValueError("predicate_mentions_amount_requires_format")
        if self.excluding and self.mode != "words":
            raise ValueError("predicate_mentions_excluding_requires_words")
        if self.sole and self.mode not in {"amount", "amount_reformatted", "clock_time"}:
            raise ValueError("predicate_mentions_sole_requires_amount_or_clock_time")
        return self

    @model_validator(mode="after")
    def coherent_date_term(self):
        if self.assume_year is not None and self.mode != "date":
            raise ValueError("predicate_mentions_assume_year_requires_date")
        return self


class LabeledValue(Frozen):
    """The value a report states for a labelled field, with conflicts rejected.

    A label occurrence (``label``'s words, case/hyphen/punctuation
    insensitive, not inside a listed longer name in ``excluding``) is
    associated with numbers only in this representation, inside one segment
    (a line split at ``;``, ``|``, tab, bullet ``•`` or a sentence end):

    - ``<label><connector><values>``: connectors are ``:``, ``=``, dashes,
      ``(``, ``is``/``was``/``are``/``were``/``of``/``at``/``equals``/``total``;
    - ``<values> [:|-|in|of|for] <label>`` when the values open the segment;
    - ``<label>: <calculation> = <values>``: when ``=``, ``->`` or ``→``
      follows the label in its segment, only the values right after the last
      sign are stated (the calculation's inputs are not);
    - ``<values>`` is a run of numbers joined by ``,``, ``-``, ``/``, ``~``,
      ``to``, ``or``, ``and``, ``through``, ``vs`` or ``(or ...``; every number
      in the run is a stated value, so a hedge ("$100 or $175") states two.

    A number later in the segment after other words (``$40,000 (80% of
    $50,000)``) is not associated. A label whose segment has numbers only
    after other words ("for Eng is $100") is undecidable (unknown); a label
    without numbers in its segment states nothing. Percents and years are not
    values. With ``entity``, only units (``scope``: line or block) mentioning
    the entity count.

    With ``value`` (read under ``format``, optional ``precision``): true when
    some stated value exists and every stated value equals it; false when any
    readable stated value differs (a conflicting alternative or repeat) or
    none is stated; unknown when a stated value or association is
    undecidable or only in quoted/fenced lines. Without ``value``: true when
    some value is stated for the label (e.g. an excluded entity entered with an
    amount), unknown when only undecidable, false otherwise. This is a
    representation-bounded reading, not natural-language understanding.
    """

    op: Literal["labeled_value"]
    text: FieldValue
    label: Operand
    excluding: tuple[StrictStr | FieldValue, ...] = Field(default=(), max_length=16, exclude_if=lambda value: not value)
    entity: MentionTerm | None = Field(default=None, exclude_if=lambda value: value is None)
    scope: Literal["line", "block"] = "line"
    value: Operand | None = Field(default=None, exclude_if=lambda value: value is None)
    format: Literal["usd_string", "usd_marked", "decimal_string"]
    precision: DecimalPrecision | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def coherent(self):
        if self.text.domain != "string" or self.text.allowed:
            raise ValueError("predicate_labeled_value_text_requires_string_field")
        if self.entity is not None and self.entity.mode != "words":
            raise ValueError("predicate_labeled_value_entity_requires_words")
        if self.precision is not None:
            if self.value is None:
                raise ValueError("predicate_labeled_value_precision_requires_value")
            MentionTerm(value=self.value, mode="amount", format=self.format, precision=self.precision)
        return self


class DateWithin(Frozen):
    """Inclusive calendar interval for ``mentions`` ``mode: "date"``."""

    start: Operand
    end: Operand


class Mentions(MentionTerm):
    """Whether readable message text mentions one value (report fact coverage).

    ``words``: the value's words appear as a contiguous whole-word sequence
    (case/Unicode-spacing insensitive); hyphenated and apostrophe words stay one
    word, and a match found only by splitting them is unknown unless a listed
    longer name in ``excluding`` explains it. ``verbatim``: the exact source
    string appears with word and digit-group boundaries (so "INS-" never
    matches inside "INS-2026-014"). ``prefix``: the exact source string starts
    a token that continues with at least one more word character (a reference
    code such as "INS-2026-014" for the prefix "INS-"; "INS-" alone or
    "XINS-1" does not match). ``amount``: a
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

    ``date``: a calendar date stated in prose equals the ISO date value (see
    ``_date_facts``). With ``within`` instead of ``value``: at least one date is
    stated and every stated date lies in the inclusive interval.
    """

    op: Literal["mentions"]
    text: FieldValue
    value: Operand | None = Field(default=None, exclude_if=lambda value: value is None)
    within: DateWithin | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def coherent(self):
        if self.text.domain != "string" or self.text.allowed:
            raise ValueError("predicate_mentions_text_requires_string_field")
        return self

    @model_validator(mode="after")
    def value_or_within(self):
        if (self.value is None) == (self.within is None):
            raise ValueError("predicate_mentions_requires_value_or_within")
        if self.within is not None and self.mode != "date":
            raise ValueError("predicate_mentions_within_requires_date")
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


class Present(Frozen):
    """The field resolves to a non-null value.

    True for any non-null value; false for an explicit null, or when the path
    is decidably absent inside a known effect record (``effect.*`` /
    ``joined.*``: a missing key, a missing list index such as
    ``signers[1]`` with one signer, or a null container on the way); unknown
    when the root (the record itself) is unavailable, when a key is missing
    from any other root (rows, lookups, requests), or when a scalar sits where
    a container is expected.
    """

    op: Literal["present"]
    value: FieldValue


# Roots whose records are complete captured snapshots, so a missing key or
# index is decidably absent rather than unread.
_KNOWN_RECORD_ROOTS = frozenset({"effect", "joined"})


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


class Items(Frozen):
    """Quantify ``where`` over the items of one list field.

    ``items`` names the list (any context root); ``where`` reads ``item`` (the
    current element: ``["item"]`` for a scalar, ``["item", <key>...]`` for a
    record) plus the enclosing context. ``any_item``: true when some item is
    proven, false when every item is decided false (an empty list is false).
    ``all_items``: false when some item is decided false, true when every item
    is proven (an empty list is true). Otherwise unknown, including an
    unresolved, null or non-list ``items`` and lists over ``max_items``.
    """

    op: Literal["any_item", "all_items"]
    items: FieldValue
    where: Predicate
    max_items: StrictInt = Field(default=4096, ge=1, le=65536)

    @model_validator(mode="after")
    def list_operand(self):
        # The list is read structurally; scalar domains and allowed values
        # would silently make every list unknown.
        if self.items.domain != "scalar" or self.items.allowed:
            raise ValueError("predicate_items_operand_requires_plain_field")
        if self.items.path[0] == "item" and len(self.items.path) == 1:
            raise ValueError("predicate_items_operand_requires_plain_field")
        return self


type Predicate = Annotated[
    Comparison | Junction | Negation | LabeledLine | LabeledValue | Mentions | MentionsTogether | Proven | Exists
    | Present | Items,
    Field(discriminator="op"),
]
Junction.model_rebuild()
Negation.model_rebuild()
Proven.model_rebuild()
Exists.model_rebuild()
Items.model_rebuild()
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
        if raw.get("op") in {"any_item", "all_items"} and "where" in raw:
            # ``item.*`` is bound to the current list element.
            yield from context_paths(raw.get("items"))
            yield from (path for path in context_paths(raw["where"]) if path[:1] != ("item",))
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
        elif isinstance(item, (Exists, Items)):
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
    if isinstance(operand, TextLength):
        known, text, paths = resolve_operand(operand.text, context)
        if not known or type(text) is not str or len(text) > 65536:
            return False, None, paths
        return True, len(text), paths
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


def _present(path: Path, context: Mapping) -> PredicateResult:
    paths = (path,)
    if not isinstance(context, Mapping) or path[0] not in context:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    known_record = path[0] in _KNOWN_RECORD_ROOTS
    value: Any = context[path[0]]
    for part in path[1:]:
        if value is None:
            break
        if isinstance(part, int):
            if not isinstance(value, (list, tuple)):
                return PredicateResult(None, "predicate_field_unavailable", paths)
            if part >= len(value):
                return PredicateResult(False if known_record else None,
                                       "predicate_field_absent" if known_record else "predicate_field_unavailable", paths)
            value = value[part]
        else:
            if not isinstance(value, Mapping):
                return PredicateResult(None, "predicate_field_unavailable", paths)
            if part not in value:
                return PredicateResult(False if known_record else None,
                                       "predicate_field_absent" if known_record else "predicate_field_unavailable", paths)
            value = value[part]
    if value is None:
        return PredicateResult(False, "predicate_field_null", paths)
    return PredicateResult(True, "predicate_field_present", paths)


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
    if isinstance(predicate, LabeledValue):
        return _labeled_value(predicate, context)
    if isinstance(predicate, Mentions):
        return _mentions_value(predicate, context)
    if isinstance(predicate, MentionsTogether):
        return _mentions_together(predicate, context)
    if isinstance(predicate, Exists):
        return _exists(predicate, context)
    if isinstance(predicate, Present):
        return _present(predicate.value.path, context)
    if isinstance(predicate, Items):
        return _items(predicate, context)
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
        # A decimal derivation (days_between, arithmetic) against a plain
        # number compares numerically; strings never acquire number semantics.
        derived, raw = (left, right) if isinstance(left, ValueResult) else (right, left)
        if (isinstance(derived, ValueResult) and not isinstance(raw, ValueResult)
                and derived.kind in {"decimal", "day_count"} and type(raw) in {int, float}
                and predicate.op != "in"):
            x, y = Decimal(str(derived.canonical_value)), Decimal(str(raw))
            if derived is right:
                x, y = y, x
            ordering = (x > y) - (x < y)
            value = {"eq": ordering == 0, "ne": ordering != 0, "lt": ordering < 0, "lte": ordering <= 0,
                     "gt": ordering > 0, "gte": ordering >= 0}[predicate.op]
            return PredicateResult(value, "predicate_decided", paths)
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


# ``labeled_value``: label -> stated values, within one segment of a line.
_SEGMENT_STOP = re.compile(r"[;|\t\u2022]|[.!?](?=\s+[A-Z]|\s*$)")
_LABEL_CONNECTOR = re.compile(
    r"\.?\s*(?:['\u2019]s\b)?\s*(?:(?:[:=(\-\u2013\u2014]|\bis\b|\bwas\b|\bare\b|\bwere\b|\bof\b|\bat\b"
    r"|\bequals\b|\btotal(?:s|ed|ing)?\b)\s*){0,3}", re.IGNORECASE)
_LABEL_TRAILER = re.compile(r"\s*(?:[:\-\u2013\u2014]|\bin\b|\bof\b|\bfor\b)?\s*", re.IGNORECASE)
_RESULT_SIGN = re.compile(r"=|\u2192|->")
_SEGMENT_OPENER = re.compile(r"\s*(?:[-*\u2022]|\d{1,3}[.)])?\s*")
_VALUE_JOIN = re.compile(
    r"\s*(?:,|-|\u2013|\u2014|/|~|\bto\b|\bor\b|\band\b|\bthrough\b|\bthru\b|\bvs\.?|\bversus\b)?\s*"
    r"|\s*\(\s*(?:or|to|~|/|-|\u2013|vs\.?|versus)\s*", re.IGNORECASE)


def _label_spans(line: str, label: tuple[str, ...], longer: tuple[tuple[str, ...], ...]) -> list[tuple[int, int]]:
    """Character spans of the label's split words, not covered by a longer name."""
    tokens = [(match.group(0).casefold(), match.start(), match.end())
              for match in _SPLIT_TOKEN.finditer(line.translate(_INVISIBLE))]
    words = [token for token, _, _ in tokens]
    covered = set()
    for other in longer:
        for start in range(len(words) - len(other) + 1):
            if tuple(words[start:start + len(other)]) == other:
                covered.update(range(start, start + len(other)))
    size = len(label)
    return [(tokens[start][1], tokens[start + size - 1][2]) for start in range(len(words) - size + 1)
            if tuple(words[start:start + size]) == label and not set(range(start, start + size)) <= covered]


def _stated_numbers(line: str, lo: int, hi: int) -> list:
    """Number tokens inside [lo, hi), without percents and years."""
    found = []
    for match in _NUMBER.finditer(line, lo, hi):
        if match.end() > hi:
            continue
        if _number_kind(line, match) not in {"percent", "year"}:
            found.append(match)
    return found


def _run(line: str, numbers: list, index: int, step: int) -> list:
    run = [numbers[index]]
    while 0 <= index + step < len(numbers):
        left, right = (numbers[index], numbers[index + step]) if step > 0 else (numbers[index + step], numbers[index])
        if not _VALUE_JOIN.fullmatch(line[left.end():right.start()]):
            break
        index += step
        run.append(numbers[index])
    return run


def _label_values(line: str, span: tuple[int, int]):
    """(stated number matches | None if undecidable, possible) for one label occurrence."""
    start, end = span
    stops = list(_SEGMENT_STOP.finditer(line))
    lo = max((stop.end() for stop in stops if stop.end() <= start), default=0)
    hi = min((stop.start() for stop in stops if stop.start() >= end), default=len(line))
    numbers = _stated_numbers(line, lo, hi)
    after = [index for index, match in enumerate(numbers) if match.start() >= end]
    before = [index for index, match in enumerate(numbers) if match.end() <= start]
    result = list(_RESULT_SIGN.finditer(line, end, hi))
    if result:
        # "<label>: <calculation> = <values>": the values after the last sign.
        sign = result[-1].end()
        tail = [index for index in after if numbers[index].start() >= sign]
        if tail and not line[sign:numbers[tail[0]].start()].strip():
            return _run(line, numbers, tail[0], 1), False
        return [], bool(after)
    if after and _LABEL_CONNECTOR.fullmatch(line[end:numbers[after[0]].start()]):
        return _run(line, numbers, after[0], 1), False
    if before and _LABEL_TRAILER.fullmatch(line[numbers[before[-1]].end():start]):
        run = _run(line, numbers, before[-1], -1)
        if _SEGMENT_OPENER.fullmatch(line[lo:run[-1].start()]):
            return run, False
    return [], bool(after)


def _stated_equal(term: _Term, line: str, match) -> bool | None:
    suffix = match.group(1)
    body = match.group(0)[:-1] if suffix else match.group(0)
    try:
        value = _decimal(body, term.format)
    except _Unavailable:
        try:  # e.g. a bare "100" under usd_marked: a value, read loosely
            value = _decimal(body, "usd_string")
        except _Unavailable:
            return None
    return _magnitude(value, suffix, body, term.expected) if suffix else _equal_amount(term, value, body)


def _labeled_value(predicate: LabeledValue, context: Mapping) -> PredicateResult:
    text_known, text, paths = resolve_operand(predicate.text, context)
    label_known, label, label_paths = resolve_operand(predicate.label, context)
    paths = tuple(dict.fromkeys(paths + label_paths))
    longer = []
    for item in predicate.excluding:
        known, other, refs = (True, item, ()) if isinstance(item, str) else resolve_operand(item, context)
        paths = tuple(dict.fromkeys(paths + refs))
        if not known or type(other) is not str:
            return PredicateResult(None, "predicate_labeled_value_excluding_unavailable", paths)
        longer.append(tuple(_tokens(other, split=True)))
    entity = target = None
    for spec, name in ((predicate.entity, "entity"), (
            MentionTerm(value=predicate.value, mode="amount", format=predicate.format, precision=predicate.precision)
            if predicate.value is not None else None, "value")):
        if spec is None:
            continue
        term, reason, refs = _prepare(spec, context)
        paths = tuple(dict.fromkeys(paths + refs))
        if not isinstance(term, _Term):
            return PredicateResult(None, reason, paths)
        entity, target = (term, target) if name == "entity" else (entity, term)
    if not text_known or not label_known or type(label) is not str or not _tokens(label, split=True):
        return PredicateResult(None, "predicate_field_unavailable", paths)
    if len(text) > _LINE_TEXT_BUDGET:
        return PredicateResult(None, "predicate_mentions_text_budget_exceeded", paths)
    words = tuple(_tokens(label, split=True))
    longer = tuple(item for item in longer if len(item) > len(words))
    verdicts = []
    for unit in _units(text, predicate.scope):
        present = _presence(entity, unit) if entity is not None else True
        if present is False:
            continue
        for line, readable in unit:
            for span in _label_spans(line, words, longer):
                stated, possible = _label_values(line, span)
                if not stated:
                    verdict = None if possible else "none"
                elif target is None:
                    verdict = True
                else:
                    checks = [_stated_equal(target, line, match) for match in stated]
                    verdict = False if False in checks else None if None in checks else True
                if verdict == "none":
                    continue
                verdicts.append(verdict if readable and present is True else None)
    if target is None:
        value = True if True in verdicts else None if None in verdicts else False
    else:
        value = False if False in verdicts else None if None in verdicts else bool(verdicts)
    reason = ("predicate_decided" if value is not None else "predicate_labeled_value_undecidable")
    return PredicateResult(value, reason, paths)


_TOKEN = re.compile(r"\w+(?:['\u2019-]\w+)*")
_SPLIT_TOKEN = re.compile(r"\w+")
# A standalone number: not part of a word, clock time (11:30), reference or date
# (PMT-2026-0402, 2026-02-01) or fraction-like code (1/2). Digit groups end in
# a digit, so a trailing list comma ("$8,420, no") is punctuation. An adjacent
# k/m/b magnitude suffix is captured (see ``_magnitude``).
# A per-period unit after "/" ("$89/mo", "$1,200/year") does not hide the amount.
_PERIOD_UNITS = r"(?:mo|mos|month|months|yr|yrs|year|years|wk|week|day|hr|hour|qtr|quarter|annum)"
_NUMBER = re.compile(
    # Start: not glued to a word/number, except a dollar amount right after
    # "<digit>-" or "<digit>/" (the second end of "$2,790.00-$3,267.00").
    r"(?:(?<![\w.,$:/-])(?<!\w-)|(?<=\d[-/])(?=\$))"
    r"-?\$?\d(?:[\d,]*\d)?(?:\.\d+)?([kKmMbB])?"
    # End: a colon followed by whitespace/end is punctuation; an attached
    # clock/code suffix remains excluded. "/" only before a period unit or
    # another dollar amount ("$89/$99").
    r"(?!\w)(?!:\S)(?!/(?!\$|" + _PERIOD_UNITS + r"\b))(?!-\d)(?![.,]\d)",
    re.IGNORECASE,
)
_PERIOD_SUFFIX = re.compile(r"(?:\s*/\s*|\s+per\s+)" + _PERIOD_UNITS + r"\.?$", re.IGNORECASE)
_MAGNITUDE_TARGET = re.compile(r"(-?\$?\d(?:[\d,]*\d)?(?:\.\d+)?)([kKmMbB])")
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


_CLOCK_12_TEXT = re.compile(r"(?<![\w:])(\d{1,2})(?::([0-5]\d)(?::00)?)?\s*([ap])\.?\s*m\.?(?![a-z])", re.IGNORECASE)
_CLOCK_24_TEXT = re.compile(r"(?<![\w:])(0\d|1[3-9]|2[0-3]):([0-5]\d)(?::00(?:\.0+)?)?(?![\w:])(?!-\w)(?!\s*[ap]\.?\s*m\.?(?![a-z]))", re.IGNORECASE)
_CLOCK_BARE_TEXT = re.compile(r"(?<![\w:])([1-9]|1[0-2]):([0-5]\d)(?::00(?:\.0+)?)?(?![\w:])(?!-\w)(?!\s*[ap]\.?\s*m\.?(?![a-z]))", re.IGNORECASE)
# "1:00–1:15 PM" / "10-10:30am": a trailing meridiem applies to both ends.
_CLOCK_RANGE_TEXT = re.compile(
    r"(?<![\w:])(\d{1,2})(?::([0-5]\d))?\s*(?:-|\u2013|\u2014|to)\s*(\d{1,2})(?::([0-5]\d))?\s*([ap])\.?\s*m\.?(?![a-z])",
    re.IGNORECASE,
)
# "13:00-13:30" / "9:00-17:00": a range with one unambiguous 24-hour end is 24-hour.
_CLOCK_RANGE_24_TEXT = re.compile(
    r"(?<![\w:])([01]?\d|2[0-3]):([0-5]\d)\s*(?:-|\u2013|\u2014|to)\s*([01]?\d|2[0-3]):([0-5]\d)(?![\w:])"
    r"(?!\s*[ap]\.?\s*m\.?(?![a-z]))",
    re.IGNORECASE,
)
# ISO timestamps are 24-hour as written: "2026-02-10T14:00:00Z", "2026-02-10 14:00:00+00:00".
_CLOCK_ISO_TEXT = re.compile(
    r"(?<=\d{4}-\d{2}-\d{2}[T ])([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?(?![\w:])",
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
    precision: DecimalPrecision | None = None


def _target_amount(value, format):
    """A mention target amount and the text it was read from.

    Beyond the strict format, a target may carry a per-period suffix
    ("$299/mo", "$89 per month": the amount is 299/89 and the suffix is
    dropped from the reformatting comparison) or an exact magnitude suffix
    ("$4.2M" = 4200000; ``k`` always, ``m``/``b`` only dollar-marked).
    """
    try:
        return _decimal(value, format), value
    except _Unavailable:
        if type(value) is not str or len(value) > 256:
            raise
    text = value.strip()
    core = _PERIOD_SUFFIX.sub("", text)
    magnitude = _MAGNITUDE_TARGET.fullmatch(core)
    if magnitude is not None:
        body, suffix = magnitude.groups()
        if suffix not in "kK" and "$" not in body:
            raise _Unavailable("value_decimal_format_unavailable")
        return _decimal(body, format) * _MAGNITUDE[suffix.lower()], core
    if core == text:
        raise _Unavailable("value_decimal_format_unavailable")
    return _decimal(core, format), core


def _prepare(term: MentionTerm, context: Mapping):
    """Return (_Term | None, reason, paths); None means the term is unknown."""
    if term.mode == "date":
        return _prepare_date(term, context)
    if term.precision is not None:
        return _prepare_precise(term, context)
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
                if term.mode == "clock_time":
                    expected = clock_minutes(value)
                else:
                    expected, source_text = _target_amount(value, term.format)
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
        if term.mode == "verbatim" else
        re.compile(r"(?<![\w$])(?<!\d[.,])" + re.escape(literal) + r"(?=\w)")
        if term.mode == "prefix" else None
    )
    return _Term(term.mode, term.format, literal, expected, target,
                 tuple(_tokens(literal, split=True)) if term.mode == "words" else (),
                 tuple(longer), tuple(split_longer), pattern, term.sole), "prepared", paths


def _prepare_precise(term: MentionTerm, context: Mapping):
    """An ``amount`` term whose target is the exact (possibly repeating) derivation."""
    assert isinstance(term.value, DerivedValue)
    expected, reason, paths = evaluate_exact_decimal(term.value.expression, context)
    if expected is None:
        return None, reason, paths
    return _Term(term.mode, term.format, "", expected, (), (), (), (), None, term.sole, term.precision), "prepared", paths


def _equal_amount(term: _Term, value: Fraction, body: str) -> bool:
    """Exact equality, or a declared rounding of an exact derivation at the written places."""
    if value == term.expected:
        return True
    precision = term.precision
    if precision is None or term.expected is None:
        return False
    places = len(body.partition(".")[2])
    if places < precision.min_places or (precision.max_places is not None and places > precision.max_places):
        return False
    ties = ("half_up", "half_even") if precision.ties == "either" else (precision.ties,)
    return any(value == round_places(term.expected, places, mode) for mode in ties)


def _term_in_line(term: _Term | _DateTerm, line: str) -> bool | None:
    if isinstance(term, _DateTerm):
        return _date_in_line(term, line)
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
        equal = _magnitude(value, suffix, body, term.expected) if suffix else _equal_amount(term, value, body)
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
    for m in _CLOCK_ISO_TEXT.finditer(line):
        times.append(Fraction(int(m.group(1)) * 60 + int(m.group(2))) + Fraction(int(m.group(3) or 0), 60))
        rest = rest.replace(m.group(0), " ")
    for m in _CLOCK_RANGE_TEXT.finditer(rest):
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
        values.append(_magnitude(value, suffix, body, term.expected) if suffix else _equal_amount(term, value, body))
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
    if predicate.within is not None:
        return _mentions_dates_within(predicate, predicate.within, context)
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


# Calendar-date mentions (``mode: "date"``).
#
# Each line yields "facts"; a fact is a tuple of alternative readings of one
# token (any one may be the writer's meaning):
#   ("date", d)               an explicit calendar date
#   ("span", lo, hi)          the interior of a stated range (endpoints are facts too)
#   ("month", first, last)    a month with a year but no day ("March 2026")
#   ("md", month, day, wd)    a year-less month/day when no ``assume_year`` is declared
#   ("dom", day)              a bare ordinal day ("on the 5th")
#   ("weekday", wd)           a bare or relative weekday ("Friday", "next Friday")
#   ("any",)                  undecidable: relative words, contradictory weekday, invalid date
#   ("none",)                 the token may not be a date at all
# Rules: ISO and year-first numerics are exact. ``a/b/YYYY`` (also ``.``/``-``)
# reads month-first and day-first, so both readings stay possible unless one
# is invalid, they coincide, or a stated weekday picks one. A weekday prefix
# must agree with the date. Days listed after a month ("Feb 3, 10 and 17") may
# be dates or plain numbers. Year-less forms ("March 5", "3/5") take
# ``assume_year``; without it they can be ruled out by month/day or weekday but
# never confirmed. A range ("March 5–7", "Mar 5 - Mar 7, 2026", "between March
# 5 and 7") states its two endpoints; interior days are covered but not
# stated, so they are unknown for a value and ignored for ``within`` (the
# endpoints decide).
_DATE_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
               r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_DATE_WEEKDAY = (r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?"
                 r"|sat(?:urday)?|sun(?:day)?)")
_DATE_SEP = r"\s*(?:-|\u2013|\u2014|to|through|thru|until|till)\s*"
_DATE_DAY_END = r"(?:st|nd|rd|th)?(?![\w:/])(?!\.\d)(?!\s*[ap]\.?m\b)"
_DATE_MONTH_FIRST = re.compile(
    rf"(?<!\w)(?:(?P<wd>{_DATE_WEEKDAY})\.?,?\s+(?:the\s+)?)?(?P<m1>{_DATE_MONTH})\.?\s+(?P<d1>\d{{1,2}}){_DATE_DAY_END}"
    rf"(?:{_DATE_SEP}(?:(?P<wd2>{_DATE_WEEKDAY})\.?,?\s+)?(?:(?P<m2>{_DATE_MONTH})\.?\s+)?(?P<d2>\d{{1,2}}){_DATE_DAY_END}"
    rf"|(?P<more>(?:\s*(?:,\s*(?:and|or|&)?|and|or|&)\s*\d{{1,2}}{_DATE_DAY_END})+))?"
    rf"(?:,?\s+(?P<y>\d{{4}})(?![\w:/]))?", re.IGNORECASE)
_DATE_DAY_FIRST = re.compile(
    rf"(?<![\w:/.$-])(?:(?P<wd>{_DATE_WEEKDAY})\.?,?\s+(?:the\s+)?)?(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:{_DATE_SEP}(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?)?\s+(?:of\s+)?(?P<m1>{_DATE_MONTH})\.?"
    rf"(?:,?\s+(?P<y>\d{{4}}))?(?![\w:/])", re.IGNORECASE)
_DATE_ISO = re.compile(
    rf"(?<![\w/.$-])(?:(?P<wd>{_DATE_WEEKDAY})\.?,?\s+)?(?P<y>\d{{4}})(?P<s>[-/])(?P<a>\d{{1,2}})(?P=s)(?P<b>\d{{1,2}})"
    r"(?![\d/])(?![-.]\d)", re.IGNORECASE)
_DATE_NUMERIC = re.compile(
    rf"(?<![\w/.$:-])(?:(?P<wd>{_DATE_WEEKDAY})\.?,?\s+)?(?P<a>\d{{1,2}})(?:(?P<s>[.-])|/)(?P<b>\d{{1,2}})"
    r"(?(s)(?P=s)(?P<y4>\d{4})|/(?P<y>\d{4}|\d{2}))(?![\w/])(?![-.:]\d)", re.IGNORECASE)
_DATE_SLASH_YEARLESS = re.compile(
    rf"(?<![\w/.$:])(?:(?P<wd>{_DATE_WEEKDAY})\.?,?\s+)?(?P<a>\d{{1,2}})/(?P<b>\d{{1,2}})(?![\w/])(?![.,]\d)",
    re.IGNORECASE)
_DATE_MONTH_YEAR = re.compile(rf"(?<!\w)(?P<m1>{_DATE_MONTH})\.?,?\s+(?P<y>\d{{4}})(?![\w:/])", re.IGNORECASE)
_DATE_ORDINAL = re.compile(
    r"\b(?:on|by|until|till|before|after|from|through|the)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)
_DATE_RELATIVE = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|eod|eow|eom)\b"
    r"|\b(?:next|this|last|coming)\s+(?:week(?:end)?|month)\b"
    r"|\bend\s+of\s+(?:the\s+)?(?:day|week|month)\b"
    r"|\bin\s+(?:\d+|a|one|two|three|four|five|six|seven|ten)\s+(?:business\s+|working\s+|calendar\s+)?(?:days?|weeks?)\b",
    re.IGNORECASE)
_DATE_BARE_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.IGNORECASE)
_DATE_BETWEEN = re.compile(r"\bbetween\s+$", re.IGNORECASE)
_DATE_RANGE_JOIN = re.compile(r"\s*(?:-|\u2013|\u2014|to|through|thru|until|till)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class _DateTerm:
    mode: str
    day: date
    assume_year: int | None
    sole: bool = False  # sole applies to amounts and clock times only


def _iso_day(value) -> date | None:
    """An ISO date from a typed calendar_date derivation or a canonical ISO string."""
    if isinstance(value, ValueResult):
        value = value.canonical_value if value.kind == "calendar_date" else None
    if type(value) is not str:
        return None
    try:
        found = date.fromisoformat(value)
    except ValueError:
        return None
    return found if found.isoformat() == value else None


def _prepare_date(term: MentionTerm, context: Mapping):
    known, value, paths = resolve_operand(term.value, context)
    if not known:
        return None, "predicate_field_unavailable", paths
    day = _iso_day(value)
    if day is None:
        return None, "predicate_mentions_date_value_unavailable", paths
    return _DateTerm("date", day, term.assume_year), "prepared", paths


def _weekday(name) -> int | None:
    return None if name is None else WEEKDAY_NUMBERS.get(name.lower().rstrip("."))


def _month_day(month: int, day: int, year: int | None, weekday: int | None, assume_year: int | None):
    """One reading of a month/day, resolved with the stated or assumed year."""
    year = year if year is not None else assume_year
    if year is None:
        if calendar_day(2000, month, day) is None:  # leap year admits Feb 29
            return ("any",)
        return ("md", month, day, weekday)
    found = calendar_day(year, month, day, weekday)
    return ("date", found) if found is not None else ("any",)


def _range_facts(start, end):
    """Endpoint facts plus the interior; a reversed or unresolvable range is undecidable."""
    if start[0] == "date" and end[0] == "date":
        if start[1] >= end[1]:
            return [(("any",),)]
        return [(start,), (end,), (("span", start[1], end[1]),)]
    if start[0] == "md" and end[0] == "md" and start[1:3] < end[1:3]:
        return [(start,), (end,), (("span", start[1:3], end[1:3]),)]
    return [(start,), (end,), (("any",),)]


def _verb_month(text: str) -> bool:
    # Lowercase "may"/"march" are often verbs; such a token may not be a date.
    return text in {"may", "march"}


def _date_facts(line: str, assume_year: int | None) -> list[tuple[tuple, ...]]:
    """Every date-like token on one line as alternative readings (see above)."""
    facts: list[tuple[tuple, ...]] = []
    spans: list[tuple[int, int, tuple | None]] = []  # (start, end, single resolved date)
    clean = rest = line.translate(_INVISIBLE)

    def consume(match, found):
        nonlocal rest
        facts.extend(found)
        single = found[0][0] if len(found) == 1 and len(found[0]) == 1 and found[0][0][0] == "date" else None
        spans.append((match.start(), match.end(), single))
        rest = rest[:match.start()] + " " * (match.end() - match.start()) + rest[match.end():]

    for match in list(_DATE_ISO.finditer(rest)):
        exact = calendar_day(int(match["y"]), int(match["a"]), int(match["b"]), _weekday(match["wd"]))
        consume(match, [((("date", exact) if exact else ("any",)),)])
    for match in list(_DATE_NUMERIC.finditer(rest)):
        year = int(match["y4"] or match["y"])
        year = year + 2000 if year < 100 else year
        a, b, weekday = int(match["a"]), int(match["b"]), _weekday(match["wd"])
        readings = tuple(dict.fromkeys(
            ("date", found) for found in (calendar_day(year, a, b, weekday), calendar_day(year, b, a, weekday)) if found))
        consume(match, [readings or (("any",),)])
    for pattern, month_first in ((_DATE_MONTH_FIRST, True), (_DATE_DAY_FIRST, False)):
        for match in list(pattern.finditer(rest)):
            month1 = MONTH_NUMBERS[match["m1"].lower()]
            month2 = MONTH_NUMBERS[match["m2"].lower()] if month_first and match["m2"] else month1
            year = int(match["y"]) if match["y"] else None
            d1, d2 = int(match["d1"]), int(match["d2"]) if match["d2"] else None
            listed = re.findall(r"\d{1,2}", match["more"] or "") if month_first else []
            if len(listed) == 1 and _DATE_BETWEEN.search(clean[:match.start()]):
                d2, listed = int(listed[0]), []  # "between March 5 and 7"
            if d2 is None:
                found: list[tuple] = [(_month_day(month1, d1, year, _weekday(match["wd"]), assume_year),)]
                # "Feb 3, 10 and 17": listed days share the month; a listed number may not be a day.
                for day in listed:
                    found.append((_month_day(month1, int(day), year, None, assume_year), ("none",)))
            else:
                start_year, assumed = year, assume_year
                if (month1, d1) > (month2, d2):
                    if year is not None:
                        start_year = year - 1  # "Dec 30 – Jan 2, 2027"
                    else:
                        assumed = None  # a year-less wrap cannot take one assumed year
                found = _range_facts(
                    _month_day(month1, d1, start_year, _weekday(match["wd"]), assumed),
                    _month_day(month2, d2, year, _weekday(match["wd2"]) if month_first else None, assumed))
            if _verb_month(match["m1"]):
                found = [fact + (("none",),) for fact in found]
            consume(match, found)
    for match in list(_DATE_SLASH_YEARLESS.finditer(rest)):
        a, b, weekday = int(match["a"]), int(match["b"]), _weekday(match["wd"])
        readings = []
        for month, day in ((a, b), (b, a)):
            if 1 <= month <= 12 and calendar_day(2000, month, day) is not None:
                reading = _month_day(month, day, None, weekday, assume_year)
                if reading[0] != "any" and reading not in readings:
                    readings.append(reading)
        consume(match, [(*readings, ("none",))])  # "3/5" may be a score or fraction
    for match in list(_DATE_MONTH_YEAR.finditer(rest)):
        month, year = MONTH_NUMBERS[match["m1"].lower()], int(match["y"])
        last = calendar_day(year, month % 12 + 1, 1) if month < 12 else calendar_day(year + 1, 1, 1)
        if last is None:
            continue
        month_reading = (("month", date(year, month, 1), last - timedelta(days=1)),)
        consume(match, [month_reading + ((("none",),) if _verb_month(match["m1"]) else ())])
    for match in list(_DATE_ORDINAL.finditer(rest)):
        consume(match, [(("dom", int(match.group(1))), ("none",))])
    for match in list(_DATE_RELATIVE.finditer(rest)):
        consume(match, [(("any",),)])
    for match in list(_DATE_BARE_WEEKDAY.finditer(rest)):
        consume(match, [(("weekday", WEEKDAY_NUMBERS[match.group(1).lower()]),)])
    # "March 5, 2026 – March 7, 2026": two separately written dates joined as a range.
    spans.sort()
    for (begin, end, first), (start, _, second) in pairwise(spans):
        joined = _DATE_RANGE_JOIN.fullmatch(clean[end:start]) or (
            re.fullmatch(r"\s+and\s+", clean[end:start], re.IGNORECASE) and _DATE_BETWEEN.search(clean[:begin]))
        if first and second and first[1] < second[1] and joined:
            facts.append((("span", first[1], second[1]),))
    return facts


def _date_states(reading: tuple, day: date) -> bool | None:
    """Whether one reading states ``day``: True, False, or unknown."""
    kind = reading[0]
    if kind == "date":
        return reading[1] == day
    if kind == "span":
        key: Any = day if isinstance(reading[1], date) else (day.month, day.day)
        return None if reading[1] < key < reading[2] else False
    if kind == "md":
        return None if reading[1:3] == (day.month, day.day) and reading[3] in {None, day.weekday()} else False
    if kind == "dom":
        return None if reading[1] == day.day else False
    if kind == "weekday":
        return None if reading[1] == day.weekday() else False
    if kind in {"none", "month"}:  # a month names no day
        return False
    return None


def _date_in_line(term: _DateTerm, line: str) -> bool | None:
    verdicts = []
    for fact in _date_facts(line, term.assume_year):
        values = {_date_states(reading, term.day) for reading in fact}
        verdicts.append(True if values == {True} else False if values == {False} else None)
    return True if True in verdicts else None if None in verdicts else False


def _date_inside(reading: tuple, start: date, end: date) -> str | None:
    """"in"/"out" for a stated date, "neutral" for a non-date, None when undecidable."""
    kind = reading[0]
    if kind == "date":
        return "in" if start <= reading[1] <= end else "out"
    if kind in {"none", "span"}:
        return "neutral"
    if kind == "month":
        return "neutral" if start <= reading[1] and reading[2] <= end else None
    if kind == "md":  # outside in every year the interval touches -> certainly outside
        days = [calendar_day(year, reading[1], reading[2], reading[3]) for year in range(start.year, end.year + 1)]
        return None if any(found and start <= found <= end for found in days) else "out"
    return None


def _fact_within(fact: tuple, start: date, end: date) -> str | None:
    values = {_date_inside(reading, start, end) for reading in fact}
    if None in values:
        return None
    if len(values) == 1:
        return values.pop()
    return None if "out" in values else "soft"  # maybe a date, inside if so


def _mentions_dates_within(predicate: Mentions, within: DateWithin, context: Mapping) -> PredicateResult:
    """At least one readable stated date, and every stated date inside the interval."""
    text_known, text, paths = resolve_operand(predicate.text, context)
    bounds = []
    for operand in (within.start, within.end):
        known, value, refs = resolve_operand(operand, context)
        paths = tuple(dict.fromkeys(paths + refs))
        bounds.append(_iso_day(value) if known else None)
    if not text_known:
        return PredicateResult(None, "predicate_field_unavailable", paths)
    start, end = bounds
    if start is None or end is None or start > end:
        return PredicateResult(None, "predicate_mentions_date_interval_unavailable", paths)
    if len(text) > _LINE_TEXT_BUDGET:
        return PredicateResult(None, "predicate_mentions_text_budget_exceeded", paths)
    # uncertain: a date that might lie outside; maybe: a possible date inside
    # that is not a readable statement (quoted/fenced, or possibly not a date).
    stated = uncertain = maybe = False
    for line, readable in _readable_lines(text):
        for fact in _date_facts(line, predicate.assume_year):
            verdict = _fact_within(fact, start, end)
            if verdict == "out" and readable:
                return PredicateResult(False, "predicate_mentions_date_outside", paths)
            uncertain = uncertain or verdict is None or verdict == "out"
            stated = stated or verdict == "in" and readable
            maybe = maybe or verdict == "soft" or verdict == "in" and not readable
    if uncertain or maybe and not stated:
        return PredicateResult(None, "predicate_mentions_unreadable_or_ambiguous", paths)
    if stated:
        return PredicateResult(True, "predicate_decided", paths)
    return PredicateResult(False, "predicate_mentions_absent", paths)


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


def _items(predicate: Items, context: Mapping) -> PredicateResult:
    root = predicate.items.path
    value: Any = context
    for part in root:
        if isinstance(part, int):
            value = value[part] if isinstance(value, (list, tuple)) and part < len(value) else None
        else:
            value = value.get(part) if isinstance(value, Mapping) else None
        if value is None:
            break
    if not isinstance(value, (list, tuple)) or len(value) > predicate.max_items:
        return PredicateResult(None, "predicate_items_unavailable", (root,))
    paths: list[tuple] = [root]
    decisive = predicate.op == "all_items"  # all: a false item decides; any: a true one
    unknown = False
    for index, item in enumerate(value):
        result = _evaluate(predicate.where, {**context, "item": item})
        paths.extend((*root, index, *path[1:]) if path[:1] == ("item",) else path
                     for path in result.evidence_paths)
        if result.value is (not decisive):
            return PredicateResult(not decisive, "predicate_decided", tuple(dict.fromkeys(paths)))
        unknown = unknown or result.value is None
    return PredicateResult(None if unknown else decisive,
                           "predicate_input_unavailable" if unknown else "predicate_decided",
                           tuple(dict.fromkeys(paths)))
