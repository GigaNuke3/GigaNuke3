"""PAYLOAD MANIFEST — the repositories as the payloads the rocket carries.

Every public, non-fork repository is a payload module standing on the
integration rail, left to right in the order it was created, so the rail
reads as the history of what was built. Real data only (GitHub REST):

    module height  log of the repository size
    status lamp    days since the last push: LIVE <= 14 (pulsing),
                   WARM <= 60 (lit), COLD (dark)
    year ticks     where the creation year changes along the rail

Click-to-open lives in the README: the same manifest, with links, is
rewritten between the manifest markers inside a <details> block.

Output: payloads_dark.svg + payloads_light.svg + the README manifest block.
"""

import json
import math
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from grid_common import TZ
from profile_card import PAD, THEMES, USER, card

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 900, 282
RAIL = 214
LIVE_DAYS, WARM_DAYS = 14, 60


def fetch_repos() -> list[dict]:
    req = urllib.request.Request(f"https://api.github.com/users/{USER}/repos?per_page=100",
                                 headers={"User-Agent": "profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        repos = [r for r in json.load(resp) if not r["fork"]]
    return sorted(repos, key=lambda r: r["created_at"])


def status(pushed: date, today: date) -> str:
    age = (today - pushed).days
    return "LIVE" if age <= LIVE_DAYS else "WARM" if age <= WARM_DAYS else "COLD"


def size_label(kb: int) -> str:
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb} KB"


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def render(theme: dict, repos: list[dict], today: date) -> str:
    key, ink, dim, line = theme["key"], theme["text"], theme["dim"], theme["border"]
    right = WIDTH - PAD
    slot = (right - PAD) / len(repos)
    mw = min(44, slot - 26)
    states = [status(date.fromisoformat(r["pushed_at"][:10]), today) for r in repos]
    out = [
        f'<text x="{PAD}" y="30" font-size="15" font-weight="bold" fill="{key}">PAYLOAD MANIFEST</text>',
        f'<text x="{right}" y="30" text-anchor="end" font-size="9.5" fill="{dim}">'
        f'{len(repos)} REPOSITORIES &#183; ORDERED BY CREATION</text>',
        f'<text x="{PAD}" y="44" font-size="8" fill="{dim}">WHAT THE ROCKET CARRIES</text>',
        f'<text x="{right}" y="44" text-anchor="end" font-size="7.5" fill="{dim}">'
        + " &#183; ".join(f"{states.count(s)} {s}" for s in ("LIVE", "WARM", "COLD")) + "</text>",
        f'<line x1="{PAD}" y1="52" x2="{right}" y2="52" stroke="{line}"/>',
        # The integration rail.
        f'<rect x="{PAD}" y="{RAIL}" width="{right - PAD}" height="3" fill="{dim}" opacity="0.6"/>',
    ]

    year = None
    for i, (r, st) in enumerate(zip(repos, states)):
        cx = PAD + slot * (i + 0.5)
        h = min(130, 18 + 24 * math.log10(r["size"] + 1))
        top = RAIL - h
        x = cx - mw / 2
        hot = st != "COLD"
        stroke = key if st == "LIVE" else dim
        if r["created_at"][:4] != year:  # creation-year tick on the rail
            year = r["created_at"][:4]
            bx = PAD + slot * i
            out.append(f'<line x1="{bx:.1f}" y1="{RAIL - 8}" x2="{bx:.1f}" y2="{RAIL + 3}" stroke="{key}"/>'
                       f'<text x="{bx + 3:.1f}" y="{RAIL - 2}" font-size="6.5" fill="{key}">{year}</text>')
        # Module: body, stage rings, nose cap, status lamp.
        out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{mw:.1f}" height="{h:.1f}" '
                   f'fill="{theme["bg"]}" stroke="{stroke}"/>')
        for ry in range(int(top) + 12, RAIL - 4, 12):
            out.append(f'<line x1="{x + 3:.1f}" y1="{ry}" x2="{x + mw - 3:.1f}" y2="{ry}" stroke="{line}"/>')
        out.append(f'<polygon points="{x + 4:.1f},{top:.1f} {x + mw - 4:.1f},{top:.1f} '
                   f'{x + mw - 10:.1f},{top - 7:.1f} {x + 10:.1f},{top - 7:.1f}" fill="{theme["bg"]}" stroke="{stroke}"/>')
        lamp = f'<rect x="{cx - 3:.1f}" y="{top - 14:.1f}" width="6" height="5" fill="{key if hot else "none"}" stroke="{key if hot else dim}"'
        if st == "LIVE":  # pulsing for motion viewers, steady for reduced motion
            out.append(f'<g class="fx">{lamp}><animate attributeName="opacity" values="1;0.2;1" '
                       f'dur="1.4s" repeatCount="indefinite"/></rect></g><g class="still">{lamp}/></g>')
        else:
            out.append(lamp + "/>")
        # Manifest label under the rail.
        chars = int(slot / 6)
        stars = f' &#183; <tspan fill="{key}">★{r["stargazers_count"]}</tspan>' if r["stargazers_count"] else ""
        out.append(f'<text x="{cx:.1f}" y="{RAIL + 18}" text-anchor="middle" font-size="8" '
                   f'fill="{key if st == "LIVE" else ink}">{escape(trunc(r["name"], chars))}</text>')
        out.append(f'<text x="{cx:.1f}" y="{RAIL + 30}" text-anchor="middle" font-size="6.5" fill="{dim}">'
                   f'{escape(r["language"] or "—")} &#183; {size_label(r["size"])}</text>')
        out.append(f'<text x="{cx:.1f}" y="{RAIL + 41}" text-anchor="middle" font-size="6.5" fill="{dim}">'
                   f'{st} &#183; {r["pushed_at"][5:10]}{stars}</text>')

    # Ambient: an inspection bracket sweeps the rail, module by module.
    stops = ";".join(f"{slot * i:.1f},0" for i in range(len(repos)))
    out.append(f'<g class="fx"><animateTransform attributeName="transform" type="translate" values="{stops}" '
               f'calcMode="discrete" dur="{len(repos) * 1.6:.1f}s" repeatCount="indefinite"/>'
               f'<path d="M{PAD + 4},{RAIL - 150} h-4 V{RAIL + 46} h4 M{PAD + slot - 4},{RAIL - 150} h4 V{RAIL + 46} h-4" '
               f'fill="none" stroke="{key}" opacity="0.5"/></g>')
    return card(theme, WIDTH, HEIGHT, "BAY 03 · PAYLOADS · REPOS", out)


def manifest(repos: list[dict], today: date) -> str:
    """The README block: the same manifest as a table with links."""
    rows = ["| PAYLOAD | LANG | STATUS | LAST PUSH | NOTE |", "|---|---|---|---|---|"]
    for r in repos:
        note = (r["description"] or "").replace("|", "\\|").replace("\n", " ")
        rows.append(f'| [{r["name"]}]({r["html_url"]}) | {r["language"] or "—"} | '
                    f'{status(date.fromisoformat(r["pushed_at"][:10]), today)} | {r["pushed_at"][:10]} | {note} |')
    return ("<details>\n<summary><b>OPEN THE PAYLOAD MANIFEST</b>: every module above, with links</summary>\n\n"
            + "\n".join(rows) + "\n\n</details>")


def main() -> None:
    today = datetime.now(TZ).date()
    try:
        repos = fetch_repos()
    except Exception as err:
        print("repo fetch failed, leaving the manifest as it is:", err)
        sys.exit(0)
    for name, theme in THEMES.items():
        path = ROOT / f"payloads_{name}.svg"
        path.write_text(render(theme, repos, today), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")
    readme = ROOT / "README.md"
    text, n = re.subn(r"(<!-- manifest:start -->\n).*?(<!-- manifest:end -->)",
                      lambda m: m.group(1) + manifest(repos, today) + "\n" + m.group(2),
                      readme.read_text(encoding="utf-8"), flags=re.S)
    if n:
        readme.write_text(text, encoding="utf-8")
        print("updated README manifest")


if __name__ == "__main__":
    main()
