from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .mlb import Game, RED_SOX_ID, YANKEES_ID, TEAM_NAMES


@dataclass
class Series:
    index: int
    games: list[Game] = field(default_factory=list)

    @property
    def anchor_game_pk(self) -> int:
        """Stable identifier for this series — the first game's MLB gamePk."""
        return self.games[0].game_pk

    @property
    def start_date(self) -> date:
        return self.games[0].date_only

    @property
    def end_date(self) -> date:
        return self.games[-1].date_only

    @property
    def venue(self) -> str:
        return self.games[0].venue

    @property
    def host_id(self) -> int:
        return self.games[0].home_id

    @property
    def expected_games(self) -> int:
        return self.games[0].games_in_series or len(self.games)

    @property
    def finished_games(self) -> list[Game]:
        return [g for g in self.games if g.is_final]

    def wins_for(self, team_id: int) -> int:
        return sum(1 for g in self.finished_games if g.winner_id == team_id)

    @property
    def is_complete(self) -> bool:
        # Complete when every scheduled game is final.
        return len(self.finished_games) == len(self.games) and len(self.games) >= self.expected_games

    @property
    def winner_id(self) -> Optional[int]:
        """The team that has clinched or won the series. None if unresolved/tied."""
        sox = self.wins_for(RED_SOX_ID)
        yanks = self.wins_for(YANKEES_ID)
        remaining = max(self.expected_games - len(self.finished_games), 0)

        if sox > yanks + remaining:
            return RED_SOX_ID
        if yanks > sox + remaining:
            return YANKEES_ID
        if self.is_complete:
            if sox > yanks:
                return RED_SOX_ID
            if yanks > sox:
                return YANKEES_ID
        return None

    @property
    def is_tied_final(self) -> bool:
        if not self.is_complete:
            return False
        return self.wins_for(RED_SOX_ID) == self.wins_for(YANKEES_ID)

    @property
    def status_label(self) -> str:
        if self.winner_id is not None:
            return f"{TEAM_NAMES[self.winner_id]} win series"
        if self.is_tied_final:
            return "Series split"
        if self.finished_games:
            return "In progress"
        return "Upcoming"


def group_into_series(games: list[Game]) -> list[Series]:
    """Group consecutive games into series using MLB's seriesGameNumber when available,
    otherwise by consecutive dates at the same venue."""
    series_list: list[Series] = []
    current: Optional[Series] = None

    for g in games:
        start_new = False
        if current is None:
            start_new = True
        elif g.series_game_number == 1:
            start_new = True
        elif g.venue != current.venue:
            start_new = True
        else:
            gap = (g.date_only - current.games[-1].date_only).days
            if gap > 2:
                start_new = True

        if start_new:
            current = Series(index=len(series_list) + 1)
            series_list.append(current)
        current.games.append(g)

    return series_list


@dataclass
class Tally:
    red_sox_series: int = 0
    yankees_series: int = 0
    splits: int = 0
    pending: int = 0

    @property
    def beer_balance(self) -> int:
        """Positive => Yankees owe Red Sox beers; negative => Red Sox owe Yankees."""
        return self.red_sox_series - self.yankees_series


def tally_series(series_list: list[Series]) -> Tally:
    t = Tally()
    for s in series_list:
        if s.winner_id == RED_SOX_ID:
            t.red_sox_series += 1
        elif s.winner_id == YANKEES_ID:
            t.yankees_series += 1
        elif s.is_tied_final:
            t.splits += 1
        else:
            t.pending += 1
    return t
