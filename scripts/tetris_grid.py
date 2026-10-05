"""Landscape Tetris contribution card: tetris_dark.svg + tetris_light.svg.

Replaces the Pac-Man grid. The 53-week x 7-day GitHub contribution calendar
is the board: days with contributions are fixed orange ground blocks, and
classic tetrominoes fall from the sky and stack onto them, filling the
valleys until the board is full. Then the stack flashes and the game resets,
looping forever on the shared SMIL timeline.

Usage:
    python scripts/tetris_grid.py            # live calendar (token fallback)
    python scripts/tetris_grid.py --offline  # fake calendar
    python scripts/tetris_grid.py --seed 7   # fixed piece sequence
"""

import argparse
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from grid_common import (TZ, Timeline, day, fetch_api_calendar,
                         fetch_public_calendar, fill_for, patterns, tiles,
                         to_weeks)
from profile_card import PAD, THEMES

ROOT = Path(__file__).resolve().parent.parent

CELL_W, CELL_H = 12, 24
COL, ROW = 16, 28          # pitch
TILE_H = 56
TILES_GAP = 24
MONTH_H = 24
ROWS = 7                   # Sunday..Saturday
SPAWN_ROW = -4             # pieces drop in from just above the board
FALL_SPEED = 190           # px/s while falling
GAP = 0.55                 # pause between a lock and the next piece
READY = 1.4                # READY! pause at the start of the loop
FULL_PAUSE = 2.2           # BOARD FULL! sign before the flash
FLASH = 1.0                # stack flashes before the reset
END_PAUSE = 0.5            # beat of calm before the loop restarts

# Classic tetrominoes in a 4x4 box; four rotations each.
SHAPES = {
    "I": [[(0, 1), (1, 1), (2, 1), (3, 1)],
          [(2, 0), (2, 1), (2, 2), (2, 3)],
          [(0, 1), (1, 1), (2, 1), (3, 1)],
          [(2, 0), (2, 1), (2, 2), (2, 3)]],
    "O": [[(1, 1), (2, 1), (1, 2), (2, 2)]] * 4,
    "T": [[(1, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (1, 1), (2, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (1, 2)],
          [(1, 0), (0, 1), (1, 1), (1, 2)]],
    "S": [[(1, 0), (2, 0), (0, 1), (1, 1)],
          [(1, 0), (1, 1), (2, 1), (2, 2)],
          [(1, 1), (2, 1), (0, 2), (1, 2)],
          [(0, 0), (0, 1), (1, 1), (1, 2)]],
    "Z": [[(0, 0), (1, 0), (1, 1), (2, 1)],
          [(2, 0), (1, 1), (2, 1), (1, 2)],
          [(0, 1), (1, 1), (1, 2), (2, 2)],
          [(1, 0), (0, 1), (1, 1), (0, 2)]],
    "J": [[(0, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (2, 0), (1, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (2, 2)],
          [(1, 0), (1, 1), (0, 2), (1, 2)]],
    "L": [[(2, 0), (0, 1), (1, 1), (2, 1)],
          [(1, 0), (1, 1), (1, 2), (2, 2)],
          [(0, 1), (1, 1), (2, 1), (0, 2)],
          [(0, 0), (1, 0), (1, 1), (1, 2)]],
}

# Classic Tetris colours, tuned for each card theme.
SHAPE_COLOURS = {
    "dark": {"I": "#56d4dd", "O": "#f2cc60", "T": "#d2a8ff", "S": "#7ee787",
             "Z": "#ff7b72", "J": "#79c0ff", "L": "#ffa657"},
    "light": {"I": "#1b7c83", "O": "#9a6700", "T": "#8250df", "S": "#1a7f37",
              "Z": "#cf222e", "J": "#0969da", "L": "#bc4c00"},
}


def shape_cells(name: str, rot: int) -> list[tuple[int, int]]:
    return SHAPES[name][rot % len(SHAPES[name])]


def play(weeks: list[list[dict]], rng: random.Random, ncols: int):
    """Simulate one game: tetrominoes stacking onto the contribution cells."""
    by_node = {(w, d["weekday"]): d for w, week in enumerate(weeks) for d in week}
    base = {(w, d["weekday"]) for w, week in enumerate(weeks) for d in week if d["count"]}
    occupied = set(base)
    drops: list[dict] = []
    names = list(SHAPES)

    while True:
        name = rng.choice(names)
        best = None  # (score, rot, col, land_row)
        for rot in range(4):
            cells = SHAPES[name][rot]
            w = max(x for x, _ in cells) + 1
            h = max(y for y, _ in cells) + 1
            for col in range(0, ncols - w + 1):
                row = SPAWN_ROW
                while True:
                    hit = any(row + y >= ROWS or (col + x, row + y) in occupied
                              for x, y in cells)
                    if hit:
                        break
                    row += 1
                land_row = row - 1
                if land_row < -1:  # would be invisible above the board
                    continue
                # Fill the deepest valley first, then avoid leaving holes.
                bottom = land_row + h - 1
                holes = 0
                for x, y in cells:
                    cx, cy = col + x, land_row + y
                    r = cy + 1
                    while r < ROWS and (cx, r) not in occupied:
                        holes += 1
                        r += 1
                score = bottom * 100 - holes * 8 + rng.random() * 6
                if best is None or score > best[0]:
                    best = (score, rot, col, land_row)
        if best is None:
            break
        _, rot, col, land_row = best
        cells = SHAPES[name][rot]
        locked = [(col + x, land_row + y) for x, y in cells]
        occupied.update(locked)
        drops.append({"name": name, "rot": rot, "col": col, "land_row": land_row,
                      "cells": locked})
    return base, by_node, drops


def fake_calendar(today: date) -> list[list[dict]]:
    rng = random.Random(7)
    days = []
    for i in range(365):
        d = today - timedelta(days=364 - i)
        count = rng.choice([1, 2, 3, 5, 8, 13]) if rng.random() < 0.22 else 0
        days.append(day(d, count, 0 if not count else min(4, 1 + count // 4)))
    return to_weeks(days)


def render(name: str, theme: dict, weeks: list[list[dict]], stats: list[tuple[str, str]],
           base: set, by_node: dict, drops: list[dict]) -> str:
    ink, bg, accent = theme["text"], theme["bg"], theme["key"]
    ncols = len(weeks)
    grid_w = ncols * COL - (COL - CELL_W)
    width = PAD * 2 + grid_w
    grid_top = PAD + 2 * TILE_H + TILES_GAP
    height = grid_top + ROWS * ROW + MONTH_H + PAD // 2

    def cell_xy(n: tuple) -> tuple[int, int]:
        return PAD + n[0] * COL, grid_top + n[1] * ROW

    # One shared SMIL loop: READY!, pieces drop one by one, BOARD FULL!, flash.
    t = READY
    for d in drops:
        fall_dist = (d["land_row"] - SPAWN_ROW) * ROW
        d["spawn"] = t
        d["lock"] = t + max(0.45, fall_dist / FALL_SPEED)
        t = d["lock"] + GAP
    game_over_at = drops[-1]["lock"] + GAP if drops else READY
    flash_start = game_over_at + FULL_PAUSE
    game_end = flash_start + FLASH
    dur = game_end + END_PAUSE
    tl = Timeline(dur)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges" '
        f'font-family="Consolas, \'Courier New\', monospace">',
        f"<defs>{patterns(ink)}"
        f'<clipPath id="boardClip"><rect x="{PAD - 2}" y="{grid_top - 2}" '
        f'width="{grid_w + 4}" height="{ROWS * ROW - (ROW - CELL_H) + 4}"/></clipPath></defs>',
        f'<rect width="{width}" height="{height}" rx="15" fill="{bg}"/>',
    ]

    # Stat tiles.
    tile_w = grid_w / 5
    for i, (value, label) in enumerate(stats):
        x = PAD + (i % 5) * tile_w
        y = PAD + (i // 5) * TILE_H
        out.append(
            f'<rect x="{x:.0f}" y="{y + 4}" width="8" height="{TILE_H - 16}" fill="url(#l1)"/>'
            f'<text x="{x + 16:.0f}" y="{y + 26}" font-size="24" fill="{ink}">{escape(value)}</text>'
            f'<text x="{x + 16:.0f}" y="{y + 40}" font-size="11" fill="{ink}" opacity="0.8">{escape(label)}</text>'
        )

    # Board floor + the fixed contribution cells (the landscape ground).
    for n, d in sorted(by_node.items()):
        x, y = cell_xy(n)
        out.append(f'<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" fill="url(#l0)" pointer-events="all">'
                   f'<title>{d["date"]:%b %d}: {d["count"]} contribution{"s" * (d["count"] != 1)}</title></rect>')
    for n in sorted(base):
        x, y = cell_xy(n)
        out.append(f'<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" '
                   f'fill="{fill_for(by_node[n]["level"], ink)}" pointer-events="all">'
                   f'<title>{by_node[n]["date"]:%b %d}: {by_node[n]["count"]} contribution{"s" * (by_node[n]["count"] != 1)}</title></rect>')

    # Board frame.
    fx, fy = PAD - 3, grid_top - 3
    out.append(f'<rect x="{fx}" y="{fy}" width="{grid_w + 6}" height="{ROWS * ROW - (ROW - CELL_H) + 6}" '
               f'fill="none" stroke="{accent}" stroke-width="2" opacity="0.85"/>')
    out.append(f'<text x="{PAD + grid_w}" y="{grid_top - 9}" text-anchor="end" font-size="11" '
               f'font-weight="bold" fill="{ink}" opacity="0.8">LANDSCAPE TETRIS</text>')

    # Falling + stacking pieces, clipped to the board.
    pieces: list[str] = []
    colours = SHAPE_COLOURS[name]
    blink_n = int(FLASH / 0.15) + 1
    for d in drops:
        sx = PAD + d["col"] * COL
        sy = grid_top + SPAWN_ROW * ROW
        lx, ly = PAD + d["col"] * COL, grid_top + d["land_row"] * ROW
        fall_dur = d["lock"] - d["spawn"]
        # Quick drop, then a short braking glide before it locks.
        tms = [d["spawn"], d["spawn"] + 0.30 * fall_dur, d["lock"]]
        pts = [(sx, sy), (sx, sy + 0.72 * (ly - sy)), (lx, ly)]
        cells = "".join(
            f'<rect x="{x * COL + 1}" y="{y * ROW + 1}" width="{CELL_W - 2}" height="{CELL_H - 2}" rx="2" '
            f'fill="{colours[d["name"]]}"/>' for x, y in shape_cells(d["name"], d["rot"]))
        shown = [(0, False), (d["spawn"], True), (d["lock"], False), (d["lock"] + 0.12, True)]
        for i in range(blink_n):
            shown.append((flash_start + i * 0.15, i % 2 == 1))
        shown.append((game_end, False))
        pieces.append(f'<g>{tl.motion(tms, pts)}<g opacity="0">{tl.show(shown)}{cells}</g></g>')
    out.append(f'<g clip-path="url(#boardClip)">{"".join(pieces)}</g>')

    # Signs.
    def sign(text: str, fill: str, shown: list[tuple[float, bool]]) -> str:
        w = len(text) * 7.2 + 12
        hx = PAD + grid_w / 2
        hy = grid_top + ROWS * ROW / 2 - 14
        return (f'<g opacity="0">{tl.show(shown)}'
                f'<rect x="{hx - w / 2:.0f}" y="{hy - 12}" width="{w:.0f}" height="16" fill="{bg}"/>'
                f'<text x="{hx}" y="{hy}" text-anchor="middle" font-size="12" font-weight="bold" '
                f'fill="{fill}">{text}</text></g>')
    out.append(sign("READY!", accent, [(0, True), (READY, False)]))
    out.append(sign("BOARD FULL!", ink, [(0, False), (game_over_at, True), (flash_start, False)]))

    # Month labels along the bottom, like the GitHub calendar.
    seen = set()
    for w, week in enumerate(weeks):
        month = next((d["date"] for d in week if d["date"].day == 1), None)
        first = week[0]["date"]
        if month is None and w == 0 and first.day <= 7:
            month = first
        if month and month.month not in seen:
            seen.add(month.month)
            out.append(f'<text x="{PAD + w * COL}" y="{grid_top + ROWS * ROW + 12}" font-size="10" '
                       f'fill="{ink}" opacity="0.75">{month:%b}</text>')

    out.append("</svg>")
    print(f"{name}: {len(drops)} pieces, loop {dur:.0f}s, game over after {len(drops)} drops")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use a fake calendar")
    ap.add_argument("--seed", type=int, help="override the daily piece sequence")
    args = ap.parse_args()
    today = datetime.now(TZ).date()

    if args.offline:
        weeks = fake_calendar(today)
    else:
        try:
            weeks = fetch_public_calendar()
        except Exception as err:  # page layout changed: fall back to the API
            print("public calendar failed, using API:", err)
            weeks = fetch_api_calendar(os.environ.get("ACCESS_TOKEN") or os.environ["GITHUB_TOKEN"])
    stats = tiles(weeks, today)
    print("tiles:", stats)

    seed = args.seed if args.seed is not None else today.toordinal()
    rng = random.Random(seed)
    base, by_node, drops = play(weeks, rng, len(weeks))
    for name, theme in THEMES.items():
        path = ROOT / f"tetris_{name}.svg"
        path.write_text(render(name, theme, weeks, stats, base, by_node, drops), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
