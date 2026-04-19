# Red Sox vs Yankees — Beer Series Tracker

Tiny FastAPI site that tracks Red Sox / Yankees head-to-head series so two friends can settle a six-pack-per-series bet.

## What it does

- Pulls the season's Red Sox vs Yankees games from the public MLB Stats API (`statsapi.mlb.com`), no auth.
- Groups games into series (uses MLB's `seriesGameNumber` / `gamesInSeries` fields).
- Decides a series winner as soon as it's clinched (majority of the scheduled games won).
- Tallies series wins, splits, and a net beer balance.
- Renders three views: **Dashboard** (tally + next series), **Schedule** (list by series), **Calendar** (month grid).
- **History** page replays the same logic across past seasons so you can see what the bet would've paid out.
- Every settled series has a **Paid / Unpaid** toggle so you can track whether the six-pack has actually been handed over. State is stored in a local SQLite file (`$DATA_DIR/app.db`, default `./data/app.db`).

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/.

## Deploying to Railway

1. Push this repo to GitHub.
2. Create a new Railway project from the repo.
3. Railway auto-detects Python via `nixpacks` and uses the start command in `railway.json` / `Procfile`:
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add a Railway **Volume** mounted at `/data` and set the env var `DATA_DIR=/data` so the paid-toggle SQLite DB survives redeploys. Without a volume the DB resets on every deploy.

## Notes

- MLB responses are cached in-process for 10 minutes to avoid hammering the API.
- `gameType=R,F,D,L,W` pulls regular season plus any postseason matchups.
- Series winner rule: whichever team wins more of the scheduled games in that series. A 1–1 in a 2-game set counts as a split (no beer owed).
