"""Render the profile card: dark_mode.svg + light_mode.svg.

A compact terminal-style window for the README: the window title bar, the
profile picture (assets/avatar.jpg, embedded), and the developer
readout with live GitHub stats on the right.

When GITHUB_TOKEN or ACCESS_TOKEN is available (GitHub Actions), GraphQL is
used for richer all-time stats; otherwise the public REST API + the public
contribution calendar are used, so the card can still be rendered locally
without a token.

Usage:
    python scripts/profile_card.py            # live stats (token if present)
    python scripts/profile_card.py --offline  # placeholder stats
"""

import argparse
import base64
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
USER = "GigaNuke3"

WIDTH, HEIGHT = 900, 352
PAD = 28  # shared card margin (imported by the other card scripts)
# Embedded, not linked: GitHub shows these SVGs as <img>, and an SVG image
# may not load external files, so a URL here renders as a broken picture.
AVATAR = ROOT / "assets" / "avatar.jpg"

# One palette for every card, so the bays read as one facility.
THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", text="#f0f3f6", key="#ffa657",
                 value="#c9d1d9", dim="#8b949e"),
    "light": dict(bg="#f6f8fa", border="#d0d7de", text="#24292f", key="#953800",
                  value="#57606a", dim="#6e7781"),
}

# Animated layers carry class "fx"; reduced-motion viewers get the "still"
# layers instead (the static frame each card is designed around).
MOTION_CSS = ("<style>.still{display:none}@media (prefers-reduced-motion: reduce)"
              "{.fx{display:none}.still{display:inline}}</style>")


def card(theme: dict, width: float, height: float, bay: str, body: list[str]) -> str:
    """Shared chrome for every card: background, border, orange corner
    registration marks and the bay label (bottom right) naming the room."""
    k, t = theme["key"], 10
    ticks = "".join(
        f'<path d="M{x},{y + t * sy} V{y} H{x + t * sx}" fill="none" stroke="{k}" stroke-width="2"/>'
        for x, y, sx, sy in ((6, 6, 1, 1), (width - 6, 6, -1, 1),
                             (6, height - 6, 1, -1), (width - 6, height - 6, -1, -1)))
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges" '
        f'font-family="Consolas, \'Courier New\', monospace">',
        MOTION_CSS,
        f'<rect width="{width}" height="{height}" rx="4" fill="{theme["bg"]}"/>',
        *body,
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4" '
        f'fill="none" stroke="{theme["border"]}"/>',
        ticks,
        f'<text x="{width - 20}" y="{height - 9}" text-anchor="end" font-size="7" '
        f'letter-spacing="1" fill="{theme["dim"]}">GN3 / {escape(bay)}</text>',
        "</svg>",
    ]) + "\n"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100) {
      totalCount
      nodes { stargazerCount }
    }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {
      totalCount
    }
  }
}
"""

COMMITS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats_graphql(token: str) -> dict:
    user = graphql(token, QUERY, {"login": USER})["user"]
    commits = 0
    now = datetime.now(timezone.utc)
    for year in range(2025, now.year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year + 1, 1, 1, tzinfo=timezone.utc), now)
        cc = graphql(token, COMMITS_QUERY, {
            "login": USER, "from": start.isoformat(), "to": end.isoformat(),
        })["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return {
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in user["repositories"]["nodes"]),
        "commits": commits,
        "followers": user["followers"]["totalCount"],
    }


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "GigaNuke3-profile"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_public_contrib_total() -> int:
    """Sum the last year of contributions from the public calendar (no token)."""
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "GigaNuke3-profile"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8")
    cells = re.findall(r'data-date="([\d-]+)" id="(contribution-day-component-[\d-]+)" data-level="(\d)"', page)
    tips = dict(re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)</tool-tip>', page))
    if len(cells) < 300:
        raise RuntimeError(f"Could not parse GitHub contribution calendar: {len(cells)} days")
    total = 0
    for _, cid, _ in cells:
        m = re.match(r"(\d+) contribution", tips.get(cid, ""))
        total += int(m.group(1)) if m else 0
    return total


def fetch_stats_rest() -> dict:
    profile = fetch_json(f"https://api.github.com/users/{USER}")
    repos = fetch_json(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=updated")
    return {
        "repos": profile.get("public_repos", 0),
        "contributed": 0,  # needs GraphQL; not shown on the card
        "stars": sum(int(r.get("stargazers_count", 0)) for r in repos),
        # Without a token only the calendar total is public: label it as such.
        "commits": fetch_public_contrib_total(),
        "commits_label": "Contributions (1y)",
        "followers": profile.get("followers", 0),
    }


def fetch_stats(token: str | None) -> dict:
    if token:
        try:
            return fetch_stats_graphql(token)
        except Exception as err:
            print(f"GraphQL stats failed ({err}); falling back to the public REST API.")
    return fetch_stats_rest()


def render(theme: dict, stats: dict, avatar: str) -> str:
    key, dim = theme["key"], theme["dim"]
    out = [
        # Title bar
        f'<text x="26" y="27" font-size="11" fill="{key}">● ● ●</text>',
        f'<text x="64" y="27" font-size="11" fill="{dim}">giganuke3@github: ~/profile</text>',
        f'<line x1="20" y1="40" x2="{WIDTH - 20}" y2="40" stroke="{theme["border"]}"/>',
        # Profile picture (clipped to a rounded square)
        '<defs><clipPath id="pic"><rect x="24" y="58" width="220" height="220" rx="4"/></clipPath></defs>',
        f'<image clip-path="url(#pic)" href="data:image/jpeg;base64,{avatar}" x="24" y="58" '
        f'width="220" height="220" preserveAspectRatio="xMidYMid slice"/>',
    ]

    lines = [
        ("key", "eco@giganuke3", 14, True),
        ("key", "─" * 37, 11, False),
        ("key", "AI ENGINEER / SOFTWARE DEVELOPER", 12.5, False),
        ("dim", "Local AI · LLMs · Desktop Apps · Web Development", 11.5, False),
        ("key", "SYSTEMS", 12, True),
        ("key", "Local AI / LLMs / Desktop Applications", 12, False),
        ("key", "STACK", 12, True),
        ("key", "Python · Kotlin · PHP · JS · SQL", 12, False),
        ("key", "Ollama · LLMs · Embeddings · AI Memory", 12, False),
        ("key", "LANGUAGES", 12, True),
        ("key", "English · Filipino", 12, False),
        ("key", "PROJECTS", 12, True),
        ("project", "Axie Flash   ", "[AI EDUCATION]"),
        ("project", "Callama      ", "[LOCAL AI DESKTOP]"),
        ("project", "LMIS         ", "[INFORMATION SYSTEM]"),
        ("key", "GITHUB", 12, True),
        ("key", f"Repos {stats['repos']} · Stars {stats['stars']:,} · Followers {stats['followers']:,}", 12, False),
        ("key", f"{stats.get('commits_label', 'Commits')} {stats['commits']:,}", 12, False),
        ("dim", "github.com/GigaNuke3", 11.5, False),
    ]
    x0, y0, lh = 272, 82, 13.6
    for i, item in enumerate(lines):
        y = y0 + i * lh
        if item[0] == "project":
            _, name, tag = item
            out.append(f'<text x="{x0}" y="{y:.1f}" font-size="12" xml:space="preserve">'
                       f'<tspan fill="{key}">{escape(name)}</tspan>'
                       f'<tspan fill="{dim}">{escape(tag)}</tspan></text>')
        else:
            kind, text, size, bold = item
            weight = ' font-weight="bold"' if bold else ""
            fill = key if kind == "key" else dim
            # Prompt cursor after the first line: the one moving thing on this card.
            cursor = (' <tspan class="fx">▌<animate attributeName="opacity" values="1;1;0;0" '
                      'keyTimes="0;0.5;0.5;1" dur="1.1s" repeatCount="indefinite"/></tspan>') if i == 0 else ""
            out.append(f'<text x="{x0}" y="{y:.1f}" font-size="{size}"{weight} fill="{fill}">'
                       f'{escape(text)}{cursor}</text>')
    return card(theme, WIDTH, HEIGHT, "BAY 00 · IDENT", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use placeholder stats")
    args = ap.parse_args()

    if args.offline:
        stats = dict(repos=9, contributed=0, stars=2, commits=562, followers=1)
    else:
        token = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
        stats = fetch_stats(token)
    print("stats:", stats)

    avatar = base64.b64encode(AVATAR.read_bytes()).decode()
    for name, theme in THEMES.items():
        path = ROOT / f"{name}_mode.svg"
        path.write_text(render(theme, stats, avatar), encoding="utf-8")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
