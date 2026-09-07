from core.predicates import build_range_predicate


def test_both_bounds():
    pred = build_range_predicate('"COL"', 0, 100)
    assert pred == '"COL" < 0 OR "COL" > 100'


def test_lower_bound_only():
    pred = build_range_predicate('"COL"', 0, None)
    assert pred == '"COL" < 0'


def test_upper_bound_only():
    pred = build_range_predicate('"COL"', None, 100)
    assert pred == '"COL" > 100'


def test_no_bounds_is_always_false():
    # Not reachable through the registry today (RANGE is only resolved
    # when at least one bound is set), but the predicate itself must not
    # match every row if it's ever called with neither bound.
    assert build_range_predicate('"COL"', None, None) == "FALSE"
