"""MISSION CONTROL — CONTRIBUTION ACTIVITY.

The last four months of GitHub activity are rendered as a multi-stage
launch mission: the vertical activity timeline becomes a diagonal flight
trajectory (lower-left -> upper-right, ~15 deg), the months become mission
checkpoints, and a Saturn V-inspired three-stage rocket travels the
trajectory as a looping cinematic launch sequence.

The loop (one shared SMIL timeline, ~13.8 s) is an explicit state machine:

    T-5 .. T-1  countdown (rocket on the pad, engines off)
    IGNITION    launch flash, engines ignite
    LIFTOFF     accelerating ascent along the trajectory
    STAGE 1 SEPARATION   first stage drifts back, rotates and fades
    SECOND-STAGE BURN    upper stages re-ignite and accelerate
    STAGE 2 SEPARATION   second stage drifts back, rotates and fades
    UPPER STAGE          third stage + payload, decelerating
    APOGEE / HOLD        engines fade, MISSION COMPLETE
    FADE OUT             rocket disappears quietly
    RESET                hidden reset, then T-5 again

Everything is static-safe: renderers that ignore SMIL see the rocket on
the launch pad at T-5 with the full mission log readable.

Output: activity_dark.svg + activity_light.svg.
"""

import calendar
import html
import math
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from grid_common import TZ, Timeline
from profile_card import PAD, THEMES, USER

ROOT = Path(__file__).resolve().parent.parent
MONTHS = 4
WIDTH = 900
HEIGHT = 472

# --- Geometry --------------------------------------------------------------
P0 = (64, 328)                 # launch pad / trajectory start (lower-left)
P1 = (856, 118)                # trajectory end / apogee (upper-right)
DX, DY = P1[0] - P0[0], P1[1] - P0[1]
ANGLE = math.degrees(math.atan2(-DY, DX))       # ~14.85 deg above horizontal
ALPHA = 90 - ANGLE                              # rotation applied to the nose-up rocket
ROCKET_LEN = 142
TRAVEL = math.hypot(DX, DY) - ROCKET_LEN        # distance the tail travels
CHECKPOINTS = [0.20, 0.42, 0.64]                # JUL / AUG / SEP along the line

BLOCK_Y = 344
BLOCK_H = 108
BLOCK_W = 196
BLOCK_GAP = 20

# --- Mission clock (seconds, one shared loop) ------------------------------
D = 13.8
T5, T4, T3, T2, T1 = 0.0, 0.9, 1.8, 2.7, 3.6
IGN = 4.5
LIFTOFF = 5.0
SEP1 = 7.0
SEP1_END = 7.7
SEP2 = 9.4
SEP2_END = 10.1
APOGEE = 11.4
HOLD_END = 12.8
FADE_END = 13.5
RESET_END = D

# --- Palette ---------------------------------------------------------------
CITY_EXTRA = {
    "dark": dict(rocket_body="#2a313b", rocket_shade="#1c222a", block_bg="#10141a",
                 block_stroke="#232a33", exhaust_inner="#ffe9c9"),
    "light": dict(rocket_body="#ffffff", rocket_shade="#dfe4ea", block_bg="#ffffff",
                  block_stroke="#c6cdd6", exhaust_inner="#ffffff"),
}


def palette(theme: dict, name: str) -> dict:
    p = {"ink": theme["text"], "bg": theme["bg"], "key": theme["key"],
         "dim": theme["dim"], "value": theme["value"]}
    p.update(CITY_EXTRA[name])
    return p


# --------------------------------------------------------------------------
# Data (unchanged from the previous activity card)
# --------------------------------------------------------------------------

def fetch_month(year: int, month: int) -> list[dict]:
    """The activity items GitHub lists for one month on the profile."""
    last = calendar.monthrange(year, month)[1]
    url = (f"https://github.com/{USER}?action=show&controller=profiles&tab=contributions"
           f"&from={year}-{month:02d}-01&to={year}-{month:02d}-{last}&user_id={USER}")
    req = urllib.request.Request(url, headers={"X-Requested-With": "XMLHttpRequest",
                                               "User-Agent": "profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8")
    start = page.find("contribution-activity-listing")
    if start < 0:
        raise RuntimeError("activity section not found; the profile page layout may have changed")
    end = page.find("Show more activity", start)
    section = page[start:end if end > 0 else None]

    def text(fragment: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()

    items = []
    for block in re.split(r'class="TimelineItem"', section)[1:]:
        head = (re.search(r"<summary[^>]*>\s*<span[^>]*>(.*?)</span>", block, re.S)
                or re.search(r"<h4[^>]*>(.*?)</h4>", block, re.S))
        summary = text(head.group(1)) if head else "Activity"
        summary = re.sub(r"\s+Public$", "", summary)
        rows = []
        for li in re.findall(r"<li\b.*?</li>", block, re.S):
            repo = re.search(r'data-hovercard-type="repository"[^>]*href="/([^"]+)"', li)
            if not repo:
                continue
            count = re.search(r">\s*(\d+) commits?\s*<", li)
            lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', li)
            when = re.search(r"This contribution was made on ([A-Z][a-z]{2} \d+)", li)
            rows.append({"repo": repo.group(1), "count": int(count.group(1)) if count else None,
                         "lang": lang.group(1).strip() if lang else None,
                         "date": when.group(1) if when else None})
        if not rows:  # e.g. a pull request item: the repo is only in the summary
            repo = re.search(r'data-hovercard-type="repository"[^>]*href="/([^\"]+)"', block)
            if repo and repo.group(1) not in summary:
                rows.append({"repo": repo.group(1), "count": None, "lang": None, "date": None})
        items.append({"summary": summary, "rows": rows})
    return items


def recent_months(today) -> list[tuple[int, int]]:
    y, m = today.year, today.month
    out = []
    for _ in range(MONTHS):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def totals(months: list[dict]) -> list[tuple[str, str]]:
    commits = repos_made = prs = 0
    active = set()
    for mo in months:
        for it in mo["items"]:
            s = it["summary"].lower()
            if "commit" in s:
                commits += sum(r["count"] or 0 for r in it["rows"])
                active |= {r["repo"] for r in it["rows"]}
            elif s.startswith("created") and "repositor" in s:
                n = re.search(r"created (\d+) repositor", s)
                repos_made += int(n.group(1)) if n else 1
            elif "pull request" in s and "first" not in s:
                prs += 1
    return [(str(commits), "COMMITS"), (str(len(active)), "ACTIVE REPOS"),
            (str(repos_made), "REPOS CREATED"), (str(prs), "PULL REQUESTS")]


def month_stats(mo: dict) -> tuple[int, int, int, int]:
    commits, created, prs = 0, 0, 0
    active = set()
    for it in mo["items"]:
        s = it["summary"].lower()
        if "commit" in s:
            commits += sum(r["count"] or 0 for r in it["rows"])
            active |= {r["repo"] for r in it["rows"]}
        elif s.startswith("created") and "repositor" in s:
            n = re.search(r"created (\d+) repositor", s)
            created += int(n.group(1)) if n else 1
        elif "pull request" in s and "first" not in s:
            prs += 1
    return commits, len(active), created, prs


def short(repo: str, owner: str = USER) -> str:
    name = repo.split("/", 1)[1] if repo.startswith(owner + "/") else repo
    return name if len(name) <= 34 else name[:33] + "…"


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# --------------------------------------------------------------------------
# Mission log (ground stations)
# --------------------------------------------------------------------------

def block_lines(mo: dict) -> list[tuple[str, str]]:
    lines = []
    for it in mo["items"]:
        lines.append(("item", it["summary"]))
        for r in it["rows"][:2]:
            if r["count"] is not None:
                lines.append(("repo", f"{short(r['repo'])} — {r['count']} commit{'s' if r['count'] != 1 else ''}"))
            else:
                meta = " · ".join(v for v in (r["lang"], r["date"]) if v)
                lines.append(("repo", f"{short(r['repo'])}" + (f" — {meta}" if meta else "")))
        if len(it["rows"]) > 2:
            lines.append(("more", f"+{len(it['rows']) - 2} more"))
    if len(lines) > 8:
        lines = lines[:7] + [("more", f"+{len(lines) - 7} more")]
    return lines


def month_tooltip(mo: dict) -> str:
    label = f"{calendar.month_name[mo['month']].upper()} {mo['year']}"
    c, a, cr, pr = month_stats(mo)
    parts = [label, f"COMMITS {c} · ACTIVE REPOS {a} · CREATED {cr} · PR {pr}", ""]
    for it in mo["items"]:
        parts.append(f"✦ {it['summary']}")
        for r in it["rows"]:
            if r["count"] is not None:
                parts.append(f"  {short(r['repo'])} — {r['count']} commits")
            else:
                meta = " · ".join(v for v in (r["lang"], r["date"]) if v)
                parts.append(f"  {short(r['repo'])}" + (f" — {meta}" if meta else ""))
    return "\n".join(parts)


# --------------------------------------------------------------------------
# SMIL helpers (everything runs on the shared loop of `D` seconds)
# --------------------------------------------------------------------------

def _r(x, y, w, h, fill, stroke=None, sw=1, extra="") -> str:
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"{s} {extra}/>'


def _poly(points, fill, stroke=None, sw=1) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<polygon points="{pts}" fill="{fill}"{s}/>'


def opacity_anim(stops: list[tuple[float, float]]) -> str:
    vals = ";".join(f"{v:.3f}" for _, v in stops)
    keys = ";".join(f"{t / D:.5f}" for t, _ in stops)
    return (f'<animate attributeName="opacity" values="{vals}" keyTimes="{keys}" '
            f'calcMode="linear" dur="{D}s" repeatCount="indefinite"/>')


def translate_anim(pairs: list[tuple[float, tuple[float, float]]]) -> str:
    vals = ";".join(f"{x:.1f},{y:.1f}" for _, (x, y) in pairs)
    keys = ";".join(f"{t / D:.5f}" for t, _ in pairs)
    return (f'<animateTransform attributeName="transform" type="translate" values="{vals}" '
            f'keyTimes="{keys}" calcMode="linear" dur="{D}s" repeatCount="indefinite"/>')


def rotate_anim(stops: list[tuple[float, float]], pivot: tuple[float, float]) -> str:
    vals = ";".join(f"{deg:.1f} {pivot[0]} {pivot[1]}" for _, deg in stops)
    keys = ";".join(f"{t / D:.5f}" for t, _ in stops)
    return (f'<animateTransform attributeName="transform" type="rotate" values="{vals}" '
            f'keyTimes="{keys}" calcMode="linear" dur="{D}s" repeatCount="indefinite"/>')


def scale_anim(stops: list[tuple[float, float]]) -> str:
    vals = ";".join(f"{s:.2f},{s:.2f}" for _, s in stops)
    keys = ";".join(f"{t / D:.5f}" for t, _ in stops)
    return (f'<animateTransform attributeName="transform" type="scale" values="{vals}" '
            f'keyTimes="{keys}" calcMode="linear" dur="{D}s" repeatCount="indefinite"/>')


def pos_s(t: float) -> float:
    """Position along the trajectory (0 = pad, 1 = apogee)."""
    if t < IGN:
        return 0.0
    if t < LIFTOFF:
        return 0.012 * (t - IGN) / (LIFTOFF - IGN)
    if t < SEP1:
        p = (t - LIFTOFF) / (SEP1 - LIFTOFF)
        return 0.012 + (0.35 - 0.012) * p * p
    if t < SEP1_END:
        return 0.35 + 0.07 * (t - SEP1) / (SEP1_END - SEP1)
    if t < SEP2:
        p = (t - SEP1_END) / (SEP2 - SEP1_END)
        return 0.42 + 0.28 * p * p
    if t < SEP2_END:
        return 0.70 + 0.06 * (t - SEP2) / (SEP2_END - SEP2)
    if t < APOGEE:
        p = (t - SEP2_END) / (APOGEE - SEP2_END)
        return 0.76 + 0.24 * (1 - (1 - p) * (1 - p))
    return 1.0


# --------------------------------------------------------------------------
# Rocket drawing (local coords: nose up at -y, S-IC engine base at origin)
# --------------------------------------------------------------------------

def s1_shapes(p: dict) -> str:
    body, out, shade = p["rocket_body"], p["ink"], p["rocket_shade"]
    g = [_r(-13, -42, 26, 42, body, out),
         _r(-19, -13, 6, 13, body, out),          # fins
         _r(13, -13, 6, 13, body, out)]
    for cx in (-11, -6.5, -2, 2.5, 7):            # engine cluster
        g.append(_r(cx, 0, 4.5, 5, shade, out, 0.8))
    g.append(_r(-13, -49, 26, 7, shade, out))     # interstage 1
    return "".join(g)


def s2_shapes(p: dict) -> str:
    body, out, shade = p["rocket_body"], p["ink"], p["rocket_shade"]
    g = [_r(-11, -83, 22, 34, body, out)]
    for cx in (-7.5, -3, 1.5, 6):
        g.append(_r(cx, -49, 3.4, 4, shade, out, 0.8))
    g.append(_r(-11, -88, 22, 5, shade, out))     # interstage 2
    return "".join(g)


def s3_payload_shapes(p: dict) -> str:
    body, out = p["rocket_body"], p["ink"]
    g = [_r(-8, -112, 16, 24, body, out)]
    for cx in (-5, -1, 3):
        g.append(_r(cx, -88, 2.6, 4, p["rocket_shade"], out, 0.8))
    g.append(_r(-5, -128, 10, 16, body, out))      # payload section
    g.append(_poly([(0, -142), (-5, -128), (5, -128)], body, out))  # nose cone
    return "".join(g)


def exhaust(p: dict, flame: float, n: int, seed: int, scale_stops: list[tuple[float, float]]) -> str:
    """Flame + particles pointing down (+y) from the local engine base."""
    key, inner = p["key"], p["exhaust_inner"]
    out = [
        f'<g>{scale_anim(scale_stops)}'
        f'<g><animate attributeName="opacity" values="0.85;1;0.85" dur="0.5s" repeatCount="indefinite"/>'
        f'{_poly([(0, 0), (-7, flame), (7, flame)], key)}'
        f'{_poly([(0, 0), (-3, flame * 0.62), (3, flame * 0.62)], inner)}</g></g>',
    ]
    for k in range(n):
        px = ((k * 7 + seed) % 13) - 6
        py = flame + 4 + (k % 3) * 5
        begin = f"{0.15 * k:.2f}s"
        out.append(
            f'<rect x="{px - 1.1:.1f}" y="{py:.1f}" width="2.2" height="3" fill="{key}" opacity="0.9">'
            f'<animateTransform attributeName="transform" type="translate" values="0,0;0,48" '
            f'dur="1.3s" begin="{begin}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0.9;0" dur="1.3s" begin="{begin}" repeatCount="indefinite"/>'
            f'</rect>')
    return "".join(out)


def exhaust_intensity(commits: int) -> tuple[float, int]:
    if commits < 30:
        return 22.0, 3
    if commits < 70:
        return 30.0, 5
    if commits < 140:
        return 38.0, 7
    return 46.0, 9


def stage_labels_local(p: dict) -> str:
    out = []
    for label, ly in (("S-IC", -21), ("S-II", -66), ("S-IVB", -100), ("PAYLOAD", -120)):
        out.append(f'<text x="17" y="{ly}" font-size="6.5" fill="{p["dim"]}">{label}</text>')
    return "".join(out)


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def render(name: str, theme: dict, months: list[dict], stats: list[tuple[str, str]]) -> str:
    p = palette(theme, name)
    tl = Timeline(D)
    out: list[str] = []
    right = WIDTH - PAD

    # --- Header ------------------------------------------------------------
    out.append(f'<text x="{PAD}" y="30" font-size="15" font-weight="bold" fill="{p["key"]}">MISSION CONTROL</text>')
    out.append(f'<text x="660" y="30" text-anchor="end" font-size="9.5" fill="{p["dim"]}">CONTRIBUTION ACTIVITY &#183; LAST {MONTHS} MONTHS</text>')
    out.append(f'<circle cx="{PAD + 2}" cy="41" r="1.8" fill="{p["key"]}">'
               f'<animate attributeName="opacity" values="1;0.15;1" dur="1.4s" repeatCount="indefinite"/></circle>')
    out.append(f'<text x="660" y="44" text-anchor="end" font-size="7.5" fill="{p["dim"]}">SYSTEMS ONLINE</text>')
    out.append(f'<line x1="{PAD}" y1="52" x2="{right}" y2="52" stroke="{p["block_stroke"]}"/>')

    # --- Mission status line (decorative state machine) --------------------
    statuses = [
        ("COUNTDOWN", p["dim"], [(0, True), (IGN, False), (D, False)], 1),
        ("IGNITION", p["key"], [(0, False), (IGN, True), (LIFTOFF, False), (D, False)], 0),
        ("ASCENT", p["dim"], [(0, False), (LIFTOFF, True), (SEP1, False), (SEP1_END, True), (SEP2, False), (D, False)], 0),
        ("STAGE SEPARATION", p["key"], [(0, False), (SEP1, True), (SEP1_END, False), (SEP2, True), (SEP2_END, False), (D, False)], 0),
        ("ORBITAL INSERTION", p["dim"], [(0, False), (SEP2_END, True), (APOGEE, False), (D, False)], 0),
        ("MISSION COMPLETE", p["key"], [(0, False), (APOGEE, True), (FADE_END, False), (D, False)], 0),
        ("PREPARING LAUNCH", p["dim"], [(0, False), (FADE_END, True), (D, False)], 0),
    ]
    for text, fill, changes, base in statuses:
        out.append(f'<g opacity="{base}">{tl.show(changes)}'
                   f'<text x="36" y="44" font-size="8" fill="{fill}">MISSION STATUS: {text}</text></g>')

    # --- Countdown (HUD corner) -------------------------------------------
    counts = [
        ("T-5", 12, [(0, True), (T4, False), (D, False)], 1),
        ("T-4", 12, [(0, False), (T4, True), (T3, False), (D, False)], 0),
        ("T-3", 12, [(0, False), (T3, True), (T2, False), (D, False)], 0),
        ("T-2", 12, [(0, False), (T2, True), (T1, False), (D, False)], 0),
        ("T-1", 12, [(0, False), (T1, True), (IGN, False), (D, False)], 0),
        ("IGNITION", 10, [(0, False), (IGN, True), (LIFTOFF + 0.4, False), (D, False)], 0),
    ]
    for text, size, changes, base in counts:
        out.append(f'<g opacity="{base}">{tl.show(changes)}'
                   f'<text x="872" y="30" text-anchor="end" font-size="{size}" font-weight="bold" fill="{p["key"]}">'
                   f'{text}<animate attributeName="opacity" values="1;0.55;1" dur="0.45s" repeatCount="indefinite"/></text></g>')

    # --- Telemetry tiles ---------------------------------------------------
    for i, (value, label) in enumerate(stats):
        x = PAD + i * 158
        out.append(f'<rect x="{x:.0f}" y="64" width="3" height="12" fill="{p["key"]}"/>')
        out.append(f'<text x="{x + 8:.0f}" y="78" font-size="19" font-weight="bold" fill="{p["ink"]}">{escape(value)}</text>')
        out.append(f'<text x="{x + 8:.0f}" y="92" font-size="8" fill="{p["dim"]}">{escape(label)}</text>')

    # --- Apogee frame (top-right destination) ------------------------------
    out.append(f'<rect x="664" y="56" width="208" height="132" fill="none" stroke="{p["block_stroke"]}" stroke-dasharray="3 3"/>')
    out.append(f'<text x="670" y="66" font-size="6.5" fill="{p["dim"]}">APOGEE 01</text>')
    out.append(f'<g opacity="0">{tl.show([(0, False), (APOGEE, True), (FADE_END, False)])}'
               f'<text x="856" y="100" text-anchor="end" font-size="8" font-weight="bold" fill="{p["key"]}">MISSION COMPLETE</text></g>')

    # --- Flight trajectory + checkpoints -----------------------------------
    out.append(f'<line x1="{P0[0]}" y1="{P0[1]}" x2="{P1[0]}" y2="{P1[1]}" stroke="{p["key"]}" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>')
    # Trajectory brightens once at apogee.
    out.append(f'<line x1="{P0[0]}" y1="{P0[1]}" x2="{P1[0]}" y2="{P1[1]}" stroke="{p["key"]}" stroke-width="2.5" opacity="0">'
               f'{opacity_anim([(0, 0), (APOGEE, 0), (APOGEE + 0.08, 0.55), (APOGEE + 0.7, 0), (D, 0)])}</line>')
    month_names = [calendar.month_name[mo["month"]][:3].upper() for mo in months]
    dots = []
    for i, t in enumerate(CHECKPOINTS):
        x = P0[0] + t * DX
        y = P0[1] + t * DY
        dots.append((x, y))
        out.append(f'<rect x="{x - 2.5:.1f}" y="{y - 2.5:.1f}" width="5" height="5" fill="{p["key"]}"/>')
        out.append(f'<text x="{x - 8:.1f}" y="{y - 8:.1f}" text-anchor="end" font-size="6.5" fill="{p["dim"]}">{month_names[i]}</text>')

    # --- Leaders: ground stations -> checkpoints ---------------------------
    block_cxs = [PAD + BLOCK_W / 2 + i * (BLOCK_W + BLOCK_GAP) for i in range(MONTHS)]
    leader_targets = list(dots) + [P1]
    for cx, (tx, ty) in zip(block_cxs, leader_targets):
        out.append(f'<line x1="{cx:.1f}" y1="{BLOCK_Y - 2}" x2="{tx:.1f}" y2="{ty:.1f}" '
                   f'stroke="{p["key"]}" stroke-width="1" stroke-dasharray="2 3" opacity="0.45"/>')

    # --- Launch pad --------------------------------------------------------
    out.append(f'<line x1="{P0[0]}" y1="{P0[1] - 28}" x2="{P0[0]}" y2="{P0[1]}" stroke="{p["dim"]}" stroke-width="1.4"/>')
    out.append(f'<line x1="{P0[0] - 8}" y1="{P0[1] - 22}" x2="{P0[0]}" y2="{P0[1] - 22}" stroke="{p["dim"]}" stroke-width="1.2"/>')
    out.append(f'<line x1="{P0[0] - 12}" y1="{P0[1]}" x2="{P0[0] + 12}" y2="{P0[1]}" stroke="{p["dim"]}" stroke-width="1.2"/>')
    out.append(f'<circle cx="{P0[0]}" cy="{P0[1] - 30}" r="1.6" fill="{p["key"]}">'
               f'<animate attributeName="opacity" values="1;0.15;1" dur="1.1s" repeatCount="indefinite"/></circle>')
    out.append(f'<text x="{P0[0] + 14}" y="{P0[1] + 14}" font-size="6.5" fill="{p["dim"]}">PAD 01</text>')

    # --- Sampled motion ----------------------------------------------------
    step = 0.08
    times = [i * step for i in range(int(D / step) + 1)]
    mover_pairs = [(t, (0.0, -pos_s(t) * TRAVEL)) for t in times]
    follower_pairs = []
    for t in times:
        sf = max(0.0, pos_s(t - 0.35))
        follower_pairs.append((t, (P0[0] + sf * DX, P0[1] + sf * DY)))
    shake_pairs = []
    for t in times:
        if T2 - 0.15 <= t < IGN:
            k = int(t / 0.06)
            ox = 1.3 if k % 2 == 0 else -1.3
            oy = 0.8 if (k // 2) % 2 == 0 else -0.8
            shake_pairs.append((t, (ox, oy)))
        else:
            shake_pairs.append((t, (0.0, 0.0)))

    # --- The rocket --------------------------------------------------------
    flame, n_particles = exhaust_intensity(int(stats[0][0]))
    s1 = s1_shapes(p)
    s2 = s2_shapes(p)
    s3 = s3_payload_shapes(p)

    rocket = [
        f'<g transform="translate({P0[0]},{P0[1]}) rotate({ALPHA:.2f})">',
        # Vehicle fade-out at the end of the mission (hidden reset).
        f'{opacity_anim([(0, 1), (HOLD_END, 1), (FADE_END, 0), (D, 0)])}',
        # Main motion: travels forward along the rocket axis (local -y).
        f'<g>{translate_anim(mover_pairs)}',
        # Camera shake during engine start-up.
        f'<g>{translate_anim(shake_pairs)}',
        # Stage 1 (detaches at SEP1).
        f'<g>{opacity_anim([(0, 1), (SEP1 + 1.2, 1), (SEP1 + 2.4, 0), (D, 0)])}'
        f'<g>{translate_anim([(0, (0, 0)), (SEP1, (0, 0)), (SEP1 + 2.4, (0, 34)), (D, (0, 34))])}'
        f'<g>{rotate_anim([(0, 0), (SEP1, 0), (SEP1 + 2.4, 16), (D, 16)], (0, -21))}{s1}</g></g></g>',
        # Stage 2 (detaches at SEP2).
        f'<g>{opacity_anim([(0, 1), (SEP2 + 1.0, 1), (SEP2 + 2.2, 0), (D, 0)])}'
        f'<g>{translate_anim([(0, (0, 0)), (SEP2, (0, 0)), (SEP2 + 2.2, (0, 28)), (D, (0, 28))])}'
        f'<g>{rotate_anim([(0, 0), (SEP2, 0), (SEP2 + 2.2, 15), (D, 15)], (0, -66))}{s2}</g></g></g>',
        # Third stage + payload (rides to apogee).
        f'<g>{s3}</g>',
        # Stage exhausts (cut off / reignited per the state machine).
        f'<g opacity="0">{opacity_anim([(0, 0), (T2, 0), (T1, 0.25), (IGN, 0.85), (SEP1 - 0.05, 0.85), (SEP1 + 0.1, 0), (D, 0)])}'
        f'{exhaust(p, flame, n_particles, 3, [(0, 1), (LIFTOFF, 1), (LIFTOFF + 0.4, 1.4), (SEP1, 1.4), (SEP1 + 0.1, 1), (D, 1)])}</g>',
        f'<g opacity="0" transform="translate(0,-49)">{opacity_anim([(0, 0), (SEP1 + 0.08, 0), (SEP1 + 0.25, 0.85), (SEP2 - 0.05, 0.85), (SEP2 + 0.1, 0), (D, 0)])}'
        f'{exhaust(p, max(20, flame * 0.6), 3, 5, [(0, 1), (SEP1 + 0.25, 1), (SEP1 + 0.5, 1.35), (SEP2, 1.35), (SEP2 + 0.1, 1), (D, 1)])}</g>',
        f'<g opacity="0" transform="translate(0,-88)">{opacity_anim([(0, 0), (SEP2 + 0.08, 0), (SEP2 + 0.25, 0.75), (APOGEE, 0.75), (HOLD_END, 0), (D, 0)])}'
        f'{exhaust(p, max(14, flame * 0.4), 2, 7, [(0, 1), (SEP2 + 0.3, 1), (SEP2 + 0.6, 1.2), (APOGEE, 1.2), (HOLD_END, 1), (D, 1)])}</g>',
        # Engine glow + ignition flash at the S-IC base.
        f'<circle cx="0" cy="0" r="9" fill="{p["key"]}" opacity="0">'
        f'{opacity_anim([(0, 0), (T3, 0), (T1, 0.22), (IGN, 0.6), (SEP1, 0.6), (SEP1 + 0.12, 0), (D, 0)])}</circle>',
        f'<polygon points="0,-6 -9,4 0,18 9,4" fill="{p["key"]}" opacity="0">'
        f'{opacity_anim([(0, 0), (IGN, 0), (IGN + 0.05, 1), (IGN + 0.4, 0), (D, 0)])}</polygon>',
        # Separation flashes.
        f'<g opacity="0">{tl.show([(0, False), (SEP1 - 0.05, True), (SEP1 + 0.25, False), (D, False)])}'
        f'{_r(-13, -50, 26, 2, p["key"])}</g>',
        f'<g opacity="0">{tl.show([(0, False), (SEP2 - 0.05, True), (SEP2 + 0.25, False), (D, False)])}'
        f'{_r(-11, -89, 22, 2, p["key"])}</g>',
        # Stage labels.
        stage_labels_local(p),
        '</g></g></g>',
    ]
    out.append("".join(rocket))

    # --- Trajectory follower (signal chasing the rocket) -------------------
    out.append(f'<g opacity="0">{tl.show([(0, False), (LIFTOFF, True), (APOGEE, False), (D, False)])}'
               f'{translate_anim(follower_pairs)}'
               f'<circle r="2.2" fill="{p["key"]}"/></g>')

    # --- CURRENT MISSION marker at the apogee ------------------------------
    out.append(f'<circle cx="{P1[0]}" cy="{P1[1]}" r="3" fill="{p["key"]}">'
               f'<animate attributeName="opacity" values="0.35;1;0.35" dur="1.1s" repeatCount="indefinite"/></circle>')
    out.append(f'<circle cx="{P1[0]}" cy="{P1[1]}" r="6.5" fill="none" stroke="{p["key"]}" opacity="0.5">'
               f'<animate attributeName="opacity" values="0.5;0;0.5" dur="1.1s" repeatCount="indefinite"/></circle>')

    # --- Ground stations (mission log) -------------------------------------
    for i, mo in enumerate(months):
        bx = PAD + i * (BLOCK_W + BLOCK_GAP)
        is_current = i == MONTHS - 1
        label = f"{calendar.month_name[mo['month']].upper()} {mo['year']}"
        stroke = p["key"] if is_current else p["block_stroke"]
        out.append(f'<g><title>{escape(month_tooltip(mo))}</title>')
        out.append(f'<rect x="{bx}" y="{BLOCK_Y}" width="{BLOCK_W}" height="{BLOCK_H}" rx="6" fill="{p["block_bg"]}" '
                   f'stroke="{stroke}" stroke-width="{1.2 if is_current else 1}"/>')
        out.append(f'<circle cx="{bx + 10}" cy="{BLOCK_Y + 12}" r="2.4" fill="{p["key"]}"/>')
        out.append(f'<text x="{bx + 17}" y="{BLOCK_Y + 15}" font-size="9" font-weight="bold" '
                   f'fill="{p["key"] if is_current else p["ink"]}">{escape(label)}</text>')
        if is_current:
            out.append(f'<text x="{bx + BLOCK_W - 10}" y="{BLOCK_Y + 15}" text-anchor="end" font-size="6.5" '
                       f'fill="{p["key"]}">CURRENT MISSION</text>')
        lines = block_lines(mo) if mo["items"] else [("item", "No activity this month")]
        for j, (kind, text) in enumerate(lines):
            y = BLOCK_Y + 28 + j * 10.5
            if kind == "item":
                out.append(f'<text x="{bx + 10}" y="{y:.1f}" font-size="8" fill="{p["ink"]}">✦ {escape(trunc(text, 38))}</text>')
            elif kind == "repo":
                out.append(f'<text x="{bx + 16}" y="{y:.1f}" font-size="7.6" fill="{p["dim"]}">{escape(trunc(text, 36))}</text>')
            else:
                out.append(f'<text x="{bx + 16}" y="{y:.1f}" font-size="7.2" fill="{p["dim"]}" opacity="0.75">{escape(trunc(text, 36))}</text>')
        out.append('</g>')

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'shape-rendering="crispEdges" font-family="Consolas, \'Courier New\', monospace">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="15" fill="{p["bg"]}"/>',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="15" fill="none" stroke="{p["block_stroke"]}"/>',
        *out,
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


def main() -> None:
    today = datetime.now(TZ).date()
    try:
        months = [{"year": y, "month": m, "items": fetch_month(y, m)} for y, m in recent_months(today)]
    except Exception as err:
        print("activity fetch failed, leaving the cards as they are:", err)
        sys.exit(0)
    for mo in months:
        print(f'{mo["year"]}-{mo["month"]:02d}:', "; ".join(i["summary"] for i in mo["items"]) or "no activity")
    stats = totals(months)
    print("telemetry:", stats)
    for name, theme in THEMES.items():
        path = ROOT / f"activity_{name}.svg"
        path.write_text(render(name, theme, months, stats), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
