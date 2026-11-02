"""Merging two readings of one page: a second reading adds only what the first left out."""

from citetally.models import Word
from citetally.reading.merge import merge_readings


def word(text: str, x0: float, y0: float = 0.1, width: float = 0.05) -> Word:
    return Word(t=text, x0=x0, y0=y0, x1=x0 + width, y1=y0 + 0.02, c=90.0)


def test_a_word_the_first_reading_missed_is_added() -> None:
    first = [word("Qty", 0.1), word("$9.00", 0.5)]
    second = [word("Qty", 0.1), word("2", 0.3), word("$9.00", 0.5)]
    merged = merge_readings(first, [second])
    assert [w.t for w in merged] == ["Qty", "$9.00", "2"]


def test_a_word_where_the_first_reading_has_one_is_not_added_even_if_it_reads_differently() -> None:
    first = [word("Total", 0.1), word("$140.00", 0.5)]
    second = [word("Tota1", 0.1), word("$14O.00", 0.51)]
    assert [w.t for w in merge_readings(first, [second])] == ["Total", "$140.00"]


def test_the_first_reading_is_kept_whole_and_in_order() -> None:
    first = [word("a", 0.1), word("b", 0.2), word("c", 0.3)]
    assert merge_readings(first, [[]]) == first
    assert merge_readings(first, []) == first


def test_several_extra_readings_add_in_turn_and_never_twice() -> None:
    first = [word("x", 0.1)]
    second = [word("1", 0.3)]
    third = [word("1", 0.3), word("2", 0.6)]
    merged = merge_readings(first, [second, third])
    assert [w.t for w in merged] == ["x", "1", "2"]
