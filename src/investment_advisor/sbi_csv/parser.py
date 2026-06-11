"""SBI証券 保有資産CSV パーサ（§9 SBI CSV Import Specification準拠）。

仕様：
- Shift-JIS (cp932) エンコーディング
- NEL (U+0085) も改行として扱う
- 先頭メタ6行スキップ
- 複数セクション構成（口座・商品区分ごと）
- 「○○合計」「総合計」行およびその直後2行はスキップ
- 列見出し行はスキップ
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import IO

# セクション見出し→(資産クラス, 口座) マッピング（§9.2）
SECTION_MAP: dict[str, tuple[str, str]] = {
    "株式（現物/特定預り）": ("日本株", "SBI特定"),
    "株式（現物/NISA預り（成長投資枠））": ("日本株", "SBI NISA成長投資枠"),
    "投資信託（金額/特定預り）": ("投信", "SBI特定"),
    "投資信託（金額/NISA預り（成長投資枠））": ("投信", "SBI NISA成長投資枠"),
    "投資信託（金額/NISA預り（つみたて投資枠））": ("投信", "SBI NISAつみたて投資枠"),
    "投資信託（金額/旧NISA預り）": ("投信", "SBI旧NISA"),
    "国内債券（特定預り）": ("債券", "SBI特定"),
}

# 列見出し行の先頭パターン
_HEADER_PATTERNS = re.compile(
    r"^(銘柄（コード）|ファンド名|銘柄,利率)"
)

# 合計行の先頭パターン（「○○合計」「総合計」）
_SUBTOTAL_PATTERN = re.compile(r".+合計")

# 数値正規化：全角プラス・全角カンマ・半角カンマ除去
_NUM_RE = re.compile(r"^[＋+]?([▲△-]?[\d,，\.]+)$")


def _decode_with_nel(raw: bytes) -> str:
    """Shift-JIS(cp932)としてデコードしつつ、NEL(0x85)を改行として扱う。

    0x85 は cp932 2バイト文字の2バイト目にもなり得る（例: 全角小文字 ｅ = 0x82 0x85）。
    そのため全 0x85 を無条件に置換すると文字を破壊する。リードバイトを認識して
    2バイト文字を消費し、文字境界に単独で現れた 0x85 のみを改行として扱う。
    """
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 0x85:  # 文字境界の単独 0x85 = NEL 改行
            out.append(0x0A)
            i += 1
        elif (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n:
            out.append(b)  # cp932 リードバイト → 次のトレイルバイトごと退避
            out.append(raw[i + 1])
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out).decode("cp932", errors="replace")


@dataclass
class SbiRow:
    asset_class: str
    account: str
    name: str
    external_id: str | None
    quantity: float | None
    cost_price: float | None      # 取得単価
    current_price: float | None   # 現在値
    gain_loss: float | None       # 評価損益
    gain_loss_pct: float | None   # 評価損益率%
    valuation: float | None       # 評価額
    face_value: float | None = None  # 国内債券: 保有額面
    errors: list[str] = field(default_factory=list)


def parse_csv(fp: IO[bytes]) -> tuple[list[SbiRow], list[str]]:
    """CSVファイルオブジェクトをパースし、(行リスト, エラーリスト)を返す。"""
    raw = fp.read()
    text = _decode_with_nel(raw)

    all_lines = text.splitlines()

    rows: list[SbiRow] = []
    parse_errors: list[str] = []

    # 先頭6行スキップ
    lines = all_lines[6:]

    current_asset_class = ""
    current_account = ""
    skip_next = 0  # 合計行直後のスキップカウンタ

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # 合計行直後スキップ
        if skip_next > 0:
            skip_next -= 1
            continue

        # セクション見出し検出
        # 株式・投信の見出しは `"株式（現物/特定預り）",` のようにクォート＋末尾カンマ付き、
        # 国内債券のみクォート無しのため、両方を正規化してから照合する。
        section_key = line.rstrip(",").strip().strip('"')
        if section_key in SECTION_MAP:
            current_asset_class, current_account = SECTION_MAP[section_key]
            continue

        # 合計行スキップ（直後2行も）
        if _SUBTOTAL_PATTERN.fullmatch(line.split(",")[0].strip().strip('"')):
            skip_next = 2
            continue

        # 列見出し行スキップ
        if _HEADER_PATTERNS.match(line.lstrip('"')):
            continue

        if not current_account:
            continue

        # 国内債券セクションは専用パース
        if current_asset_class == "債券":
            row, err = _parse_bond_row(line, current_asset_class, current_account)
        else:
            row, err = _parse_stock_or_fund_row(
                line, current_asset_class, current_account
            )

        if err:
            parse_errors.append(err)
        if row:
            rows.append(row)

    return rows, parse_errors


def _parse_stock_or_fund_row(
    line: str,
    asset_class: str,
    account: str,
) -> tuple[SbiRow | None, str | None]:
    """株式・投信行のパース（§9.3）。"""
    # ダブルクォートで囲まれた値を考慮してカンマ分割
    parts = _csv_split(line)
    if len(parts) < 10:
        return None, f"列数不足 ({len(parts)}): {line[:80]}"

    raw_name = parts[0].strip()
    external_id: str | None = None
    name: str

    if asset_class == "日本株":
        # 「コード 銘柄名」を最初の空白で分割
        idx = raw_name.find(" ")
        if idx == -1:
            idx = raw_name.find("　")  # 全角スペース
        if idx != -1:
            external_id = raw_name[:idx].strip()
            name = raw_name[idx:].strip()
        else:
            name = raw_name
    else:
        name = raw_name

    errors: list[str] = []

    quantity = _parse_num(parts[2], f"数量 ({line[:40]})", errors)
    cost_price = _parse_num(parts[3], f"取得単価 ({line[:40]})", errors)
    current_price = _parse_num(parts[4], f"現在値 ({line[:40]})", errors)
    gain_loss = _parse_num(parts[7], f"損益 ({line[:40]})", errors)
    gain_loss_pct = _parse_num(parts[8], f"損益% ({line[:40]})", errors)
    valuation = _parse_num(parts[9], f"評価額 ({line[:40]})", errors)

    row = SbiRow(
        asset_class=asset_class,
        account=account,
        name=name,
        external_id=external_id,
        quantity=quantity,
        cost_price=cost_price,
        current_price=current_price,
        gain_loss=gain_loss,
        gain_loss_pct=gain_loss_pct,
        valuation=valuation,
        errors=errors,
    )
    err_msg = "; ".join(errors) if errors else None
    return row, err_msg


def _parse_bond_row(
    line: str,
    asset_class: str,
    account: str,
) -> tuple[SbiRow | None, str | None]:
    """国内債券行のパース（§9.4）。クォート無し・列構成が異なる。

    列: 銘柄, 利率(%), 償還日, 利払日, 買付日, 保有額面, 取得単価, 約定為替, 参考為替, 評価額
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 10:
        return None, f"国内債券: 列数不足 ({len(parts)}): {line[:80]}"

    errors: list[str] = []
    name = parts[0]
    face_value = _parse_num(parts[5], f"保有額面 ({line[:40]})", errors)
    cost_price = _parse_num(parts[6], f"取得単価 ({line[:40]})", errors)
    valuation = _parse_num(parts[9], f"評価額 ({line[:40]})", errors)

    row = SbiRow(
        asset_class=asset_class,
        account=account,
        name=name,
        external_id=None,
        quantity=face_value,
        cost_price=cost_price,
        current_price=None,
        gain_loss=None,
        gain_loss_pct=None,
        valuation=valuation,
        face_value=face_value,
        errors=errors,
    )
    err_msg = "; ".join(errors) if errors else None
    return row, err_msg


def _csv_split(line: str) -> list[str]:
    """ダブルクォート付きCSV行を分割する（簡易実装）。"""
    import csv
    import io

    reader = csv.reader(io.StringIO(line))
    try:
        return next(reader)
    except StopIteration:
        return []


def _parse_num(
    raw: str,
    label: str,
    errors: list[str],
) -> float | None:
    """数値文字列を正規化して float に変換する。変換不能なら None。"""
    v = raw.strip().strip('"')
    if not v or v in ("--", "----/--/--", "-"):
        return None
    # 全角プラス除去・カンマ除去
    v = v.replace("＋", "").replace(",", "").replace("，", "")
    # 全角マイナス→半角
    v = v.replace("▲", "-").replace("△", "-")
    try:
        return float(v)
    except ValueError:
        errors.append(f"{label}: '{raw}' を数値に変換できません")
        return None
