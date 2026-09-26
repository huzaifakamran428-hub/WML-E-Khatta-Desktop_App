Installing Python Command:
winget install -e --id Python.Python.3.12

python --version
pip --version


python -m venv venv
.\venv\Scripts\Activate.ps1

Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

pip install -r requirements.txt

python main.py

pyinstaller wml_ekhatta.spec

winget install -e --id JRSoftware.InnoSetup

iscc "installer\WML_E-Khatta_Setup.iss"

cd "$env:USERPROFILE\Documents\WML_E-Khatta"
.\venv\Scripts\Activate.ps1
python main.py


# WML E-Khatta

A desktop app for **Waqare Medina Computers & Laptop** — inventory, sales,
shopkeeper accounts, credit plans, reports, users, and bills. Runs entirely
on your own computer: no server, no monthly hosting, no internet required
day-to-day.

This is a rebuild of the earlier `desktop_app` project. What changed:

- **No server.** Everything that used to go to Render now lives in one
  local database file on your computer (`wml_ekhatta.db`). The app works
  fully offline.
- **Google Drive backup.** Turn it on once in Settings and every change is
  backed up to your own Drive automatically. A "Restore from Drive" button
  brings it all back on any computer.
- **No saved passwords.** Every person types their username and password
  each time. Nothing is cached, so logging out is actually private.
- **New Sale shows the total as you type** — subtotal, discount, and what's
  left to receive update live, so you never have to work it out by hand.
- **CSV import** for Inventory — add many laptops at once from a
  spreadsheet.
- **Purchase price is private** — only visible to admins, and only inside
  the laptop's Edit screen. It's never shown elsewhere or printed on bills.
- **A6 bills** — small, clean, printable receipts.
- **A glossy, modern look**, in the shop's own green-and-gold colours.

## Running it (development)

```
pip install -r requirements.txt
python main.py
```

The very first time you run it, you'll be asked to create the
administrator account for this computer — pick any username and password
(6+ characters). After that, everyone who uses this computer logs in with
their own account from the same screen.

## Setting up Google Drive backup (optional but recommended)

The app backs up to **your own** Google Drive — Anthropic and I have no
access to it, and neither does anyone else's Drive. It only ever touches
the one backup file it creates (`WML_E-Khatta_backup.db`); it cannot see
or touch anything else in your Drive.

To turn it on:

1. Go to <https://console.cloud.google.com/> and create a project (or use
   an existing one).
2. Enable the **Google Drive API** for that project (APIs & Services →
   Enable APIs → search "Google Drive API").
3. Go to APIs & Services → Credentials → Create Credentials → OAuth
   client ID.
   - Application type: **Desktop app**.
   - Give it any name, e.g. "WML E-Khatta".
4. Download the JSON file it gives you.
5. In the app: **Settings → Google Drive backup → Connect Google Drive**,
   and choose that JSON file when asked. Your browser will open so you can
   sign in and approve access — then you're done.

If you'd rather not deal with any of this, the **local backup file**
button right below it does the same job onto a USB drive or folder,
no Google account needed.

## Building the Windows installer

On a Windows computer (PyInstaller must build on the OS you're targeting):

```
pip install -r requirements.txt
pyinstaller wml_ekhatta.spec
```

This creates `dist\WML E-Khatta\` with the built app inside. Then, with
[Inno Setup](https://jrsoftware.org/isinfo.php) installed, open
`installer\WML_E-Khatta_Setup.iss` and click Compile (or run
`iscc installer\WML_E-Khatta_Setup.iss` from the command line). That
produces `installer\WML_E-Khatta_Setup.exe` — a normal Windows installer
with a Start Menu entry, an optional desktop shortcut, and an uninstaller.

For a Mac build, run the same `pyinstaller wml_ekhatta.spec` command on a
Mac — it will produce a `.app` bundle in `dist/` instead.

## Where your data lives

- Windows: `%APPDATA%\WML_EKhatta\wml_ekhatta.db`
- Mac: `~/Library/Application Support/WML_EKhatta/wml_ekhatta.db`
- Linux: `~/.local/share/WML_EKhatta/wml_ekhatta.db`

Back this file up occasionally even if you're not using Google Drive —
Settings → "Save a backup file..." does this in one click.

## Project layout

```
main.py                    entry point
app/config.py               paths, app name
app/db.py                   database schema, password hashing
app/local_api.py            all business logic (used to be the server)
app/local_reports.py        dashboard + report calculations
app/calc.py                 sale total / discount math
app/csv_import.py           inventory CSV import
app/drive_backup.py         Google Drive upload/download, local backup
app/backup_manager.py       automatic-backup scheduling (Qt-aware)
app/ui/                     every screen
app/ui/theme.py             colours, icons, the glossy stylesheet
app/ui/widgets/crud.py      the reusable "list + add/edit/delete" screen
app/utils/bill_pdf.py       A6 bill generator
app/utils/formatting.py     currency/date display helpers
assets/                     shop logo, app icon
installer/                  Windows installer script
tests/                      automated tests (see below)
```

## Running the tests

```
python tests/test_backend.py
python tests/test_csv.py
python tests/test_drive.py
```

These don't need Qt, a real Google account, or the internet — they test
the underlying logic directly (sales math, stock, roles and privacy,
CSV parsing, and the Drive backup flow against a stand-in for Google's
API).
