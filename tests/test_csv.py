import os, sys, tempfile
tmp = tempfile.mkdtemp(); os.environ["WML_DATA_DIR"] = tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import csv_import as C
from app.local_api import client
client.create_first_admin("boss", "secret1")

# 1) the template we ship must import cleanly
t = os.path.join(tmp, "template.csv"); C.write_template(t)
p = C.read_csv(t); assert len(p.rows) == 2 and not p.skipped, p
r = client.post_json("laptops/bulk-import/", {"rows": p.rows}); assert r["created"] == 2 and not r["skipped"], r
lap = [l for l in client.list_("laptops/") if l["model_name"] == "Latitude 7490"][0]
assert lap["ram"] == "8 GB" and lap["storage"] == "256 GB SSD" and lap["cpu_cores"] == 4 and lap["purchase_price"] == 38000
assert lap["condition"] == "USED" and lap["purchase_date"] == "2026-08-15" and lap["quantity"] == 3 and lap["gpu"] == "Intel UHD 620"
print("template round-trip OK: all specs kept")

# 2) messy real-world file: semicolons, Excel-style headers, Rs/commas, blanks, bad rows, duplicate serial
messy = os.path.join(tmp, "messy.csv")
open(messy, "w", encoding="cp1252").write(
"Brand;MODEL;Gen;CPU;RAM;HDD;Condition;Serial No;Cost;Selling Price;Qty;Colour\n"
"Lenovo;ThinkPad T480;8th;Core i5;8GB;256GB SSD;used;LN1;Rs. 35,000;Rs 45,500;2;Black\n"
";Orphan;;;;;;;;;;\n"
"Acer;;;;;;;;;;;\n"
"\n"
"Apple;MacBook Air M1;;M1;8GB;256GB;New;AP1;;150000;;Silver\n"
"Asus;VivoBook;;;;;refurbished;LN1;1;2;1;\n")
p = C.read_csv(messy)
assert [r["brand"] for r in p.rows] == ["Lenovo", "Apple", "Asus"], p.rows
assert p.rows[0]["purchase_price"] == 35000 and p.rows[0]["sale_price"] == 45500 and p.rows[0]["condition"] == "USED"
assert len(p.skipped) == 2 and p.ignored_headers == ["Colour"], (p.skipped, p.ignored_headers)
r = client.post_json("laptops/bulk-import/", {"rows": p.rows})
assert r["created"] == 2 and len(r["skipped"]) == 1 and "LN1" in r["skipped"][0]["reason"], r   # duplicate serial LN1 skipped
print("messy file OK:", r["skipped"])

# 3) unusable files give a clear message
bad = os.path.join(tmp, "bad.csv"); open(bad, "w").write("foo,bar\n1,2\n")
try: C.read_csv(bad); raise SystemExit("accepted junk")
except ValueError as e: print("junk refused:", e)
print("ALL CSV TESTS PASSED")
