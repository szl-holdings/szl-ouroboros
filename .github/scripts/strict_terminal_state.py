#!/usr/bin/env python3
"""Fail-closed extraction of an Ouroboros review terminal receipt state.

A terminal state is not an authority or a release gate. This parser only prevents
ambiguous JSON from being admitted by the workflow's separate terminal-state step.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

STATES = frozenset(("REVIEW_PROPOSED", "NO_ACTION_RECOMMENDED", "BLOCKED"))


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("AMBIGUOUS_RECEIPT")
        value[key] = item
    return value


def _no_nonfinite_constant(_constant: str) -> None:
    raise ValueError("NONSTANDARD_JSON_NUMBER")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_JSON_NUMBER")
    return number


def terminal_state(path: str) -> str:
    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_no_nonfinite_constant,
        parse_float=_finite_float,
    )
    if type(data) is not dict or type(data.get("state")) is not str:
        raise ValueError("INVALID_TERMINAL_STATE")
    state = data["state"]
    if state not in STATES:
        raise ValueError("INVALID_TERMINAL_STATE")
    return state


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("INVALID_TERMINAL_RECEIPT", file=sys.stderr)
        return 2
    try:
        state = terminal_state(argv[1])
    except (OSError, ValueError, UnicodeError, TypeError, OverflowError):
        print("INVALID_TERMINAL_RECEIPT", file=sys.stderr)
        return 2
    sys.stdout.write(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
