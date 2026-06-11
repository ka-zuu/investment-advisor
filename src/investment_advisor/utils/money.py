from __future__ import annotations


def format_jpy(amount: float) -> str:
    return f"¥{amount:,.0f}"


def format_pct(value: float | None, *, plus_sign: bool = True) -> str:
    if value is None:
        return "N/A"
    sign = "+" if (plus_sign and value > 0) else ""
    return f"{sign}{value:.2f}%"
