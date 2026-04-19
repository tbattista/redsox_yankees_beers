from __future__ import annotations

import calendar
import time
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .mlb import RED_SOX_ID, YANKEES_ID, TEAM_NAMES, Game, fetch_matchup
from .series import Series, Tally, group_into_series, tally_series

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Red Sox vs Yankees — Beer Series Tracker")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()

CURRENT_SEASON = 2026

# Simple in-memory cache so we don't hammer statsapi on every page load.
_cache: dict[int, tuple[float, list[Game]]] = {}
_CACHE_TTL_SECONDS = 600  # 10 min


async def _get_games(season: int) -> list[Game]:
    now = time.time()
    hit = _cache.get(season)
    if hit and now - hit[0] < _CACHE_TTL_SECONDS:
        return hit[1]
    games = await fetch_matchup(season)
    _cache[season] = (now, games)
    return games


def _build_context(season: int, games: list[Game]) -> dict:
    series_list = group_into_series(games)
    tally = tally_series(series_list)
    paid_map = db.get_paid_map(season)
    today = date.today()
    upcoming = [s for s in series_list if s.end_date >= today and s.winner_id is None and not s.is_tied_final]
    next_series = upcoming[0] if upcoming else None
    return {
        "season": season,
        "games": games,
        "series_list": series_list,
        "tally": tally,
        "paid_map": paid_map,
        "next_series": next_series,
        "today": today,
        "RED_SOX_ID": RED_SOX_ID,
        "YANKEES_ID": YANKEES_ID,
        "TEAM_NAMES": TEAM_NAMES,
        "available_seasons": list(range(CURRENT_SEASON, 2014, -1)),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    games = await _get_games(CURRENT_SEASON)
    ctx = _build_context(CURRENT_SEASON, games)
    ctx["request"] = request
    return templates.TemplateResponse("index.html", ctx)


@app.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request, season: int = CURRENT_SEASON):
    games = await _get_games(season)
    ctx = _build_context(season, games)
    ctx["request"] = request
    return templates.TemplateResponse("schedule.html", ctx)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_view(request: Request, season: int = CURRENT_SEASON):
    games = await _get_games(season)
    games_by_date: dict[date, list[Game]] = {}
    for g in games:
        games_by_date.setdefault(g.date_only, []).append(g)

    months = []
    if games:
        months_seen: set[tuple[int, int]] = set()
        for g in games:
            months_seen.add((g.date_only.year, g.date_only.month))
        for y, m in sorted(months_seen):
            cal = calendar.Calendar(firstweekday=6)  # Sunday
            weeks = cal.monthdatescalendar(y, m)
            months.append({
                "year": y,
                "month": m,
                "name": calendar.month_name[m],
                "weeks": weeks,
            })

    ctx = _build_context(season, games)
    ctx.update({
        "request": request,
        "games_by_date": games_by_date,
        "months": months,
    })
    return templates.TemplateResponse("calendar.html", ctx)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    """Backfill view: tallies across many seasons."""
    rows = []
    for season in range(CURRENT_SEASON - 1, 2014, -1):
        games = await _get_games(season)
        series_list = group_into_series(games)
        t = tally_series(series_list)
        rows.append({
            "season": season,
            "tally": t,
            "series_count": len(series_list),
            "games_count": len(games),
        })
    return templates.TemplateResponse("history.html", {
        "request": request,
        "rows": rows,
        "today": date.today(),
        "RED_SOX_ID": RED_SOX_ID,
        "YANKEES_ID": YANKEES_ID,
        "TEAM_NAMES": TEAM_NAMES,
    })


@app.post("/series/{season}/{anchor_game_pk}/paid")
async def toggle_paid(
    season: int,
    anchor_game_pk: int,
    paid: str = Form(""),
    redirect_to: str = Form("/"),
):
    db.set_paid(season, anchor_game_pk, paid == "on")
    # Only allow relative redirects back into the app.
    target = redirect_to if redirect_to.startswith("/") else "/"
    return RedirectResponse(target, status_code=303)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
