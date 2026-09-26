"""Money maths shared by the backend, the reports and the New Sale screen."""
from __future__ import annotations

EPS = 0.005


def final_price(price: float, amount: float, percent: float) -> float:
    discount = amount if amount > 0 else price * percent / 100.0
    return round(max(0.0, price - discount), 2)


def sale_totals(price: float, qty: int, amount: float, percent: float, received: float) -> dict:
    """Subtotal -> discount -> total to receive -> what is still left to receive.

    The discount is taken off the whole sale (price x quantity). If a rupee
    discount is given it is used; otherwise the percentage is applied.
    """
    subtotal = round(price * qty, 2)
    discount = amount if amount > 0 else round(subtotal * percent / 100.0, 2)
    discount = round(min(max(discount, 0.0), subtotal), 2)
    final = round(subtotal - discount, 2)
    remaining = round(max(final - received, 0.0), 2)
    if received >= final - EPS:
        status = "PAID"
    elif received > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"
    return {"subtotal": subtotal, "discount_total": discount, "final_total": final,
            "remaining_amount": remaining, "payment_status": status}
