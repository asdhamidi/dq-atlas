import pytest

from core.evaluation import compute_fail_pct, evaluate_pass_fail


class TestComputeFailPct:
    def test_normal_ratio(self):
        assert compute_fail_pct(200, 50) == 25.0

    def test_zero_total_returns_zero(self):
        assert compute_fail_pct(0, 0) == 0.0

    def test_none_total_returns_zero(self):
        assert compute_fail_pct(None, None) == 0.0

    def test_rounds_to_four_decimal_places(self):
        assert compute_fail_pct(3, 1) == round(100 / 3, 4)


class TestEvaluatePassFail:
    def test_none_failed_rows_is_unresolvable(self):
        assert evaluate_pass_fail("COUNT", 0, None, None) is None

    @pytest.mark.parametrize(
        "failed_rows, threshold, expected",
        [
            (0, 0, "PASS"),  # at threshold is a pass
            (1, 0, "FAIL"),
            (5, 5, "PASS"),
            (6, 5, "FAIL"),
        ],
    )
    def test_count_threshold_compares_failed_rows_directly(self, failed_rows, threshold, expected):
        assert evaluate_pass_fail("COUNT", threshold, failed_rows, fail_pct=None) == expected

    @pytest.mark.parametrize(
        "fail_pct, threshold, expected",
        [
            (0.0, 1.0, "PASS"),
            (1.0, 1.0, "PASS"),
            (1.01, 1.0, "FAIL"),
        ],
    )
    def test_percent_threshold_compares_fail_pct(self, fail_pct, threshold, expected):
        assert evaluate_pass_fail("PERCENT", threshold, failed_rows=1, fail_pct=fail_pct) == expected

    def test_percent_threshold_treats_missing_fail_pct_as_zero(self):
        assert evaluate_pass_fail("PERCENT", 0, failed_rows=0, fail_pct=None) == "PASS"
