"""Shared helpers for the GigaNuke3 profile grid cards.

Extracted from pacman_grid.py so the Tetris card, the monthly contribution
graph and the activity card all use the same public-calendar fetcher, dither
patterns, pixel art and SMIL timeline helpers.
"""

import os
import random
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from profile_card import PAD, THEMES, USER, graphql

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Asia/Manila")

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""


def day(d: date, count: int, level: int) -> dict:
    return {"date": d, "weekday": (d.weekday() + 1) % 7, "count": count, "level": level}


def to_weeks(days: list[dict]) -> list[list[dict]]:
    """Group days into Sunday-first columns, like the GitHub calendar."""
    weeks: list[list[dict]] = []
    for d in sorted(days, key=lambda d: d["date"]):
        if not weeks or d["weekday"] == 0:
            weeks.append([])
        weeks[-1].append(d)
    return weeks


def fetch_public_calendar() -> list[list[dict]]:
    """The calendar on github.com/<user>: what visitors see, no token needed."""
    req = urllib.request.Request(f"https://github.com/users/{USER}/contributions",
                                 headers={"User-Agent": "profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")
    cells = re.findall(r'data-date="([\d-]+)" id="(contribution-day-component-[\d-]+)" data-level="(\d)"', html)
    tips = dict(re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)</tool-tip>', html))
    if len(cells) < 300:
        raise RuntimeError(f"contributions page changed: parsed {len(cells)} days")
    days = []
    for iso, cid, level in cells:
        m = re.match(r"(\d+) contribution", tips.get(cid, ""))
        days.append(day(date.fromisoformat(iso), int(m.group(1)) if m else 0, int(level)))
    return to_weeks(days)


def fetch_api_calendar(token: str) -> list[list[dict]]:
    data = graphql(token, CALENDAR_QUERY, {"login": USER})
    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return to_weeks([day(date.fromisoformat(d["date"]), d["contributionCount"], LEVELS[d["contributionLevel"]])
                     for w in weeks for d in w["contributionDays"]])


def tiles(weeks: list[list[dict]], today: date) -> list[tuple[str, str]]:
    """Stat tiles: today, yesterday, week, streaks and monthly totals."""
    days = {d["date"]: d["count"] for w in weeks for d in w}

    def total(start: date, end: date = today) -> int:
        return sum(c for d, c in days.items() if start <= d <= end)

    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    streak, d = 0, today if days.get(today) else today - timedelta(days=1)
    while days.get(d):
        streak, d = streak + 1, d - timedelta(days=1)
    return [
        (str(days.get(today, 0)), "Today"),
        (str(days.get(today - timedelta(days=1), 0)), "Yesterday"),
        (str(total(today - timedelta(days=today.weekday()))), "This Week"),
        (str(total(today - timedelta(days=6))), "Last 7 Days"),
        (f"{streak}d", "Current Streak"),
        (str(total(month_start)), "This Month"),
        (str(total(last_month_end.replace(day=1), last_month_end)), "Last Month"),
        (str(total(today - timedelta(days=29))), "Last 30 Days"),
        (str(total(today - timedelta(days=89))), "Last 3 Months"),
        (f"{sum(days.values()):,}", "Last Year"),
    ]


def pixel_art(rows: list[str], fill: str, px: int = 2) -> str:
    """Centre a '#' bitmap on (0, 0) as crisp squares."""
    off = len(rows) * px / 2
    return "".join(
        f'<rect x="{x * px - off}" y="{y * px - off}" width="{px}" height="{px}"/>'
        for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "#"
    ).join([f'<g fill="{fill}">', "</g>"])


def patterns(ink: str) -> str:
    """Level 0-3 dither fills: 4x4 tiles of 2px 'pixels' (level 0 is a faint 1px dot)."""
    def pat(pid, rects, opacity=1):
        body = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{w}"/>' for x, y, w in rects)
        return (f'<pattern id="{pid}" width="4" height="4" patternUnits="userSpaceOnUse">'
                f'<g fill="{ink}" opacity="{opacity}">{body}</g></pattern>')
    return "".join([
        pat("l0", [(0, 0, 1)], 0.45),
        pat("l1", [(0, 0, 2)]),
        pat("l2", [(0, 0, 2), (2, 2, 2)]),
        pat("l3", [(0, 0, 2), (2, 2, 2), (2, 0, 2)]),
    ])


def fill_for(level: int, ink: str) -> str:
    return ink if level >= 4 else f"url(#l{max(level, 1)})"


class Timeline:
    """Builds SMIL attributes on one shared loop of `dur` seconds."""

    def __init__(self, dur: float):
        self.dur = dur
        self.loop = f'dur="{dur:.2f}s" repeatCount="indefinite"'

    def key(self, t: float) -> str:
        return f"{min(max(t / self.dur, 0), 1):.5f}"

    def steps(self, changes: list[tuple[float, str]]) -> str:
        """Discrete values from (time, value) change points; first must be at 0."""
        pts = []
        for t, v in changes:
            if pts and pts[-1][1] == v:
                continue
            if pts and self.key(t) == self.key(pts[-1][0]):
                pts[-1] = (pts[-1][0], v)
            else:
                pts.append((t, v))
        return (f'values="{";".join(v for _, v in pts)}" '
                f'keyTimes="{";".join(self.key(t) for t, _ in pts)}" calcMode="discrete" {self.loop}')

    def show(self, changes: list[tuple[float, bool]]) -> str:
        return f'<animate attributeName="opacity" {self.steps([(t, "1" if on else "0") for t, on in changes])}/>'

    def motion(self, times: list[float], points: list[tuple[float, float]]) -> str:
        times, points = [0.0] + times + [self.dur], [points[0]] + points + [points[-1]]
        keep = [0] + [i for i in range(1, len(times)) if self.key(times[i]) != self.key(times[i - 1])]
        vals = ";".join(f"{points[i][0]},{points[i][1]}" for i in keep)
        keys = ";".join(self.key(times[i]) for i in keep)
        return f'<animateMotion values="{vals}" keyTimes="{keys}" calcMode="linear" {self.loop}/>'
