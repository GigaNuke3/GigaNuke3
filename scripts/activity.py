"""MISSION CONTROL — CONTRIBUTION ACTIVITY.

The last four months of GitHub activity are rendered as a multi-stage
launch mission: the vertical activity timeline becomes a diagonal flight
trajectory (lower-left -> upper-right, ~15 deg), the months become mission
checkpoints, and a Saturn V-inspired three-stage rocket rides the trajectory
as the visual spine.

Data is unchanged: the same public activity feed the old card used
(commit counts per repository, repositories created, pull requests). The
contribution totals drive the telemetry tiles and the exhaust intensity.

The launch sequence (ignition surge, stage separation, third stage
continuing to the payload state) plays once when the card loads, then the
card idles with subtle exhaust flicker, a trajectory pulse and a pulsing
CURRENT MISSION marker. Everything is static-safe: renderers that ignore
SMIL still see the full rocket on its trajectory with all data readable.

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

from grid_common import TZ
from profile_card import PAD, THEMES, USER

ROOT = Path(__file__).resolve().parent.parent
MONTHS = 4
WIDTH = 900
HEIGHT = 472

# --- Geometry --------------------------------------------------------------
P0 = (64, 328)                 # trajectory start (oldest month, lower-left)
P1 = (856, 118)                # trajectory end / rocket nose (current, upper-right)
DX, DY = P1[0] - P0[0], P1[1] - P0[1]
ANGLE = math.degrees(math.atan2(-DY, DX))       # ~14.85 deg above horizontal
ALPHA = 90 - ANGLE                              # rotation applied to the nose-up rocket
COS_A, SIN_A = math.cos(math.radians(ALPHA)), math.sin(math.radians(ALPHA))
ROCKET_LEN = 176
TAIL = (P1[0] - ROCKET_LEN * math.cos(math.radians(ANGLE)),
        P1[1] + ROCKET_LEN * math.sin(math.radians(ANGLE)))

CHECKPOINTS = [0.10, 0.36, 0.62]                # JUL / AUG / SEP along the line
BLOCK_Y = 344
BLOCK_H = 108
BLOCK_W = 196
BLOCK_GAP = 20

# Launch sequence timings (seconds, one-shot).
SEP1 = 1.8
SEP2 = 2.9
SEQ = 4.2

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
    """(kind, text) lines for one month's ground station."""
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
# Rocket drawing (local coords: nose up at -y, engine base at origin)
# --------------------------------------------------------------------------

def _r(x, y, w, h, fill, stroke=None, sw=1, extra="") -> str:
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"{s} {extra}/>'


def _poly(points, fill, stroke=None, sw=1) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<polygon points="{pts}" fill="{fill}"{s}/>'


def s1_shapes(p: dict) -> str:
    body, out, shade = p["rocket_body"], p["ink"], p["rocket_shade"]
    g = [_r(-13, -52, 26, 52, body, out),
         _r(-19, -16, 6, 16, body, out),          # fins
         _r(13, -16, 6, 16, body, out)]
    for cx in (-11, -6.5, -2, 2.5, 7):            # engine cluster
        g.append(_r(cx, 0, 4.5, 5, shade, out, 0.8))
    g.append(_r(-13, -60, 26, 8, shade, out))     # interstage 1
    return "".join(g)


def s2_shapes(p: dict) -> str:
    body, out, shade = p["rocket_body"], p["ink"], p["rocket_shade"]
    g = [_r(-11, -102, 22, 42, body, out)]
    for cx in (-7.5, -3, 1.5, 6):
        g.append(_r(cx, -60, 3.4, 4, shade, out, 0.8))
    g.append(_r(-11, -108, 22, 6, shade, out))     # interstage 2
    return "".join(g)


def s3_payload_shapes(p: dict) -> str:
    body, out = p["rocket_body"], p["ink"]
    g = [_r(-8, -138, 16, 30, body, out)]
    for cx in (-5, -1, 3):
        g.append(_r(cx, -108, 2.6, 4, p["rocket_shade"], out, 0.8))
    g.append(_r(-5, -156, 10, 18, body, out))      # payload section
    g.append(_poly([(0, -176), (-5, -156), (5, -156)], body, out))  # nose cone
    return "".join(g)


def exhaust(p: dict, flame: float, n: int, seed: int) -> str:
    """Flame + particles pointing down (+y) from the local engine base."""
    key, inner = p["key"], p["exhaust_inner"]
    out = [
        f'<g><animate attributeName="opacity" values="0.85;1;0.85" dur="0.5s" repeatCount="indefinite"/>'
        f'{_poly([(0, 0), (-7, flame), (7, flame)], key)}'
        f'{_poly([(0, 0), (-3, flame * 0.62), (3, flame * 0.62)], inner)}</g>',
    ]
    for k in range(n):
        px = ((k * 7 + seed) % 13) - 6
        py = flame + 4 + (k % 3) * 5
        begin = f"{0.15 * k:.2f}s"
        out.append(
            f'<rect x="{px - 1.1:.1f}" y="{py:.1f}" width="2.2" height="3" fill="{key}" opacity="0.9">'
            f'<animateTransform attributeName="transform" type="translate" values="0,0;0,14" '
            f'dur="1.5s" begin="{begin}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0.9;0" dur="1.5s" begin="{begin}" repeatCount="indefinite"/>'
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


def stage_labels(p: dict) -> str:
    out = []
    for label, ly in (("S-IC", -26), ("S-II", -81), ("S-IVB", -123), ("PAYLOAD", -147)):
        sx = TAIL[0] + 17 * COS_A - ly * SIN_A
        sy = TAIL[1] + 17 * SIN_A + ly * COS_A
        out.append(f'<text x="{sx:.1f}" y="{sy:.1f}" font-size="6.5" fill="{p["dim"]}">{label}</text>')
    return "".join(out)


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def render(name: str, theme: dict, months: list[dict], stats: list[tuple[str, str]]) -> str:
    p = palette(theme, name)
    out: list[str] = []
    right = WIDTH - PAD

    # --- Header ------------------------------------------------------------
    out.append(f'<text x="{PAD}" y="30" font-size="15" font-weight="bold" fill="{p["key"]}">MISSION CONTROL</text>')
    out.append(f'<text x="660" y="30" text-anchor="end" font-size="9.5" fill="{p["dim"]}">CONTRIBUTION ACTIVITY &#183; LAST {MONTHS} MONTHS</text>')
    out.append(f'<circle cx="{PAD + 2}" cy="41" r="1.8" fill="{p["key"]}">'
               f'<animate attributeName="opacity" values="1;0.15;1" dur="1.4s" repeatCount="indefinite"/></circle>')
    out.append(f'<text x="{PAD + 8}" y="44" font-size="8" fill="{p["dim"]}">MISSION STATUS: TRAJECTORY NOMINAL</text>')
    out.append(f'<text x="660" y="44" text-anchor="end" font-size="7.5" fill="{p["dim"]}">SYSTEMS ONLINE</text>')
    out.append(f'<line x1="{PAD}" y1="52" x2="{right}" y2="52" stroke="{p["block_stroke"]}"/>')

    # --- Telemetry tiles ---------------------------------------------------
    for i, (value, label) in enumerate(stats):
        x = PAD + i * 158
        out.append(f'<rect x="{x:.0f}" y="64" width="3" height="12" fill="{p["key"]}"/>')
        out.append(f'<text x="{x + 8:.0f}" y="78" font-size="19" font-weight="bold" fill="{p["ink"]}">{escape(value)}</text>')
        out.append(f'<text x="{x + 8:.0f}" y="92" font-size="8" fill="{p["dim"]}">{escape(label)}</text>')

    # --- Launch-pad frame (top-right rocket zone) --------------------------
    out.append(f'<rect x="664" y="56" width="208" height="132" fill="none" stroke="{p["block_stroke"]}" stroke-dasharray="3 3"/>')
    out.append(f'<text x="670" y="66" font-size="6.5" fill="{p["dim"]}">LAUNCH PAD 01</text>')

    # --- Flight trajectory + checkpoints -----------------------------------
    out.append(f'<line x1="{P0[0]}" y1="{P0[1]}" x2="{P1[0]}" y2="{P1[1]}" stroke="{p["key"]}" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>')
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

    # --- The rocket --------------------------------------------------------
    flame, n_particles = exhaust_intensity(int(stats[0][0]))
    s1 = s1_shapes(p)
    s2 = s2_shapes(p)
    s3 = s3_payload_shapes(p)
    k1 = SEP1 / SEQ
    k2 = SEP2 / SEQ
    rocket = [
        f'<g transform="translate({TAIL[0]:.1f},{TAIL[1]:.1f}) rotate({ALPHA:.2f})">',
        # Ignition surge (forward = local -y), static-safe.
        f'<g><animateTransform attributeName="transform" type="translate" '
        f'values="0,0;0,2;0,-5;0,0" begin="0.3s" dur="1.1s" fill="freeze"/>',
        # First stage.
        f'<g><animate attributeName="opacity" values="1;0" begin="{SEP1}s" dur="0.3s" fill="freeze"/>{s1}</g>',
        # First-stage exhaust: visible at t=0, cut at stage separation.
        f'<g><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{k1:.4f};{k1 + 0.06:.4f};1" '
        f'begin="0s" dur="{SEQ}s" fill="freeze"/>{exhaust(p, flame, n_particles, 3)}</g>',
        # Second stage.
        f'<g><animate attributeName="opacity" values="1;0" begin="{SEP2}s" dur="0.3s" fill="freeze"/>{s2}</g>',
        # Second-stage exhaust: appears after first separation.
        f'<g opacity="0"><animate attributeName="opacity" '
        f'values="0;0;1;1;0;0" keyTimes="0;{k1:.4f};{k1 + 0.06:.4f};{k2:.4f};{k2 + 0.06:.4f};1" '
        f'begin="0s" dur="{SEQ}s" fill="freeze"/>{exhaust(p, max(20, flame * 0.6), 3, 5)}</g>',
        # Third stage + payload.
        f'<g>{s3}</g>',
        # Third-stage exhaust: appears after second separation and idles.
        f'<g opacity="0"><animate attributeName="opacity" '
        f'values="0;0;0;1;1" keyTimes="0;{k2:.4f};{k2 + 0.06:.4f};{k2 + 0.12:.4f};1" '
        f'begin="0s" dur="{SEQ}s" fill="freeze"/>{exhaust(p, max(14, flame * 0.4), 2, 7)}</g>',
        # Separation flashes.
        f'<g opacity="0"><animate attributeName="opacity" values="0;0.9;0" begin="{SEP1 - 0.05}s" dur="0.5s" fill="freeze"/>'
        f'{_r(-13, -61, 26, 2, p["key"])}</g>',
        f'<g opacity="0"><animate attributeName="opacity" values="0;0.9;0" begin="{SEP2 - 0.05}s" dur="0.5s" fill="freeze"/>'
        f'{_r(-11, -109, 22, 2, p["key"])}</g>',
        # Separated stages drifting away (down-left, fading).
        f'<g opacity="0"><animate attributeName="opacity" values="0;0.9;0" begin="{SEP1}s" dur="1.6s" fill="freeze"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0,0;0,30" begin="{SEP1}s" dur="1.6s" fill="freeze"/>'
        f'{s1}</g>',
        f'<g opacity="0"><animate attributeName="opacity" values="0;0.9;0" begin="{SEP2}s" dur="1.5s" fill="freeze"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0,0;0,24" begin="{SEP2}s" dur="1.5s" fill="freeze"/>'
        f'{s2}</g>',
        '</g></g>',
    ]
    out.append("".join(rocket))
    out.append(stage_labels(p))

    # --- CURRENT MISSION marker at the nose --------------------------------
    out.append(f'<circle cx="{P1[0]}" cy="{P1[1]}" r="3" fill="{p["key"]}">'
               f'<animate attributeName="opacity" values="0.35;1;0.35" dur="1.1s" repeatCount="indefinite"/></circle>')
    out.append(f'<circle cx="{P1[0]}" cy="{P1[1]}" r="6.5" fill="none" stroke="{p["key"]}" opacity="0.5">'
               f'<animate attributeName="opacity" values="0.5;0;0.5" dur="1.1s" repeatCount="indefinite"/></circle>')

    # --- Trajectory pulse (idle loop) --------------------------------------
    out.append(f'<g opacity="0"><animateMotion values="{P0[0]},{P0[1]};{P1[0]},{P1[1]}" dur="7s" begin="4.6s" repeatCount="indefinite"/>'
               f'<animate attributeName="opacity" values="0;0;0.8;0" keyTimes="0;0.1;0.5;1" dur="7s" begin="4.6s" repeatCount="indefinite"/>'
               f'<circle r="2.5" fill="{p["key"]}"/></g>')

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
