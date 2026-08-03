"""Deterministic IFEval instruction checkers.

The algorithms are a small, typed port of Google's Apache-2.0 IFEval reference
at commit ``e6890f85757dd84e27ca6df2dd30651dafad28e0``.  They intentionally do
not import the reference package or perform network/model judging.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any

import langdetect

Comparison = str
Checker = Callable[[str, Mapping[str, Any]], bool]

RELATIONS = ("less than", "at least")
CONSTRAINED_RESPONSES = ("My answer is yes.", "My answer is no.", "My answer is maybe.")
SUPPORTED_INSTRUCTION_IDS = (
    "change_case:capital_word_frequency",
    "change_case:english_capital",
    "change_case:english_lowercase",
    "combination:repeat_prompt",
    "combination:two_responses",
    "detectable_content:number_placeholders",
    "detectable_content:postscript",
    "detectable_format:constrained_response",
    "detectable_format:json_format",
    "detectable_format:multiple_sections",
    "detectable_format:number_bullet_lists",
    "detectable_format:number_highlighted_sections",
    "detectable_format:title",
    "keywords:existence",
    "keywords:forbidden_words",
    "keywords:frequency",
    "keywords:letter_frequency",
    "language:response_language",
    "length_constraints:nth_paragraph_first_word",
    "length_constraints:number_paragraphs",
    "length_constraints:number_sentences",
    "length_constraints:number_words",
    "punctuation:no_comma",
    "startend:end_checker",
    "startend:quotation",
)


def _relation(kwargs: Mapping[str, Any], key: str = "relation") -> Comparison:
    value = kwargs.get(key)
    if value not in RELATIONS:
        raise ValueError(f"{key} must be one of {RELATIONS}, got {value!r}")
    return str(value)


def _count_sentences(text: str) -> int:
    """Match Google's lightweight sentence splitter without NLTK data files."""

    text = f" {text}  ".replace("\n", " ")
    text = re.sub(r"(Mr|St|Mrs|Ms|Dr)\.", r"\1<prd>", text)
    text = re.sub(r"\.(com|net|org|io|gov|edu|me)", r"<prd>\1", text)
    text = re.sub(r"([0-9])\.([0-9])", r"\1<prd>\2", text)
    text = re.sub(r"\.{2,}", lambda match: "<prd>" * len(match.group()) + "<stop>", text)
    text = text.replace("Ph.D.", "Ph<prd>D<prd>")
    text = re.sub(r"\s([A-Za-z])\. ", r" \1<prd> ", text)
    text = text.replace('".', '".').replace(".”", "”.").replace('!"', '"!').replace('?"', '"?')
    text = text.replace(".", ".<stop>").replace("?", "?<stop>").replace("!", "!<stop>")
    text = text.replace("<prd>", ".")
    sentences = [part.strip() for part in text.split("<stop>")]
    return len([part for part in sentences if part])


def _count_words(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _split_sentences(text: str) -> list[str]:
    # IFEval's key-sentence instruction is not in the pinned registry; this
    # helper is retained for parity-friendly paragraph handling.
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _language(text: str, expected: str) -> bool:
    try:
        return langdetect.detect(text) == expected
    except langdetect.LangDetectException:
        # This is the reference's fail-open behavior for undetectable text.
        return True


def _number_sentences(response: str, kwargs: Mapping[str, Any]) -> bool:
    threshold = int(kwargs["num_sentences"])
    count = _count_sentences(response)
    return count < threshold if _relation(kwargs) == RELATIONS[0] else count >= threshold


def _number_words(response: str, kwargs: Mapping[str, Any]) -> bool:
    threshold = int(kwargs["num_words"])
    count = _count_words(response)
    return count < threshold if _relation(kwargs) == RELATIONS[0] else count >= threshold


def _number_paragraphs(response: str, kwargs: Mapping[str, Any]) -> bool:
    paragraphs = re.split(r"\s?\*\*\*\s?", response)
    count = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        if not paragraph.strip():
            if index in (0, len(paragraphs) - 1):
                count -= 1
            else:
                return False
    return count == int(kwargs["num_paragraphs"])


def _nth_paragraph_first_word(response: str, kwargs: Mapping[str, Any]) -> bool:
    paragraphs = response.split("\n\n")
    count = sum(bool(paragraph.strip()) for paragraph in paragraphs)
    nth = int(kwargs["nth_paragraph"])
    if nth > count or nth <= 0:
        return False
    paragraph = paragraphs[nth - 1].strip()
    if not paragraph:
        return False
    word = paragraph.split()[0].lstrip("'").lstrip('"')
    first_word = ""
    for letter in word:
        if letter in {".", ",", "?", "!", "'", '"'}:
            break
        first_word += letter.lower()
    return (
        count == int(kwargs["num_paragraphs"]) and first_word == str(kwargs["first_word"]).lower()
    )


def _postscript(response: str, kwargs: Mapping[str, Any]) -> bool:
    marker = str(kwargs["postscript_marker"])
    lowered = response.lower()
    if marker == "P.P.S":
        pattern = r"\s*p\.\s?p\.\s?s.*$"
    elif marker == "P.S.":
        pattern = r"\s*p\.\s?s\..*$"
    else:
        pattern = rf"\s*{re.escape(marker.lower())}.*$"
    return bool(re.findall(pattern, lowered, flags=re.MULTILINE))


def _number_bullets(response: str, kwargs: Mapping[str, Any]) -> bool:
    bullets = re.findall(r"^\s*\*[^\*].*$", response, flags=re.MULTILINE)
    bullets += re.findall(r"^\s*-.*$", response, flags=re.MULTILINE)
    return len(bullets) == int(kwargs["num_bullets"])


def _highlighted(response: str, kwargs: Mapping[str, Any]) -> bool:
    count = sum(bool(item.strip("*").strip()) for item in re.findall(r"\*[^\n\*]*\*", response))
    count += sum(
        bool(item.removeprefix("**").removesuffix("**").strip())
        for item in re.findall(r"\*\*[^\n\*]*\*\*", response)
    )
    return count >= int(kwargs["num_highlights"])


def _multiple_sections(response: str, kwargs: Mapping[str, Any]) -> bool:
    splitter = re.escape(str(kwargs["section_spliter"]))
    sections = re.split(rf"\s?{splitter}\s?\d+\s?", response)
    return len(sections) - 1 >= int(kwargs["num_sections"])


def _json_format(response: str, _: Mapping[str, Any]) -> bool:
    value = (
        response.strip()
        .removeprefix("```json")
        .removeprefix("```Json")
        .removeprefix("```JSON")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True


def _keyword_existence(response: str, kwargs: Mapping[str, Any]) -> bool:
    return all(
        re.search(str(keyword), response, flags=re.IGNORECASE) for keyword in kwargs["keywords"]
    )


def _keyword_frequency(response: str, kwargs: Mapping[str, Any]) -> bool:
    count = len(re.findall(str(kwargs["keyword"]), response, flags=re.IGNORECASE))
    threshold = int(kwargs["frequency"])
    return count < threshold if _relation(kwargs) == RELATIONS[0] else count >= threshold


def _forbidden_words(response: str, kwargs: Mapping[str, Any]) -> bool:
    return not any(
        re.search(rf"\b{word}\b", response, flags=re.IGNORECASE)
        for word in kwargs["forbidden_words"]
    )


def _letter_frequency(response: str, kwargs: Mapping[str, Any]) -> bool:
    letter = str(kwargs["letter"]).lower()
    count = Counter(response.lower())[letter]
    threshold = int(kwargs["let_frequency"])
    return (
        count < threshold
        if _relation(kwargs, "let_relation") == RELATIONS[0]
        else count >= threshold
    )


def _capital_word_frequency(response: str, kwargs: Mapping[str, Any]) -> bool:
    count = sum(word.isupper() for word in re.findall(r"\w+", response, flags=re.UNICODE))
    threshold = int(kwargs["capital_frequency"])
    return (
        count < threshold
        if _relation(kwargs, "capital_relation") == RELATIONS[0]
        else count >= threshold
    )


def _constrained_response(response: str, _: Mapping[str, Any]) -> bool:
    value = response.strip()
    return any(option in value for option in CONSTRAINED_RESPONSES)


def _two_responses(response: str, _: Mapping[str, Any]) -> bool:
    valid = []
    pieces = response.split("******")
    for index, piece in enumerate(pieces):
        if not piece.strip():
            if index not in (0, len(pieces) - 1):
                return False
        else:
            valid.append(piece)
    return len(valid) == 2 and valid[0].strip() != valid[1].strip()


def _repeat_prompt(response: str, kwargs: Mapping[str, Any]) -> bool:
    return response.strip().lower().startswith(str(kwargs["prompt_to_repeat"]).strip().lower())


def _end(response: str, kwargs: Mapping[str, Any]) -> bool:
    return response.strip().strip('"').lower().endswith(str(kwargs["end_phrase"]).strip().lower())


def _title(response: str, _: Mapping[str, Any]) -> bool:
    return any(item.lstrip("<").rstrip(">").strip() for item in re.findall(r"<<[^\n]+>>", response))


def _response_language(response: str, kwargs: Mapping[str, Any]) -> bool:
    return _language(response, str(kwargs["language"]))


def _english_capital(response: str, _: Mapping[str, Any]) -> bool:
    return response.isupper() and _language(response, "en")


def _english_lowercase(response: str, _: Mapping[str, Any]) -> bool:
    return response.islower() and _language(response, "en")


def _no_comma(response: str, _: Mapping[str, Any]) -> bool:
    return not re.search(r",", response)


CHECKERS: dict[str, Checker] = {
    "change_case:capital_word_frequency": _capital_word_frequency,
    "change_case:english_capital": _english_capital,
    "change_case:english_lowercase": _english_lowercase,
    "combination:repeat_prompt": _repeat_prompt,
    "combination:two_responses": _two_responses,
    "detectable_content:number_placeholders": lambda r, k: (
        len(re.findall(r"\[.*?\]", r)) >= int(k["num_placeholders"])
    ),
    "detectable_content:postscript": _postscript,
    "detectable_format:constrained_response": _constrained_response,
    "detectable_format:json_format": _json_format,
    "detectable_format:multiple_sections": _multiple_sections,
    "detectable_format:number_bullet_lists": _number_bullets,
    "detectable_format:number_highlighted_sections": _highlighted,
    "detectable_format:title": _title,
    "keywords:existence": _keyword_existence,
    "keywords:forbidden_words": _forbidden_words,
    "keywords:frequency": _keyword_frequency,
    "keywords:letter_frequency": _letter_frequency,
    "language:response_language": _response_language,
    "length_constraints:nth_paragraph_first_word": _nth_paragraph_first_word,
    "length_constraints:number_paragraphs": _number_paragraphs,
    "length_constraints:number_sentences": _number_sentences,
    "length_constraints:number_words": _number_words,
    "punctuation:no_comma": _no_comma,
    "startend:end_checker": _end,
    "startend:quotation": lambda r, _: (
        len(r.strip()) > 1 and r.strip()[0] == '"' and r.strip()[-1] == '"'
    ),
}

if tuple(sorted(CHECKERS)) != tuple(sorted(SUPPORTED_INSTRUCTION_IDS)):
    raise RuntimeError("IFEval checker registry is incomplete")


def check_instruction(instruction_id: str, response: str, kwargs: Mapping[str, Any]) -> bool:
    try:
        checker = CHECKERS[instruction_id]
    except KeyError as error:
        raise ValueError(f"unsupported IFEval instruction: {instruction_id}") from error
    return bool(checker(response, kwargs))


def loose_responses(response: str) -> tuple[str, ...]:
    """Return the eight deterministic variants from Google's loose evaluator."""

    lines = response.split("\n")
    remove_first = "\n".join(lines[1:]).strip()
    remove_last = "\n".join(lines[:-1]).strip()
    remove_both = "\n".join(lines[1:-1]).strip()
    no_stars = response.replace("*", "")
    no_stars_first = remove_first.replace("*", "")
    no_stars_last = remove_last.replace("*", "")
    no_stars_both = remove_both.replace("*", "")
    return (
        response,
        no_stars,
        remove_first,
        remove_last,
        remove_both,
        no_stars_first,
        no_stars_last,
        no_stars_both,
    )


__all__ = [
    "CHECKERS",
    "SUPPORTED_INSTRUCTION_IDS",
    "check_instruction",
    "loose_responses",
]
