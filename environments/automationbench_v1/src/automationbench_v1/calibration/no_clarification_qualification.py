"""Bounded no-clarification qualification; imports never dispatch inference."""

from .summary_qualification import (
    SummaryQualificationSelection,
    _main,
    _profile,
    run_no_clarification_qualification,
)

__all__ = ["SummaryQualificationSelection", "run_no_clarification_qualification"]


def main():
    _main(_profile("no_clarification@1"))


if __name__ == "__main__":
    main()
