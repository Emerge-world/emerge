from argparse import ArgumentTypeError
from itertools import islice

import pytest

from simulation.tick_limits import (
    format_tick_limit,
    iter_tick_numbers,
    parse_tick_limit_arg,
    validate_tick_limit_value,
)


def test_parse_tick_limit_arg_accepts_infinite_literal():
    assert parse_tick_limit_arg("infinite") is None


def test_parse_tick_limit_arg_accepts_positive_integer():
    assert parse_tick_limit_arg("25") == 25


@pytest.mark.parametrize("raw", ["0", "-3", "forever"])
def test_parse_tick_limit_arg_rejects_invalid_values(raw):
    with pytest.raises(ArgumentTypeError):
        parse_tick_limit_arg(raw)


def test_validate_tick_limit_value_accepts_yaml_infinite_string():
    assert validate_tick_limit_value("infinite") is None


@pytest.mark.parametrize("raw", [0, -1, "forever"])
def test_validate_tick_limit_value_rejects_invalid_config_values(raw):
    with pytest.raises(ValueError):
        validate_tick_limit_value(raw)


def test_format_tick_limit_renders_none_as_infinite():
    assert format_tick_limit(None) == "infinite"


def test_iter_tick_numbers_is_unbounded_for_none():
    assert list(islice(iter_tick_numbers(None), 3)) == [1, 2, 3]


def test_iter_tick_numbers_is_bounded_for_positive_integer():
    assert list(iter_tick_numbers(3)) == [1, 2, 3]
