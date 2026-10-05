"""Render the profile card: dark_mode.svg + light_mode.svg.

A compact terminal-style window for the README: the window title bar, the
profile picture (assets/profile.png, referenced by URL), and the developer
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
IMG_URL = f"https://raw.githubusercontent.com/{USER}/{USER}/main/assets/profile.png"

THEMES = {
    "dark": dict(bg="#161b22", text="#f0f3f6", key="#ffa657", value="#c9d1d9",
                 dim="#8b949e", ascii="#f0f3f6", invert=False),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#57606a",
                  dim="#6e7781", ascii="#24292f", invert=True),
}

CARD = {
    "dark": dict(bg="#0d1117", border="#30363d"),
    "light": dict(bg="#f6f8fa", border="#d0d7de"),
}

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
        "commits": fetch_public_contrib_total(),
        "followers": profile.get("followers", 0),
    }


def fetch_stats(token: str | None) -> dict:
    if token:
        try:
            return fetch_stats_graphql(token)
        except Exception as err:
            print(f"GraphQL stats failed ({err}); falling back to the public REST API.")
    return fetch_stats_rest()


def render(name: str, theme: dict, stats: dict) -> str:
    key, dim = theme["key"], theme["dim"]
    card = CARD[name]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Consolas, \'Courier New\', monospace">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="15" fill="{card["bg"]}"/>',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="15" '
        f'fill="none" stroke="{card["border"]}"/>',
        # Title bar
        f'<text x="26" y="27" font-size="11" fill="{key}">&#9679; &#9679; &#9679;</text>',
        f'<text x="64" y="27" font-size="11" fill="{dim}">giganuke3@github: ~/profile</text>',
        f'<line x1="20" y1="40" x2="{WIDTH - 20}" y2="40" stroke="{card["border"]}"/>',
        # Profile picture (clipped to a rounded square)
        '<defs><clipPath id="pic"><rect x="24" y="58" width="220" height="220" rx="12"/></clipPath></defs>',
        f'<image clip-path="url(#pic)" href="{IMG_URL}" x="24" y="58" width="220" height="220" '
        f'preserveAspectRatio="xMidYMid slice"/>',
    ]

    lines = [
        ("key", "eco@giganuke3 &#9612;", 14, True),
        ("key", "&#9472;" * 37, 11, False),
        ("key", "AI ENGINEER / SOFTWARE DEVELOPER", 12.5, False),
        ("dim", "Local AI &#183; LLMs &#183; Desktop Apps &#183; Web Development", 11.5, False),
        ("key", "SYSTEMS", 12, True),
        ("key", "Local AI / LLMs / Desktop Applications", 12, False),
        ("key", "STACK", 12, True),
        ("key", "Python &#183; Kotlin &#183; PHP &#183; JS &#183; SQL", 12, False),
        ("key", "Ollama &#183; LLMs &#183; Embeddings &#183; AI Memory", 12, False),
        ("key", "LANGUAGES", 12, True),
        ("key", "English &#183; Filipino", 12, False),
        ("key", "PROJECTS", 12, True),
        ("project", "Axie Flash   ", "[AI EDUCATION]"),
        ("project", "Callama      ", "[LOCAL AI DESKTOP]"),
        ("project", "LMIS         ", "[INFORMATION SYSTEM]"),
        ("key", "GITHUB", 12, True),
        ("key", f"Repos {stats['repos']} &#183; Stars {stats['stars']:,} &#183; Followers {stats['followers']:,}", 12, False),
        ("key", f"Commits {stats['commits']:,}", 12, False),
        ("dim", "github.com/GigaNuke3", 11.5, False),
    ]
    x0, y0, lh = 272, 82, 13.6
    for i, item in enumerate(lines):
        y = y0 + i * lh
        if item[0] == "project":
            _, name, tag = item
            out.append(f'<text x="{x0}" y="{y:.1f}" font-size="12">'
                       f'<tspan fill="{key}">{escape(name)}</tspan>'
                       f'<tspan fill="{dim}">{escape(tag)}</tspan></text>')
        else:
            kind, text, size, bold = item
            weight = ' font-weight="bold"' if bold else ""
            fill = key if kind == "key" else dim
            out.append(f'<text x="{x0}" y="{y:.1f}" font-size="{size}"{weight} fill="{fill}">'
                       f'{escape(text)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


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

    for name, theme in THEMES.items():
        path = ROOT / f"{name}_mode.svg"
        path.write_text(render(name, theme, stats), encoding="utf-8")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
