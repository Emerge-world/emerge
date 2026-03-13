from __future__ import annotations

from argparse import ArgumentTypeError
from itertools import count
from typing import Iterator

INFINITE_TICKS_LITERAL = "infinite"


def parse_tick_limit_arg(raw: str) -> int | None:
    if raw == INFINITE_TICKS_LITERAL:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ArgumentTypeError(
            f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
        ) from exc
    if value <= 0:
        raise ArgumentTypeError(
            f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
        )
    return value


def validate_tick_limit_value(raw: object) -> int | None:
    if raw == INFINITE_TICKS_LITERAL:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    raise ValueError(
        f"ticks must be a positive integer or '{INFINITE_TICKS_LITERAL}'"
    )


def format_tick_limit(max_ticks: int | None) -> str:
    return INFINITE_TICKS_LITERAL if max_ticks is None else str(max_ticks)


def iter_tick_numbers(max_ticks: int | None) -> Iterator[int]:
    return count(1) if max_ticks is None else iter(range(1, max_ticks + 1))
