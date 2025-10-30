# Sayyor Qabul / Открытый диалог – Telegram Registration Bot

Bilingual (UZ/RU) registration bot for open-dialog events. Collects: region → mode (offline/online) → full name → DOB → district → phone (one‑tap) → appeal text. Saves to CSV; optional Google Sheets sync.

## Quick Start (local)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Set token
# macOS/Linux
export TELEGRAM_TOKEN="123:ABC"
# Windows PowerShell
# $env:TELEGRAM_TOKEN="123:ABC"

python sayyor_qabul_bot.py
```

## Files

- `sayyor_qabul_bot.py` – main bot (polling)
- `.env.example` – template for environment variables
- `requirements.txt` – Python deps
- `Procfile` – worker process declaration (Heroku/Railway)
- `.gitignore` – git ignores
- `LICENSE` – MIT
- `README.md` – this file

## Optional: Google Sheets

1. Create a Service Account and download JSON key.
2. Create a Google Sheet and **share** it with the service account email.
3. Uncomment the `gspread` block in the code.
4. Set env vars (or `.env`):

```
GOOGLE_SHEETS_JSON=/abs/path/to/sa.json
GOOGLE_SHEETS_NAME=SayyorQabul
```

## Deploy (Heroku/Railway)

- Uses polling. Scale a **worker** dyno/process:

**Heroku**
```
heroku login
heroku create
heroku buildpacks:add heroku/python
git push heroku main
heroku config:set TELEGRAM_TOKEN=123:ABC
heroku ps:scale worker=1
```

**Railway**
- Create a new project → Deploy from repo.
- Add env var `TELEGRAM_TOKEN`.
- Railway reads `Procfile` automatically.

## Notes

- Telegram bots **cannot** message a user before they tap **Start**.
- CSV output: `registrations.csv` in project root.
- DOB accepted as `dd.mm.yyyy` (also `/` or `-`).
