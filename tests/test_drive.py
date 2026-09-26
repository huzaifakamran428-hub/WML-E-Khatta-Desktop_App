import os, sys, tempfile, json, threading, re, shutil, urllib.request
tmp = tempfile.mkdtemp(); os.environ["WML_DATA_DIR"] = tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import config, drive_backup as D
from app.local_api import client, APIError

class R:
    def __init__(s, code=200, data=None, content=b""): s.status_code, s._d, s.content = code, data or {}, content
    def json(s): return s._d

class FakeDrive:
    def __init__(s): s.files = {}; s.calls = []
    def post(s, url, data=None, headers=None, params=None, timeout=None):
        s.calls.append(("post", url))
        if url == D.TOKEN_URL:
            if data["grant_type"] == "authorization_code":
                assert data["code"] == "abc" and data["code_verifier"]
                return R(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
            assert data["refresh_token"] == "RT"
            return R(200, {"access_token": "AT2", "expires_in": 3600})
        assert url == D.UPLOAD_URL and headers["Authorization"].startswith("Bearer ")
        b = re.search(r"boundary=(\S+)", headers["Content-Type"]).group(1).encode()
        parts = data.split(b"--" + b)
        meta = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].strip())
        content = parts[2].split(b"\r\n\r\n", 1)[1][:-2]
        fid = f"id{len(s.files)+1}"; s.files[fid] = {"name": meta["name"], "data": content}
        return R(200, {"id": fid})
    def patch(s, url, data=None, headers=None, params=None, timeout=None):
        s.calls.append(("patch", url)); fid = url.rsplit("/", 1)[1]; s.files[fid]["data"] = data; return R(200, {"id": fid})
    def get(s, url, headers=None, params=None, timeout=None):
        s.calls.append(("get", url))
        if url == D.FILES_URL:
            name = re.search(r"name = '([^']+)'", params["q"]).group(1)
            hits = [{"id": k, "name": v["name"], "modifiedTime": "now"} for k, v in s.files.items() if v["name"] == name]
            return R(200, {"files": hits[:1]})
        fid = url.rsplit("/", 1)[1]; return R(200, content=s.files[fid]["data"])

fake = FakeDrive(); drive = D.DriveBackup(http=fake)

# credentials
good = os.path.join(tmp, "cred.json"); json.dump({"installed": {"client_id": "cid", "client_secret": "sec"}}, open(good, "w"))
web = os.path.join(tmp, "web.json"); json.dump({"web": {"client_id": "cid", "client_secret": "sec"}}, open(web, "w"))
assert not drive.credentials_available()
try: drive.install_credentials(web); raise SystemExit("web creds accepted")
except D.BackupError: pass
drive.install_credentials(good); assert drive.credentials_available()
print("credentials OK")

# sign-in flow (browser simulated)
def fake_browser(url):
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"] and q["scope"] == [D.SCOPE] and q["access_type"] == ["offline"]
    cb = f"{q['redirect_uri'][0]}/?code=abc&state={q['state'][0]}"
    threading.Timer(0.3, lambda: urllib.request.urlopen(cb).read()).start()
D.webbrowser.open = fake_browser
assert not drive.is_connected()
drive.connect(timeout=10)
assert drive.is_connected()
assert json.load(open(config.DRIVE_TOKEN_FILE))["refresh_token"] == "RT"
print("sign-in OK")

# business data, upload, change, upload again (must UPDATE the same file), restore
client.create_first_admin("boss", "secret1")
client.create("customers/", dict(name="Before Backup"))
drive.upload_backup(); assert len(fake.files) == 1
client.create("customers/", dict(name="After Backup"))
drive.upload_backup(); assert len(fake.files) == 1 and ("patch", D.UPLOAD_URL + "/id1") in fake.calls
client.create("customers/", dict(name="Junk Added Later"))
assert len(client.list_("customers/")) == 3
# restore the (2-customer) backup
safety = drive.restore_from_drive()
names = sorted(c["name"] for c in client.list_("customers/"))
assert names == ["After Backup", "Before Backup"], names
assert safety.exists()
print("upload/update/restore OK; safety copy kept:", safety.name)

# bad files are refused and current data is untouched
bad = os.path.join(tmp, "bad.db"); open(bad, "wb").write(b"not a database at all")
try: D.apply_restore(bad); raise SystemExit("bad file accepted")
except D.BackupError as e: print("bad file refused:", e)
assert len(client.list_("customers/")) == 2

# local file backup + restore
out = D.snapshot_to(os.path.join(tmp, "manual.db")); D.validate_backup_file(out)

# disconnect removes the token
drive.disconnect(); assert not drive.is_connected() and not config.DRIVE_TOKEN_FILE.exists()
shutil.rmtree(tmp); print("ALL DRIVE TESTS PASSED")
