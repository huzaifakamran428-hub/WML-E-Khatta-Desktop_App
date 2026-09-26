import os, sys, tempfile, shutil
tmp = tempfile.mkdtemp()
os.environ["WML_DATA_DIR"] = tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.local_api import client, APIError
from app import config

def expect_error(fn, contains):
    try:
        fn()
    except APIError as e:
        assert contains.lower() in e.message.lower(), f"wrong message: {e.message!r} (wanted {contains!r})"
        return
    raise AssertionError(f"expected error containing {contains!r}")

# --- first run & login
assert client.needs_setup()
expect_error(lambda: client.list_("laptops/"), "log in")
expect_error(lambda: client.create_first_admin("boss", "123"), "at least 6")
u = client.create_first_admin("boss", "secret1", "Boss")
assert u["role"] == "ADMIN" and not client.needs_setup()
print("setup + login OK")

# --- inventory
lap = client.create("laptops/", dict(brand="Dell", model_name="Latitude 7490", generation="8th Gen", processor="Core i5",
    cpu_cores=4, ram="8 GB", storage="256 GB SSD", condition="USED", purchase_price=40000, sale_price=55000, quantity=3))
assert lap["final_price"] == 55000 and not lap["is_low_stock"]
assert lap["purchase_price"] == 40000
expect_error(lambda: client.create("laptops/", dict(brand="", model_name="x")), "brand")
lap2 = client.create("laptops/", dict(brand="HP", model_name="EliteBook", sale_price=60000, purchase_price=45000, quantity=1, serial_number="SN1"))
expect_error(lambda: client.create("laptops/", dict(brand="HP", model_name="EliteBook", serial_number="SN1")), "already exists")
assert lap2["is_low_stock"]
print("inventory OK")

# --- customers + sale with discount
cust = client.create("customers/", dict(name="Ali Khan", phone="0300-1234567"))
sale = client.create("sales/", dict(customer=cust["id"], laptop_id=lap["id"], quantity=1, sale_price=55000,
    discount_amount=2500, discount_percent=0, payment_type="CASH", amount_received=20000))
assert sale["final_total"] == 52500 and sale["remaining_amount"] == 32500 and sale["payment_status"] == "PARTIAL", sale
assert sale["receipt_no"] == "WML-00001"
assert sale["items"][0]["profit"] == 12500  # 52500 - 40000
assert client.retrieve("laptops/", lap["id"])["quantity"] == 2
# percent discount
sale2 = client.create("sales/", dict(customer=cust["id"], laptop_id=lap["id"], quantity=2, sale_price=55000,
    discount_amount=0, discount_percent=10, amount_received=99000))
assert sale2["final_total"] == 99000 and sale2["payment_status"] == "PAID"
expect_error(lambda: client.create("sales/", dict(customer=cust["id"], laptop_id=lap["id"], quantity=1, sale_price=1)), "stock")
expect_error(lambda: client.create("sales/", dict(customer=cust["id"], laptop_id=lap2["id"], quantity=1, sale_price=100, amount_received=500)), "more than the total")
# edit sale: increase received
upd = client.update("sales/", sale["id"], dict(amount_received=52500, quantity=1))
assert upd["payment_status"] == "PAID"
# receipt search
assert client.get_json("sales/receipt/1/")["id"] == sale["id"]
assert client.get_json("sales/receipt/wml-00002/")["id"] == sale2["id"]
# delete sale restores stock
client.remove("sales/", sale2["id"])
assert client.retrieve("laptops/", lap["id"])["quantity"] == 2
print("sales OK")

# --- shopkeeper flow
sk = client.create("shopkeepers/", dict(name="Bilal Traders", phone="0311"))
assert sk["reference_number"] == "SK-0001"
item = client.create("shopkeeper-laptops/", dict(shopkeeper=sk["id"], inventory_laptop=lap["id"], price=50000))
extra = client.create("shopkeeper-extra-money/", dict(shopkeeper=sk["id"], amount=5000, note="cash advance"))
d = client.retrieve("shopkeepers/", sk["id"])
assert d["total_amount"] == 55000 and d["remaining_amount"] == 55000 and d["status"] == "PENDING"
client.create("shopkeeper-payments/", dict(shopkeeper=sk["id"], laptop_item=item["id"], amount=50000, method="BANK"))
expect_error(lambda: client.create("shopkeeper-payments/", dict(shopkeeper=sk["id"], extra_money=extra["id"], amount=9000)), "more than")
client.create("shopkeeper-payments/", dict(shopkeeper=sk["id"], extra_money=extra["id"], amount=5000))
d = client.retrieve("shopkeepers/", sk["id"])
assert d["status"] == "CLEARED" and d["remaining_amount"] == 0 and all(l["is_cleared"] for l in d["laptops"])
print("shopkeepers OK")

# --- credit plan
plan = client.create("credit-plans/", dict(customer=cust["id"], laptop=lap["id"], total_amount=60000, down_payment=10000,
    installment_amount=10000, due_date="2020-01-01"))
assert plan["remaining_amount"] == 50000 and plan["is_overdue"]
client.create("payments/", dict(credit_plan=plan["id"], amount=20000, method="CASH"))
expect_error(lambda: client.create("payments/", dict(credit_plan=plan["id"], amount=99999)), "more than")
plan = client.retrieve("credit-plans/", plan["id"])
assert plan["remaining_amount"] == 30000
print("credit plans OK")

# --- reports & dashboard
dash = client.get_json("dashboard/")
assert "total_profit" in dash and dash["total_sales"] > 0, dash
for r in ("sales", "profit", "inventory", "investment", "outstanding", "payments"):
    out = client.get_json(f"reports/{r}/", {"date_from": "2000-01-01", "date_to": "2999-01-01"})
    assert isinstance(out, dict)
assert all("purchase_cost_snapshot" not in i for i in client.get_json("reports/profit/")["items"])
print("reports OK", dash)

# --- notifications
client.logout(); client.login("boss", "secret1")
notes = client.list_("notifications/")
assert any("Overdue" in n["title"] for n in notes), [n["title"] for n in notes]
assert client.get_json("notifications/unread-count/")["count"] >= 1
print("notifications OK")

# --- users, roles, privacy
ro = client.create("users/", dict(username="viewer", role="READ_ONLY", password="viewer1"))
expect_error(lambda: client.create("users/", dict(username="VIEWER", role="READ_ONLY", password="viewer1")), "conflicts")
expect_error(lambda: client.update("users/", client.list_("users/")[0]["id"], dict(role="READ_ONLY")), "at least one")
client.logout()
expect_error(lambda: client.login("viewer", "nope"), "wrong username")
v = client.login("viewer", "viewer1")
assert v["role"] == "READ_ONLY"
laps = client.list_("laptops/")
assert all("purchase_price" not in l and "supplier" not in l for l in laps)
expect_error(lambda: client.create("customers/", dict(name="x")), "read-only")
expect_error(lambda: client.list_("users/"), "administrator")
expect_error(lambda: client.get_json("reports/sales/"), "administrator")
d = client.get_json("dashboard/")
assert "total_profit" not in d and "total_investment" not in d
assert all("profit" not in i for s in client.list_("sales/") for i in s["items"])
client.post_json("users/me/change-password/", dict(current_password="viewer1", new_password="viewer2"))
client.logout()
client.login("viewer", "viewer2")
client.logout()
assert client.current_user is None
# nothing about the session/password on disk
for root, _, files in os.walk(tmp):
    for f in files:
        blob = open(os.path.join(root, f), "rb").read()
        assert b"viewer2" not in blob and b"secret1" not in blob, f"plain password found in {f}"
print("roles / privacy OK; files:", sorted(os.listdir(tmp)))

# lockout
for _ in range(5):
    try: client.login("boss", "bad")
    except APIError: pass
expect_error(lambda: client.login("boss", "secret1"), "too many")
print("lockout OK")
shutil.rmtree(tmp)
print("ALL BACKEND TESTS PASSED")
