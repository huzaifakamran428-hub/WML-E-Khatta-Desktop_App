"""Reports + dashboard numbers, worked out from the local database."""
from __future__ import annotations

from app.calc import EPS


def _in_range(iso_value: str | None, date_from: str | None, date_to: str | None) -> bool:
    day = (iso_value or "")[:10]
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


class Reports:
    def __init__(self, client):
        self.client = client
        self.conn = client._conn

    # -- building blocks ----------------------------------------------

    def _laptops(self):
        return self.conn.execute("SELECT * FROM laptops WHERE is_archived = 0").fetchall()

    def _inventory(self) -> dict:
        threshold = self.client._threshold()
        rows = self._laptops()
        low = [r for r in rows if 0 < r["quantity"] <= threshold]
        out = [r for r in rows if r["quantity"] <= 0]
        return {
            "total_units": sum(max(r["quantity"], 0) for r in rows),
            "low_stock_count": len(low),
            "out_of_stock_count": len(out),
            "total_stock_value": round(sum(r["sale_price"] * max(r["quantity"], 0) for r in rows), 2),
            "low_stock_items": [
                {"brand": r["brand"], "model_name": r["model_name"], "quantity": r["quantity"]}
                for r in sorted(low + out, key=lambda x: x["quantity"])
            ],
        }

    def _investment(self) -> dict:
        rows = [r for r in self._laptops() if r["quantity"] > 0]
        items = [{
            "brand": r["brand"], "model_name": r["model_name"], "quantity": r["quantity"],
            "purchase_price": r["purchase_price"],
            "investment": round(r["purchase_price"] * r["quantity"], 2),
        } for r in rows]
        return {
            "total_investment": round(sum(i["investment"] for i in items), 2),
            "laptops": len(items),
            "items": sorted(items, key=lambda i: i["investment"], reverse=True),
        }

    def _outstanding(self) -> dict:
        plans = [
            {"person": p["person_name"], "remaining_amount": p["remaining_amount"],
             "due_date": p["due_date"], "is_overdue": p["is_overdue"]}
            for p in self.client._plan_list({}) if p["remaining_amount"] > EPS
        ]
        sales = [
            {"person": s["customer_name"], "receipt_no": s["receipt_no"], "remaining_amount": s["remaining_amount"]}
            for s in self.client._sale_list({}) if s["remaining_amount"] > EPS
        ]
        shopkeepers = []
        for sk in self.client._sk_list({}):
            if sk["remaining_amount"] > EPS:
                count = self.conn.execute(
                    "SELECT COUNT(*) FROM shopkeeper_laptops WHERE shopkeeper=?", (sk["id"],)).fetchone()[0]
                shopkeepers.append({"person": sk["name"], "remaining_amount": sk["remaining_amount"],
                                    "laptop_count": count})
        total = sum(x["remaining_amount"] for x in plans + sales + shopkeepers)
        return {"total_outstanding": round(total, 2), "plans": plans, "sales": sales, "shopkeepers": shopkeepers}

    # -- dashboard ---------------------------------------------------------

    def dashboard(self, is_admin: bool) -> dict:
        inv = self._inventory()
        sales = self.client._sale_list({})
        data = {
            "total_units": inv["total_units"],
            "low_stock_count": inv["low_stock_count"],
            "out_of_stock_count": inv["out_of_stock_count"],
            "total_sales": round(sum(s["final_total"] for s in sales), 2),
            "total_outstanding": self._outstanding()["total_outstanding"],
        }
        if is_admin:
            data["total_profit"] = round(sum(i.get("profit", 0) for s in sales for i in s["items"]), 2)
            data["total_investment"] = self._investment()["total_investment"]
            data["total_purchase_cost"] = round(
                sum((i.get("purchase_cost_snapshot") or 0) * i["quantity"] for s in sales for i in s["items"]), 2)
            data["units_sold"] = sum(i["quantity"] for s in sales for i in s["items"])
            sold_items = []
            for s in sales:
                for it in s["items"]:
                    lap = self.conn.execute(
                        "SELECT brand, model_name FROM laptops WHERE id=?", (it["product"],)).fetchone()
                    sold_items.append({
                        "receipt_no": s["receipt_no"],
                        "customer_name": s["customer_name"],
                        "sale_date": s["sale_date"],
                        "brand": lap["brand"] if lap else "",
                        "model_name": lap["model_name"] if lap else "",
                        "quantity": it["quantity"],
                        "sale_price": it["sale_price"],
                        "profit": it.get("profit", 0),
                    })
            sold_items.sort(key=lambda i: i["sale_date"], reverse=True)
            data["sold_items"] = sold_items
        return data

    # -- reports (admin only; enforced before we get here) ----------------

    def report(self, name: str, params: dict) -> dict:
        date_from, date_to = params.get("date_from"), params.get("date_to")
        if name == "sales":
            sales = [s for s in self.client._sale_list({}) if _in_range(s["sale_date"], date_from, date_to)]
            return {
                "count": len(sales),
                "total_sales": round(sum(s["final_total"] for s in sales), 2),
                "sales": [{"receipt_no": s["receipt_no"], "customer__name": s["customer_name"],
                           "final_total": s["final_total"], "sale_date": s["sale_date"]} for s in sales],
            }
        if name == "profit":
            items = []
            for s in self.client._sale_list({}):
                if not _in_range(s["sale_date"], date_from, date_to):
                    continue
                for it in s["items"]:
                    lap = self.conn.execute("SELECT brand, model_name FROM laptops WHERE id=?", (it["product"],)).fetchone()
                    items.append({
                        "sale__receipt_no": s["receipt_no"],
                        "product__brand": lap["brand"] if lap else "",
                        "product__model_name": lap["model_name"] if lap else "",
                        "quantity": it["quantity"],
                        "sale_price": it["sale_price"],
                        "purchase_price": it.get("purchase_cost_snapshot", 0),
                        "profit": it.get("profit", 0),
                    })
            return {"total_profit": round(sum(i["profit"] for i in items), 2), "items": items}
        if name == "inventory":
            return self._inventory()
        if name == "investment":
            return self._investment()
        if name == "outstanding":
            return self._outstanding()
        if name == "payments":
            rows = []
            for s in self.client._sale_list({}):
                if s["amount_received"] > 0 and _in_range(s["sale_date"], date_from, date_to):
                    rows.append({"payment_date": s["sale_date"], "source": f"Sale {s['receipt_no']} - {s['customer_name']}",
                                 "amount": s["amount_received"], "method": s["payment_type"]})
            for p in self.conn.execute(
                    "SELECT p.*, c.name AS person FROM payments p JOIN credit_plans cp ON cp.id = p.credit_plan "
                    "JOIN customers c ON c.id = cp.customer"):
                if _in_range(p["payment_date"], date_from, date_to):
                    rows.append({"payment_date": p["payment_date"], "source": f"Credit plan - {p['person']}",
                                 "amount": p["amount"], "method": p["method"]})
            for p in self.conn.execute(
                    "SELECT p.*, s.name AS person FROM shopkeeper_payments p JOIN shopkeepers s ON s.id = p.shopkeeper"):
                if _in_range(p["payment_date"], date_from, date_to):
                    rows.append({"payment_date": p["payment_date"], "source": f"Shopkeeper - {p['person']}",
                                 "amount": p["amount"], "method": p["method"]})
            rows.sort(key=lambda r: r["payment_date"], reverse=True)
            return {"total_received": round(sum(r["amount"] for r in rows), 2), "rows": rows}
        from app.local_api import APIError
        raise APIError("Not found.", 404)
