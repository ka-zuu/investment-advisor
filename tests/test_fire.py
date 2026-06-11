"""FIRE差分計算モジュールのテスト。"""

from datetime import date

import pytest

from investment_advisor.portfolio.fire import FireGap, compute_fire_gap, parse_jpy_amount, parse_year


class TestParseJpyAmount:
    def test_oku(self):
        assert parse_jpy_amount("1億円") == 1e8

    def test_man(self):
        assert parse_jpy_amount("500万円") == 5_000_000

    def test_oku_man_combined(self):
        assert parse_jpy_amount("1億2000万円") == 120_000_000

    def test_raw_number(self):
        assert parse_jpy_amount("3000000") == 3_000_000

    def test_comma_separated(self):
        assert parse_jpy_amount("1,500,000") == 1_500_000

    def test_fullwidth_digits(self):
        # 全角数字＋億
        result = parse_jpy_amount("２億円")
        assert result == 2e8

    def test_decimal_man(self):
        assert parse_jpy_amount("1.5億") == 1.5e8

    def test_empty(self):
        assert parse_jpy_amount("") is None

    def test_no_number(self):
        assert parse_jpy_amount("未設定") is None

    def test_monthly_contribution(self):
        assert parse_jpy_amount("30万") == 300_000


class TestParseYear:
    def test_four_digit_year(self):
        assert parse_year("2035年") == 2035

    def test_year_in_sentence(self):
        assert parse_year("FIRE目標は2040年です") == 2040

    def test_fullwidth_year(self):
        assert parse_year("２０３５年") == 2035

    def test_empty(self):
        assert parse_year("") is None

    def test_no_year(self):
        assert parse_year("未設定") is None


class TestComputeFireGap:
    def _policy(self, target="1億円", fire_year="2040年", monthly="30万円"):
        p = {}
        if target:
            p["目標資産額"] = target
        if fire_year:
            p["FIRE目標年"] = fire_year
        if monthly:
            p["毎月入金額"] = monthly
        return p

    def test_basic_gap(self):
        policy = self._policy()
        gap = compute_fire_gap(policy, 30_000_000, date(2026, 1, 1))
        assert gap is not None
        assert gap.target_assets == 1e8
        assert abs(gap.progress_pct - 30.0) < 0.01
        assert gap.gap == 70_000_000
        assert gap.years_left == 14

    def test_required_cagr_reasonable(self):
        policy = self._policy()
        gap = compute_fire_gap(policy, 30_000_000, date(2026, 1, 1))
        assert gap is not None
        assert gap.required_cagr is not None
        assert 0 < gap.required_cagr < 20  # 現実的な範囲

    def test_contribution_covers_pct(self):
        policy = self._policy()
        gap = compute_fire_gap(policy, 30_000_000, date(2026, 1, 1))
        assert gap is not None
        assert gap.contribution_covers_pct is not None
        expected = (300_000 * 12 * 14) / 70_000_000 * 100
        assert abs(gap.contribution_covers_pct - expected) < 0.1

    def test_returns_none_when_all_missing(self):
        gap = compute_fire_gap({}, 10_000_000, date(2026, 1, 1))
        assert gap is None

    def test_partial_policy(self):
        # 目標年のみ設定
        gap = compute_fire_gap({"FIRE目標年": "2035年"}, 10_000_000, date(2026, 1, 1))
        assert gap is not None
        assert gap.target_assets is None
        assert gap.progress_pct is None
        assert gap.target_year == 2035

    def test_already_reached(self):
        # 現在資産が目標を超えている
        gap = compute_fire_gap(self._policy("5000万円"), 80_000_000, date(2026, 1, 1))
        assert gap is not None
        assert gap.progress_pct is not None
        assert gap.progress_pct > 100


class TestSynthesizerToolSchema:
    def test_opinion_conflict_in_required(self):
        from investment_advisor.agents.runner import _SYNTHESIZER_TOOL
        required = _SYNTHESIZER_TOOL["input_schema"]["required"]
        assert "opinion_conflict" in required

    def test_lookback_review_in_required(self):
        from investment_advisor.agents.runner import _SYNTHESIZER_TOOL
        required = _SYNTHESIZER_TOOL["input_schema"]["required"]
        assert "lookback_review" in required

    def test_opinion_conflict_in_properties(self):
        from investment_advisor.agents.runner import _SYNTHESIZER_TOOL
        props = _SYNTHESIZER_TOOL["input_schema"]["properties"]
        assert "opinion_conflict" in props

    def test_lookback_review_in_properties(self):
        from investment_advisor.agents.runner import _SYNTHESIZER_TOOL
        props = _SYNTHESIZER_TOOL["input_schema"]["properties"]
        assert "lookback_review" in props
