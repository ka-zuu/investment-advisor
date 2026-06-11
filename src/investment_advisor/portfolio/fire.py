"""FIRE目標との差分計算（§11 §3）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date


@dataclass
class FireGap:
    target_assets: float | None       # 目標資産額（円）
    current: float                     # 現在の総資産額（円）
    progress_pct: float | None         # 進捗率（%）
    gap: float | None                  # 残り差額（円）
    target_year: int | None            # FIRE目標年
    years_left: int | None             # 残り年数
    required_cagr: float | None        # 必要CAGR（%）。入金なしの単純複利ベース
    annual_contribution: float | None  # 年間入金額（円）
    contribution_covers_pct: float | None  # 入金累計で差額をカバーできる割合（%）


def compute_fire_gap(
    policy: dict[str, str],
    current_total: float,
    today: date,
) -> FireGap | None:
    """Investment Policy DB の方針値からFIRE差分を計算する。全項目パース不能な場合はNoneを返す。"""
    target = parse_jpy_amount(policy.get("目標資産額", ""))
    target_year = parse_year(policy.get("FIRE目標年", ""))
    monthly = parse_jpy_amount(policy.get("毎月入金額", ""))

    if target is None and target_year is None and monthly is None:
        return None

    progress_pct = round(current_total / target * 100, 2) if target else None
    gap = round(target - current_total, 0) if target is not None else None
    years_left = (target_year - today.year) if target_year is not None else None
    annual_contribution = monthly * 12 if monthly is not None else None

    required_cagr: float | None = None
    if target and current_total > 0 and years_left and years_left > 0:
        required_cagr = round(((target / current_total) ** (1.0 / years_left) - 1) * 100, 2)

    contribution_covers_pct: float | None = None
    if annual_contribution is not None and gap and gap > 0 and years_left and years_left > 0:
        contribution_covers_pct = round(annual_contribution * years_left / gap * 100, 2)

    return FireGap(
        target_assets=target,
        current=current_total,
        progress_pct=progress_pct,
        gap=gap,
        target_year=target_year,
        years_left=years_left,
        required_cagr=required_cagr,
        annual_contribution=annual_contribution,
        contribution_covers_pct=contribution_covers_pct,
    )


def parse_jpy_amount(text: str) -> float | None:
    """テキストから日本円金額を抽出して float で返す。
    例: "1億2000万円" → 120_000_000, "30万" → 300_000, "1,500,000" → 1_500_000
    """
    if not text:
        return None
    # 全角→半角
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(",", "").replace("，", "").replace(" ", "").replace("　", "")

    # 億・万の組み合わせ（例: "1億2000万"）
    m_oku = re.search(r"(\d+(?:\.\d+)?)億", text)
    m_man = re.search(r"(\d+(?:\.\d+)?)万", text)
    m_raw = re.search(r"(\d+(?:\.\d+)?)", text)

    if m_oku or m_man:
        oku = float(m_oku.group(1)) if m_oku else 0.0
        man = float(m_man.group(1)) if m_man else 0.0
        return oku * 1e8 + man * 1e4

    if m_raw:
        return float(m_raw.group(1))

    return None


def parse_year(text: str) -> int | None:
    """テキストから西暦年（4桁）を抽出して返す。"""
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    m = re.search(r"(20\d{2}|19\d{2})", text)
    return int(m.group(1)) if m else None
