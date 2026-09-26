from __future__ import annotations

from datetime import datetime


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def format_currency(value) -> str:
    """Rs. 55,000  (decimals only when there are some)."""
    amount = _to_float(value)
    if abs(amount - round(amount)) < 0.005:
        return f"Rs. {int(round(amount)):,}"
    return f"Rs. {amount:,.2f}"


def format_date(value, fmt: str = "%d %b %Y") -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).strftime(fmt)
    except ValueError:
        return str(value)
