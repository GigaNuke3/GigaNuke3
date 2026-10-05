"""CODE CITY — A CITY BUILT BY CODE.

Replaces the old contribution bar chart. Each day of the current month is a
city lot: the day's contribution count decides the building archetype, height,
window density, lit windows and rooftop infrastructure. The city is fully
deterministic — the same contribution data always produces the same city —
and it is alive: cars drive the street, windows switch on and off, beacon
lights blink, a scanline sweeps the sky and today's lot is an active
construction site.

Architecture
------------
Data stays untouched (grid_common.fetch_public_calendar + the same
month-days/stats maths as the old chart). City generation is a pure
transformation, kept separate from rendering:

    month_days()          -> raw day records
    generate_city()       -> deterministic lot/building specs
    building_type_for()   -> archetype selection
    building_height_for() -> height from contribution tier
    activity_level()      -> human label for tooltips
    render_city()         -> SVG string (dark + light themes)

Output: graph_dark.svg + graph_light.svg (the same filenames the old chart
used, so the README and the workflow keep working without changes).
"""

import calendar
import sys
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from grid_common import TZ, fetch_public_calendar
from profile_card import PAD, THEMES, card

ROOT = Path(__file__).resolve().parent.parent
WIDTH = 900
HEIGHT = 364
RIGHT = WIDTH - PAD

# --- City layout -----------------------------------------------------------
HEADER_Y = 30
SUB_Y = 44
DIVIDER_Y = 52
STATS_TOP = 62
STATS_VALUE_Y = 80
STATS_LABEL_Y = 94
CITY_TOP = 106
BASELINE = 300
STREET_TOP = 302
LANE_Y = 316
DAY_LABEL_Y = 334

# --- Contribution -> architecture tiers ------------------------------------
TIER_HEIGHTS = [0, 18, 30, 46, 66, 92, 122]   # base building height, px
TIER_WIDTHS = [10, 12, 15, 18, 21, 24, 27]    # base building width, px
FLOOR_PITCH = 9                               # px per floor

ARCHETYPES = [
    # name          width  windows   roof       flags
    {"name": "narrow tower", "w": 0.62, "win": "vert",   "roof": "antenna"},
    {"name": "office block", "w": 0.95, "win": "grid",   "roof": "ac"},
    {"name": "residential",  "w": 0.72, "win": "grid",   "roof": "tank",   "balcony": True},
    {"name": "industrial",   "w": 0.90, "win": "sparse", "roof": "vent",   "pipes": True},
    {"name": "tech hub",     "w": 0.80, "win": "strips", "roof": "dish"},
    {"name": "brutalist",    "w": 0.85, "win": "sparse", "roof": "ledge",  "setback": True},
    {"name": "comms mast",   "w": 0.35, "win": "none",   "roof": "beacon", "lattice": True},
    {"name": "data center",  "w": 0.98, "win": "strips", "roof": "cooling", "pulse": True},
]

SIGNS = ["HQ", "GRID", "TECH", "DATA", "NODE", "CORE", "NET", "OPS"]

# Palette per theme: the city is grayscale + one orange accent.
CITY_PALETTE = {
    "dark": dict(
        ink="#f0f3f6", dim="#8b949e",
        key="#ffa657", faint="#232a33", building="#11151c", outline="#39424e",
        outline_hot="#ffa657", window_off="#202732", window_on="#d8dee7",
        street="#0c0f14", lane="#222933", sidewalk="#1a2028", crane="#ffa657",
    ),
    "light": dict(
        ink="#24292f", dim="#6e7781",
        key="#953800", faint="#d7dde4", building="#ffffff", outline="#2b3a4a",
        outline_hot="#953800", window_off="#e2e7ec", window_on="#4b5b6b",
        street="#e2e6eb", lane="#c3cbd4", sidewalk="#cfd6dd", crane="#953800",
    ),
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def month_days(weeks: list[list[dict]], today: date) -> list[dict]:
    """Every day of today's month: its count, or None if it hasn't come yet."""
    counts = {d["date"]: d["count"] for w in weeks for d in w}
    last = calendar.monthrange(today.year, today.month)[1]
    days = []
    for n in range(1, last + 1):
        d = today.replace(day=n)
        days.append({"date": d, "count": counts.get(d, 0) if d <= today else None})
    return days


def month_stats(days: list[dict], today: date) -> list[tuple[str, str]]:
    """The five city-sign metrics (same maths as the old chart)."""
    past = [d for d in days if d["count"] is not None]
    total = sum(d["count"] for d in past)
    best = max(past, key=lambda d: d["count"])
    streak = 0
    for d in reversed(past):
        if d["count"]:
            streak += 1
        elif d["date"] != today:
            break
    return [
        (f"{total:,}", "THIS MONTH"),
        (str(best["count"]), f"BEST DAY {best['date']:%b %d}".upper() if best["count"] else "BEST DAY"),
        (f"{total / len(past):.1f}", "DAILY AVG"),
        (str(sum(1 for d in past if d["count"])), "ACTIVE DAYS"),
        (f"{streak}d", "STREAK"),
    ]


def activity_level(count: int) -> tuple[int, str]:
    """Contribution count -> (tier, human label)."""
    if count <= 0:
        return 0, "EMPTY LOT"
    if count <= 2:
        return 1, "LOW ACTIVITY"
    if count <= 5:
        return 2, "MODERATE"
    if count <= 10:
        return 3, "ACTIVE"
    if count <= 20:
        return 4, "HIGH ACTIVITY"
    if count <= 30:
        return 5, "VERY HIGH"
    return 6, "LANDMARK DAY"


def frac(seed: int, salt: int) -> float:
    """Deterministic pseudo-random in [0, 1): same data -> same city."""
    x = (seed * 2654435761 + salt * 374761393) & 0xFFFFFFFF
    return (x % 1000) / 1000.0


# --------------------------------------------------------------------------
# City generation (pure data -> specs)
# --------------------------------------------------------------------------

def building_type_for(seed: int, tier: int) -> dict | None:
    if tier == 0:
        return None
    return ARCHETYPES[seed % len(ARCHETYPES)]


def building_height_for(seed: int, tier: int) -> int:
    if tier == 0:
        return 0
    base = TIER_HEIGHTS[tier]
    return max(10, round(base * (0.85 + 0.30 * frac(seed, 7))))


def building_width_for(seed: int, tier: int, arch: dict, lot_w: float) -> int:
    if tier == 0:
        return 8
    w = TIER_WIDTHS[tier] * arch["w"] + (frac(seed, 11) - 0.5) * 4
    return int(max(9, min(lot_w - 6, w)))


def generate_city(days: list[dict], today: date) -> list[dict]:
    """Deterministic city model: one lot per day."""
    n = len(days)
    lot_w = (RIGHT - PAD) / n
    city = []
    for i, d in enumerate(days):
        seed = d["date"].toordinal()
        count = d["count"]
        tier, label = activity_level(count) if count is not None else (0, "PLANNED")
        arch = building_type_for(seed, tier) if count else None
        bx = PAD + i * lot_w
        cx = bx + lot_w / 2
        h = building_height_for(seed, tier) if count else 0
        w = building_width_for(seed, tier, arch, lot_w) if arch else 0
        lit_ratio = min(0.85, 0.12 + 0.11 * tier + 0.08 * frac(seed, 13)) if count else 0
        hot_ratio = min(0.9, 0.25 + 0.10 * tier + 0.10 * frac(seed, 17)) if count else 0
        city.append({
            "date": d["date"], "day": d["date"].day, "count": count, "tier": tier,
            "label": label, "future": count is None, "seed": seed,
            "bx": bx, "cx": cx, "lot_w": lot_w, "w": w, "h": h, "arch": arch,
            "lit_ratio": lit_ratio, "hot_ratio": hot_ratio,
            "is_today": d["date"] == today,
        })
    return city


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _r(x, y, w, h, fill, stroke=None, sw=1, extra="") -> str:
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"{s} {extra}/>'


def _line(x1, y1, x2, y2, stroke, sw=1, extra="") -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'


def _blink(cx, cy, r, fill, dur="1.6s", begin="0s") -> str:
    return (f'<circle class="fx" cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}">'
            f'<animate attributeName="opacity" values="1;0;1" keyTimes="0;0.5;1" '
            f'dur="{dur}" begin="{begin}" repeatCount="indefinite"/></circle>')


def render_ground(p: dict, city: list[dict]) -> list[str]:
    out = []
    # Street plane.
    out.append(f'<rect x="{PAD}" y="{STREET_TOP}" width="{RIGHT - PAD}" height="{HEIGHT - STREET_TOP}" fill="{p["street"]}"/>')
    out.append(_line(PAD, STREET_TOP, RIGHT, STREET_TOP, p["sidewalk"], 1))
    # Lane dashes.
    dash = ""
    x = PAD + 8
    while x < RIGHT - 8:
        dash += f'<rect x="{x}" y="{LANE_Y}" width="10" height="1.5" fill="{p["lane"]}"/>'
        x += 26
    out.append(f'<g opacity="0.8">{dash}</g>')
    # Vertical lot grid (subtle pixel-grid detail).
    for lot in city:
        out.append(_line(lot["bx"], CITY_TOP, lot["bx"], BASELINE, p["faint"], 1))
    out.append(_line(PAD, BASELINE, RIGHT, BASELINE, p["faint"], 1))
    # Faint horizontal guides in the sky.
    for gy in (150, 200, 250):
        out.append(_line(PAD, gy, RIGHT, gy, p["faint"], 1))
    return out


def render_windows(spec: dict, p: dict, win_anims: list[str]) -> list[str]:
    """Window grid for one building, in absolute coordinates."""
    arch = spec["arch"]
    if arch is None or arch["win"] == "none":
        return []
    bx, top = spec["bx"], BASELINE - spec["h"]
    w, h = spec["w"], spec["h"]
    seed = spec["seed"]
    floors = max(1, h // FLOOR_PITCH)
    margin_x = 3
    usable = max(6, w - margin_x * 2)
    out = []

    def emit(x, y, ww, hh, f, c):
        lit = frac(seed, 40 + f * 13 + c * 7) < spec["lit_ratio"]
        hot = lit and frac(seed, 60 + f * 17 + c * 11) < spec["hot_ratio"]
        fill = p["window_off"]
        anim = ""
        if lit:
            fill = p["key"] if hot else p["window_on"]
            # A few windows slowly switch off and on again.
            if len(win_anims) < 12 and frac(seed, 500 + f * 13 + c * 7) < 0.55:
                dur = f"{8 + frac(seed, 700 + f * 13 + c * 7) * 8:.1f}s"
                begin = f"{frac(seed, 800 + f * 13 + c * 7) * 6:.1f}s"
                anim = (f'<animate attributeName="opacity" values="1;0.15;1" keyTimes="0;0.5;1" '
                        f'dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')
                win_anims.append("")  # reserve a slot in the global budget
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{ww:.1f}" height="{hh:.1f}" fill="{fill}">{anim}</rect>')

    style = arch["win"]
    if style == "strips":
        for f in range(floors):
            y = top + 3 + f * FLOOR_PITCH
            if y + 3 > BASELINE - 3:
                break
            emit(bx + 2, y, w - 4, 3, f, 0)
        return out

    if style == "vert":
        cols = 1 if w < 15 else 2
    elif style == "sparse":
        cols = max(1, usable // 9)
    else:  # grid
        cols = max(1, usable // 5)
    cw = usable / cols
    for f in range(floors):
        if style == "sparse" and f % 2:
            continue
        y = top + 3 + f * FLOOR_PITCH
        if y + 4 > BASELINE - 3:
            break
        for c in range(cols):
            x = bx + margin_x + c * cw + (cw - 3) / 2
            emit(x, y, 3, 4, f, c)
    return out


def render_roof(spec: dict, p: dict, blinks: list[str]) -> list[str]:
    arch = spec["arch"]
    if arch is None:
        return []
    cx, top = spec["cx"], BASELINE - spec["h"]
    w, seed = spec["w"], spec["seed"]
    kind = arch["roof"]
    out = []
    if kind == "antenna":
        out.append(_line(cx, top, cx, top - 12, p["outline"], 1))
        out.append(_line(cx - 3, top - 4, cx + 3, top - 4, p["outline"], 1))
        blinks.append(_blink(cx, top - 13, 1.6, p["key"], "1.8s", f"{frac(seed, 91) * 1.2:.2f}s"))
    elif kind == "vent":
        out.append(_r(cx - 5, top - 5, 4, 5, p["building"], p["outline"]))
        out.append(_r(cx + 1, top - 6, 4, 6, p["building"], p["outline"]))
    elif kind == "tank":
        out.append(_r(cx - 5, top - 7, 10, 7, p["building"], p["outline"]))
        out.append(_line(cx - 4, top - 7, cx - 4, top - 9, p["outline"], 1))
        out.append(_line(cx + 4, top - 7, cx + 4, top - 9, p["outline"], 1))
    elif kind == "dish":
        out.append(f'<circle cx="{cx:.1f}" cy="{top - 4:.1f}" r="4" fill="none" stroke="{p["outline"]}"/>')
        out.append(_line(cx, top - 4, cx, top + 1, p["outline"], 1))
    elif kind == "ac":
        out.append(_r(cx - 7, top - 4, 6, 4, p["building"], p["outline"]))
        out.append(_r(cx + 1, top - 4, 6, 4, p["building"], p["outline"]))
    elif kind == "ledge":
        out.append(_r(spec["bx"], top - 2, w, 2, p["building"], p["outline"]))
    elif kind == "cooling":
        for dx in (-6, 0, 6):
            out.append(f'<circle cx="{cx + dx:.1f}" cy="{top - 3:.1f}" r="2.4" fill="none" stroke="{p["outline"]}"/>')
        out.append(_line(cx - 9, top - 3, cx + 9, top - 3, p["outline"], 1))
        out.append(_r(cx + 9, top - 6, 2, 6, p["building"], p["outline"]))
    elif kind == "beacon":  # lattice mast handles its own light
        pass
    return out


def render_building(spec: dict, p: dict, blinks: list[str], pulses: list[str],
                    win_anims: list[str]) -> list[str]:
    out = []
    bx, cx = spec["bx"], spec["cx"]
    top = BASELINE - spec["h"]
    w, h = spec["w"], spec["h"]
    arch = spec["arch"]
    outline = p["outline_hot"] if spec["is_today"] else p["outline"]

    if arch is not None and arch.get("lattice"):
        # Comms mast: a triangular lattice with a beacon on top.
        out.append(_line(cx - 4, BASELINE, cx, top, outline, 1))
        out.append(_line(cx + 4, BASELINE, cx, top, outline, 1))
        out.append(_line(cx, BASELINE, cx, top, outline, 1))
        y = BASELINE - 7
        while y > top + 2:
            out.append(_line(cx - 3, y, cx + 3, y, outline, 1))
            y -= 7
        blinks.append(_blink(cx, top - 2, 1.8, p["key"], "1.4s", f"{frac(spec['seed'], 93) * 0.9:.2f}s"))
        return out

    # Solid building body.
    if arch is not None and arch.get("setback"):
        out.append(_r(bx, top + 7, w, h - 7, p["building"], outline))
        out.append(_r(bx + w * 0.15, top, w * 0.7, 9, p["building"], outline))
    else:
        out.append(_r(bx, top, w, h, p["building"], outline))

    # Balcony ledges (residential).
    if arch is not None and arch.get("balcony"):
        floors = max(1, h // FLOOR_PITCH)
        for f in range(1, floors):
            y = top + f * FLOOR_PITCH
            out.append(_line(bx + 1, y, bx + w - 1, y, outline, 1))

    # Side pipes (industrial).
    if arch is not None and arch.get("pipes"):
        out.append(_line(bx + 2, top, bx + 2, BASELINE, outline, 1))
        out.append(_line(bx + w - 2, top, bx + w - 2, BASELINE, outline, 1))

    # Windows.
    out += render_windows(spec, p, win_anims)

    # Rooftop infrastructure.
    out += render_roof(spec, p, blinks)

    # Signage on larger buildings.
    if spec["tier"] >= 4 and w >= 16 and arch is not None:
        sign = SIGNS[spec["seed"] % len(SIGNS)]
        out.append(_r(bx, top, w, 7, p["building"], None))
        out.append(f'<text x="{cx:.1f}" y="{top + 5.5:.1f}" text-anchor="middle" font-size="5" '
                   f'fill="{p["dim"]}" opacity="0.85">{escape(sign)}</text>')

    # Rooftop data pulse on technical buildings.
    if arch is not None and arch.get("pulse") and len(pulses) < 3:
        px = cx + w / 2 - 1
        pulses.append(
            f'<g class="fx" opacity="0.7"><animateTransform attributeName="transform" type="translate" '
            f'values="0,0;0,-{(top + 4) - (top - 10):.1f}" dur="3.2s" repeatCount="indefinite"/>'
            f'<rect x="{px:.1f}" y="{top - 10:.1f}" width="1.6" height="4" fill="{p["key"]}"/></g>')
    return out


def render_today(spec: dict, p: dict, city_top_limit: float) -> list[str]:
    """The current day as an active construction site."""
    cx = spec["cx"]
    top = BASELINE - max(spec["h"], 26)
    out = []
    # Tower crane in front of today's lot.
    mast_h = spec["h"] + 26
    mast_top = BASELINE - mast_h
    out.append(_line(cx - 2, BASELINE, cx - 2, mast_top, p["crane"], 1.4))
    out.append(_line(cx - 4, BASELINE, cx - 4, BASELINE - 10, p["crane"], 1.4))
    out.append(_line(cx - 7, mast_top, cx + 11, mast_top, p["crane"], 1.4))       # jib
    out.append(_line(cx - 7, mast_top, cx - 2, mast_top - 5, p["crane"], 1))      # tie
    out.append(_line(cx + 8, mast_top, cx + 8, mast_top + 9, p["crane"], 1))      # cable
    out.append(f'<rect x="{cx + 6.5:.1f}" y="{mast_top + 9:.1f}" width="3" height="3" fill="none" stroke="{p["crane"]}"/>')
    # Beacon + label above the site.
    out.append(_blink(cx, mast_top - 3, 2, p["key"], "1.1s"))
    out.append(f'<text x="{cx:.1f}" y="{mast_top - 9:.1f}" text-anchor="middle" font-size="8.5" '
               f'font-weight="bold" fill="{p["key"]}">TODAY</text>')
    # Construction barricade at street level.
    out.append(_r(cx - 6, BASELINE + 4, 12, 4, "none", p["key"], 1))
    out.append(_line(cx - 6, BASELINE + 6, cx + 6, BASELINE + 6, p["key"], 1))
    return out


def render_car(p: dict, lane: float, dur: str, begin: str, direction: int = 1) -> str:
    """A tiny car driving the street. direction=-1 flips it right-to-left."""
    y = lane
    body = (f'<g>'
            f'<rect x="0" y="{y}" width="13" height="4.5" rx="1" fill="{p["building"]}" stroke="{p["outline"]}" stroke-width="0.8"/>'
            f'<rect x="4" y="{y - 2.5}" width="5.5" height="2.8" fill="{p["building"]}" stroke="{p["outline"]}" stroke-width="0.8"/>'
            f'<rect x="2.5" y="{y + 4}" width="2" height="1.6" fill="{p["outline"]}"/>'
            f'<rect x="9" y="{y + 4}" width="2" height="1.6" fill="{p["outline"]}"/>'
            f'<rect x="12.2" y="{y + 1}" width="1" height="1" fill="{p["key"]}"/>'
            f'</g>')
    if direction == -1:
        body = f'<g transform="scale(-1,1)">{body}</g>'
    x0, x1 = ("-30", "930") if direction == 1 else ("930", "-30")
    return (f'<g class="fx"><animateTransform attributeName="transform" type="translate" '
            f'values="{x0},0;{x1},0" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>{body}</g>')


def render_city(name: str, days: list[dict], stats: list[tuple[str, str]], today: date) -> str:
    theme = THEMES[name]
    p = {**CITY_PALETTE[name], "bg": theme["bg"], "border": theme["border"]}
    city = generate_city(days, today)
    out: list[str] = []

    # --- Header ------------------------------------------------------------
    out.append(f'<text x="{PAD}" y="{HEADER_Y}" font-size="15" font-weight="bold" fill="{p["key"]}">// CODE CITY</text>')
    out.append(f'<text x="{RIGHT}" y="{HEADER_Y}" text-anchor="end" font-size="9.5" fill="{p["dim"]}">daily &#183; {today:%B %Y}</text>')
    out.append(f'<text x="{PAD}" y="{SUB_Y}" font-size="8" fill="{p["dim"]}" opacity="0.9">A CITY BUILT BY CODE</text>')
    out.append(_blink(RIGHT - 118, SUB_Y - 2.5, 1.8, p["key"], "1.2s"))
    out.append(f'<text x="{RIGHT}" y="{SUB_Y}" text-anchor="end" font-size="7.5" fill="{p["dim"]}">CITY STATUS: ONLINE</text>')
    out.append(_line(PAD, DIVIDER_Y, RIGHT, DIVIDER_Y, p["border"], 1))

    # --- Stats -------------------------------------------------------------
    tile_w = (RIGHT - PAD) / len(stats)
    for i, (value, label) in enumerate(stats):
        x = PAD + i * tile_w
        out.append(f'<rect x="{x:.0f}" y="{STATS_TOP}" width="3" height="14" fill="{p["key"]}"/>')
        out.append(f'<text x="{x + 8:.0f}" y="{STATS_VALUE_Y}" font-size="19" font-weight="bold" fill="{p["ink"]}">{escape(value)}</text>')
        out.append(f'<text x="{x + 8:.0f}" y="{STATS_LABEL_Y}" font-size="8" fill="{p["dim"]}">{escape(label)}</text>')

    # --- Ground + sky grid -------------------------------------------------
    out += render_ground(p, city)

    # --- Buildings ---------------------------------------------------------
    blinks: list[str] = []
    pulses: list[str] = []
    win_anims: list[str] = []
    for i, spec in enumerate(city):
        if spec["future"]:
            # Planned zone: dashed empty lot.
            out.append(f'<rect x="{spec["bx"] + 3:.1f}" y="{BASELINE - 14:.1f}" width="{spec["lot_w"] - 10:.1f}" height="14" '
                       f'fill="none" stroke="{p["faint"]}" stroke-width="1" stroke-dasharray="2 2"/>')
            continue
        if spec["tier"] == 0:
            # Empty lot: slab + a tiny utility box.
            out.append(_r(spec["bx"] + 2, BASELINE - 3, spec["lot_w"] - 8, 3, p["building"], p["faint"]))
            out.append(_r(spec["cx"] - 3, BASELINE - 9, 6, 6, "none", p["faint"], 1))
            continue
        # Tooltip (native, city-formatted).
        tip = (f'{spec["date"]:%b %d, %Y}\n{spec["count"]} CONTRIBUTIONS\n{spec["label"]}')
        out.append(f'<g><title>{escape(tip)}</title>')
        out.append(f'<rect x="{spec["bx"] + 1:.1f}" y="{CITY_TOP:.1f}" width="{spec["lot_w"] - 2:.1f}" '
                   f'height="{BASELINE - CITY_TOP:.1f}" fill="transparent"/>')
        # One-time "construction settle": the building is fully visible in
        # static renderers and settles 4px down into its foundations when the
        # card loads. Static-first, animation as an enhancement only.
        begin = f"{0.10 + i * 0.055:.2f}s"
        out.append(f'<g><animateTransform attributeName="transform" type="translate" '
                   f'values="0,4;0,0" begin="{begin}" dur="0.5s" fill="freeze"/>')
        out += render_building(spec, p, blinks, pulses, win_anims)
        out.append('</g>')
        out.append('</g>')

    # --- Today's construction site ----------------------------------------
    today_spec = next((s for s in city if s["is_today"]), None)
    if today_spec is not None:
        out += render_today(today_spec, p, CITY_TOP)

    # --- Ambient life ------------------------------------------------------
    out += blinks
    out += pulses
    out.append(render_car(p, LANE_Y - 6, "55s", "0s", 1))
    out.append(render_car(p, LANE_Y + 4, "80s", "4s", -1))
    out.append(render_car(p, LANE_Y - 1, "120s", "9s", 1))

    # Scanline sweeping the sky.
    out.append(f'<rect class="fx" x="0" y="{CITY_TOP}" width="1.5" height="{BASELINE - CITY_TOP}" fill="{p["ink"]}" opacity="0.03">'
               f'<animateTransform attributeName="transform" type="translate" values="0,0;{WIDTH},0" '
               f'dur="38s" repeatCount="indefinite"/></rect>')

    # --- Day numbers -------------------------------------------------------
    for spec in city:
        fill = p["key"] if spec["is_today"] else p["dim"]
        out.append(f'<text x="{spec["cx"]:.1f}" y="{DAY_LABEL_Y}" text-anchor="middle" font-size="7.5" '
                   f'fill="{fill}" opacity="{1 if spec["is_today"] else 0.75}">{spec["day"]}</text>')

    return card(theme, WIDTH, HEIGHT, "BAY 02 · SETTLEMENT · 1 MO", out)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use a fake month")
    args = ap.parse_args()

    today = datetime.now(TZ).date()
    if args.offline:
        # A deterministic fake month so the renderer can be tested offline.
        days = []
        for n in range(1, calendar.monthrange(today.year, today.month)[1] + 1):
            d = today.replace(day=n)
            seed = d.toordinal()
            count = 0 if n > today.day else [0, 1, 3, 6, 12, 24, 40][seed % 7]
            days.append({"date": d, "count": count})
    else:
        try:
            weeks = fetch_public_calendar()
        except Exception as err:  # keep yesterday's city rather than fail the workflow
            print("calendar fetch failed, leaving the city as it is:", err)
            sys.exit(0)
        days = month_days(weeks, today)

    stats = month_stats(days, today)
    print(f"{today:%B %Y}: {sum(d['count'] or 0 for d in days)} contributions; stats: {stats}")
    for name in ("dark", "light"):
        path = ROOT / f"graph_{name}.svg"
        path.write_text(render_city(name, days, stats, today), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
