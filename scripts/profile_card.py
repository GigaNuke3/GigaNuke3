"""Render the profile card: dark_mode.svg + light_mode.svg.

Adapted for GigaNuke3 from the Gabi-comm profile card generator
(https://github.com/Gabi-comm/Gabi-comm), with a REST fallback so the
card can be rendered locally without a token. When GITHUB_TOKEN or
ACCESS_TOKEN is available (GitHub Actions), GraphQL is used for richer
all-time stats.

Usage:
    python scripts/profile_card.py            # live stats (token if present)
    python scripts/profile_card.py --offline  # placeholder stats
"""

import argparse
import json
import os
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
USER = "GigaNuke3"
JOINED = date(2025, 4, 13)  # the day the GitHub account was created

WIDTH = 62  # character width of the info column


PROFILE = [
    ("OS", "Fedora Linux / Windows"),
    ("Uptime", "{uptime}"),
    ("Host", "github.com/GigaNuke3"),
    ("Kernel", "AI Engineer / Software Developer"),
    ("IDE", "VS Code, Cursor, Claude Code"),
    None,
    ("Languages.Programming", "Python, Kotlin, PHP, JS, SQL"),
    ("Languages.AI/ML", "Ollama, LLMs, Embeddings, AI Memory"),
    ("Languages.Real", "English, Filipino"),
    None,
    ("Role.Current", "AI Engineer / Software Developer"),
    ("Role.Focus", "Local AI / LLMs / Desktop Applications"),
    ("Systems", "Axie Flash / Callama / LMIS"),
    ("Mindset", "Build -> Break -> Understand -> Rebuild"),
    ("- Contact", None),
    ("GitHub", USER),
    ("- GitHub Stats", None),
    "{stats_repos}",
    "{stats_commits}",
]

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#f0f3f6", value="#a5d6ff",
                 dim="#616e7f", ascii="#c9d1d9", invert=False),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#1f2328", value="#0a3069",
                  dim="#9aa6b5", ascii="#24292f", invert=True),
}

PAD = 28
ASCII_FONT, ASCII_CHAR_W, ASCII_LINE = 12, 7.2, 13.9
INFO_FONT, INFO_CHAR_W, INFO_LINE = 14, 8.4, 18.5
GAP = 28


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
    for year in range(JOINED.year, now.year + 1):
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
        "contributed": 0,  # needs GraphQL; only shown when a token is available
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


def uptime(today: date) -> str:
    months = (today.year - JOINED.year) * 12 + today.month - JOINED.month
    if today.day < JOINED.day:
        months -= 1
    anchor_month = JOINED.month - 1 + months
    anchor = date(JOINED.year + anchor_month // 12, anchor_month % 12 + 1, JOINED.day)
    days = (today - anchor).days
    years, months = divmod(months, 12)

    def unit(n, word):
        return f"{n} {word}{'' if n == 1 else 's'}"

    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"


def kv(key: str, value: str, width: int) -> list[tuple[str, str]]:
    """'. Key: ...... value' padded to `width` characters."""
    head, tail = f"{key}:", f" {value}"
    dots = width - 2 - len(head) - len(tail) - 1
    if dots < 2:
        raise ValueError(f"line too long for {width} cols: {key}: {value}")
    return [("dim", ". "), ("key", key), ("text", ":"), ("dim", " " + "." * dots), ("value", tail)]


def rule(title: str, width: int) -> list[tuple[str, str]]:
    return [("text", title + " "), ("dim", "—" * (width - len(title) - 1))]


STAT_SPLIT = 36  # where the ' | ' between the two stat pairs sits


def stat_pair(left: tuple[str, str], right: tuple[str, str], width: int) -> list[tuple[str, str]]:
    """Two key/values on one line split by ' | ', like the sample's stats rows."""
    right_spans = kv(*right, width - STAT_SPLIT - 3 + 2)[1:]
    return kv(*left, STAT_SPLIT) + [("text", " | ")] + right_spans


def info_lines(stats: dict, today: date) -> list[list[tuple[str, str]]]:
    lines = [rule("eco@giganuke3", WIDTH)]
    for row in PROFILE:
        if row is None:
            lines.append([("dim", ".")])
        elif row == "{stats_repos}":
            lines.append(stat_pair(("Repos", f"{stats['repos']}"),
                                   ("Stars", f"{stats['stars']:,}"), WIDTH))
        elif row == "{stats_commits}":
            lines.append(stat_pair(("Commits", f"{stats['commits']:,}"),
                                   ("Followers", f"{stats['followers']:,}"), WIDTH))
        elif row[1] is None:
            lines.append(rule(row[0], WIDTH))
        else:
            key, value = row
            lines.append(kv(key, value.format(uptime=uptime(today)), WIDTH))
    return lines


def render(theme: dict, portrait: list[str], info: list[list[tuple[str, str]]]) -> str:
    ascii_cols = max(len(l) for l in portrait)
    ascii_w = ascii_cols * ASCII_CHAR_W
    ascii_h = len(portrait) * ASCII_LINE
    info_w = WIDTH * INFO_CHAR_W
    info_h = len(info) * INFO_LINE
    content_h = max(ascii_h, info_h)
    width = round(PAD * 2 + ascii_w + GAP + info_w)
    height = round(PAD * 2 + content_h)

    colours = {k: theme[k] for k in ("text", "key", "value", "dim")}
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Consolas, \'Courier New\', monospace">',
        "<style>text { white-space: pre; }</style>",
        f'<rect width="{width}" height="{height}" rx="15" fill="{theme["bg"]}"/>',
    ]

    y0 = PAD + (content_h - ascii_h) / 2 + ASCII_LINE * 0.8
    out.append(f'<g fill="{theme["ascii"]}" font-size="{ASCII_FONT}">')
    for i, line in enumerate(portrait):
        line = line.ljust(ascii_cols)
        out.append(
            f'<text x="{PAD}" y="{y0 + i * ASCII_LINE:.1f}" textLength="{ascii_w:.1f}" '
            f'lengthAdjust="spacing">{escape(line)}</text>'
        )
    out.append("</g>")

    x = PAD + ascii_w + GAP
    y1 = PAD + (content_h - info_h) / 2 + INFO_LINE * 0.8
    out.append(f'<g font-size="{INFO_FONT}">')
    for i, spans in enumerate(info):
        n = sum(len(t) for _, t in spans)
        tspans = "".join(f'<tspan fill="{colours[s]}">{escape(t)}</tspan>' for s, t in spans)
        out.append(
            f'<text x="{x:.1f}" y="{y1 + i * INFO_LINE:.1f}" textLength="{n * INFO_CHAR_W:.1f}" '
            f'lengthAdjust="spacing">{tspans}</text>'
        )
    out.append("</g></svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use placeholder stats")
    args = ap.parse_args()

    if args.offline:
        stats = dict(repos=9, contributed=0, stars=2, commits=1234, followers=1)
    else:
        token = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
        stats = fetch_stats(token)
    print("stats:", stats)

    portrait = (ROOT / "assets" / "portrait.txt").read_text(encoding="utf-8").splitlines()
    info = info_lines(stats, date.today())
    for name, theme in THEMES.items():
        path = ROOT / f"{name}_mode.svg"
        path.write_text(render(theme, portrait, info), encoding="utf-8")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
