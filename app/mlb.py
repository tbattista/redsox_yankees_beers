from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import httpx

STATS_API = "https://statsapi.mlb.com/api/v1"

RED_SOX_ID = 111
YANKEES_ID = 147

TEAM_NAMES = {
    RED_SOX_ID: "Red Sox",
    YANKEES_ID: "Yankees",
}


@dataclass
class Game:
    game_pk: int
    game_date: datetime
    status: str  # abstractGameState: Preview / Live / Final
    detailed_status: str
    home_id: int
    away_id: int
    home_score: Optional[int]
    away_score: Optional[int]
    venue: str
    series_game_number: Optional[int]
    games_in_series: Optional[int]
    series_description: Optional[str]

    @property
    def date_only(self) -> date:
        return self.game_date.date()

    @property
    def is_final(self) -> bool:
        return self.status == "Final"

    @property
    def winner_id(self) -> Optional[int]:
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        if self.home_score == self.away_score:
            return None
        return self.home_id if self.home_score > self.away_score else self.away_id

    @property
    def home_name(self) -> str:
        return TEAM_NAMES.get(self.home_id, str(self.home_id))

    @property
    def away_name(self) -> str:
        return TEAM_NAMES.get(self.away_id, str(self.away_id))


def _parse_game(raw: dict) -> Game:
    teams = raw.get("teams", {})
    home = teams.get("home", {})
    away = teams.get("away", {})
    return Game(
        game_pk=raw["gamePk"],
        game_date=datetime.fromisoformat(raw["gameDate"].replace("Z", "+00:00")),
        status=raw.get("status", {}).get("abstractGameState", "Unknown"),
        detailed_status=raw.get("status", {}).get("detailedState", ""),
        home_id=home.get("team", {}).get("id"),
        away_id=away.get("team", {}).get("id"),
        home_score=home.get("score"),
        away_score=away.get("score"),
        venue=raw.get("venue", {}).get("name", ""),
        series_game_number=raw.get("seriesGameNumber"),
        games_in_series=raw.get("gamesInSeries"),
        series_description=raw.get("seriesDescription"),
    )


async def fetch_matchup(season: int) -> list[Game]:
    """Fetch all Red Sox vs Yankees regular + postseason games for a season."""
    params = {
        "sportId": 1,
        "teamId": RED_SOX_ID,
        "opponentId": YANKEES_ID,
        "season": season,
        "gameType": "R,F,D,L,W",  # regular + postseason rounds
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{STATS_API}/schedule", params=params)
        r.raise_for_status()
        data = r.json()

    games: list[Game] = []
    for d in data.get("dates", []):
        for raw in d.get("games", []):
            g = _parse_game(raw)
            if {g.home_id, g.away_id} == {RED_SOX_ID, YANKEES_ID}:
                games.append(g)
    games.sort(key=lambda g: g.game_date)
    return games
