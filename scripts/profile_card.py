#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import statistics
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "GigaNuke3")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]

QUERY = """
query($login:String!) {
  user(login:$login) {
    login
    name
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes { stargazerCount primaryLanguage { name } }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
      contributionCalendar {
        weeks {
          contributionDays { contributionCount date weekday }
        }
      }
    }
  }
}
"""

def gql() -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "GigaNuke3-profile-renderer",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode())
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]

def esc(v: object) -> str:
    return html.escape(str(v), quote=True)

def t(x: float, y: float, value: object, fill: str, size: int = 14,
      weight: str = "400", anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>'

ASCII = [
    "                 .-=========-.",
    "             .-''               ''-.",
    "           .'      .---------.      '.",
    "          /      .'   AI CORE   '.      \\",
    "         /      /      .-.        \\      \\",
    "        |      |      ( o )        |      |",
    "        |      |       -           |      |",
    "        |      |    .---|---.      |      |",
    "        |      |   /    |    \\     |      |",
    "        |      |  /   .-^-.   \\    |      |",
    "         \\      \\ '._/     \\_.'   /      /",
    "          '.      '---.     .---'     .'",
    "            '-.        '---'        .-'",
    "               '----.         .----'",
    "                    '---------'",
    "",
    "              ECO // AI ENGINEERING",
]

def palette(dark: bool) -> dict[str, str]:
    if dark:
        return {"bg":"#161b22","panel":"#1c222a","text":"#c9d1d9","muted":"#8b949e","accent":"#a855f7","grid":"#30363d"}
    return {"bg":"#ffffff","panel":"#f6f8fa","text":"#24292f","muted":"#57606a","accent":"#7c3aed","grid":"#d0d7de"}

def shell(w: int, h: int, p: dict[str,str], body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Consolas,monospace"><rect width="{w}" height="{h}" rx="15" fill="{p["bg"]}"/><rect x="1" y="1" width="{w-2}" height="{h-2}" rx="15" fill="none" stroke="{p["grid"]}"/>{body}</svg>'

def lines(x: float, y: float, vals: list[str], p: dict[str,str], size=12, gap=18):
    return "".join(t(x, y+i*gap, v, p["accent"], size) for i,v in enumerate(vals))

def render_card(u: dict, dark: bool) -> str:
    p=palette(dark)
    repos=u["repositories"]
    stars=sum(int(r["stargazerCount"]) for r in repos["nodes"])
    info=[
        f'{USER}@github',
        'OS: Fedora Linux / Windows',
        'Role: AI Engineer / Software Developer',
        'Focus: AI / Local LLMs / Applications',
        'Languages: Python / Kotlin / PHP / JavaScript / SQL',
        'AI Stack: Ollama / LLMs / Embeddings',
        'Projects: Axie Flash / Callama / LMIS',
        '',
        f'Repositories: {repos["totalCount"]}',
        f'Stars: {stars}',
        f'Followers: {u["followers"]["totalCount"]}',
    ]
    body=[t(28,35,"GigaNuke3 // README.md",p["muted"],10)]
    body.append(lines(48,72,ASCII,p,10,15))
    body.append(f'<rect x="470" y="52" width="1" height="360" fill="{p["grid"]}"/>')
    body.append(t(495,68,info[0],p["text"],14,"700"))
    body.append(lines(495,92,info[1:7],p,11,21))
    body.append(t(495,252,"> profile.status",p["accent"],11))
    body.append(t(495,273,"ACTIVE // LEARNING // BUILDING",p["text"],11))
    body.append(t(495,307,"> systems",p["accent"],11))
    body.append(t(495,328,"Axie Flash      [AI / EDUCATION]",p["text"],11))
    body.append(t(495,347,"Callama         [LOCAL AI]",p["text"],11))
    body.append(t(495,366,"LMIS            [INFORMATION SYSTEM]",p["text"],11))
    body.append(t(495,399,"Build. Break. Understand. Rebuild.",p["muted"],11))
    return shell(1037,430,p,"".join(body))

def days(u: dict) -> list[dict]:
    out=[]
    for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]:
        out.extend(w["contributionDays"])
    return sorted(out,key=lambda d:d["date"])

def render_graph(u: dict, dark: bool) -> str:
    p=palette(dark)
    ds=days(u)
    cutoff=date.today()-timedelta(days=365)
    ds=[d for d in ds if date.fromisoformat(d["date"])>=cutoff]
    total=sum(d["contributionCount"] for d in ds)
    active=sum(1 for d in ds if d["contributionCount"]>0)
    best=max([d["contributionCount"] for d in ds] or [0])
    vals=[d["contributionCount"] for d in ds if d["contributionCount"]>0]
    avg=statistics.mean(vals) if vals else 0
    body=[t(28,39,"Contribution Graph",p["accent"],15,"700"),
          t(872,39,"daily · rolling 365 days",p["muted"],10,anchor="end"),
          t(28,79,total,p["text"],24),t(28,95,"Contributions",p["muted"],10),
          t(200,79,best,p["text"],24),t(200,95,"Best Day",p["muted"],10),
          t(370,79,f"{avg:.1f}",p["text"],24),t(370,95,"Active-Day Avg",p["muted"],10),
          t(540,79,active,p["text"],24),t(540,95,"Active Days",p["muted"],10)]
    if ds:
        start=date.fromisoformat(ds[0]["date"])
        offset=(start.weekday()+1)%7
        maxv=max(d["contributionCount"] for d in ds) or 1
        for i,d in enumerate(ds):
            pos=offset+i
            col,row=divmod(pos,7)
            x=28+col*14
            y=120+row*15
            n=d["contributionCount"]
            opacity=0.18 if n==0 else 0.25+0.7*(n/maxv)
            body.append(f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{p["accent"]}" fill-opacity="{opacity:.2f}"><title>{esc(d["date"])}: {n}</title></rect>')
    return shell(900,300,p,"".join(body))

def render_activity(u: dict, dark: bool) -> str:
    p=palette(dark)
    ds=days(u)
    now=date.today()
    monthly=defaultdict(int)
    for d in ds:
        dt=date.fromisoformat(d["date"])
        months=(now.year-dt.year)*12+now.month-dt.month
        if 0<=months<6:
            monthly[(dt.year,dt.month)]+=d["contributionCount"]
    ordered=sorted(monthly.items())[-6:]
    maxv=max([v for _,v in ordered] or [1])
    cc=u["contributionsCollection"]
    body=[t(28,39,"Contribution Activity",p["accent"],15,"700"),
          t(872,39,"last 6 months",p["muted"],10,anchor="end"),
          t(28,79,cc["totalCommitContributions"],p["text"],24),t(28,95,"Commits",p["muted"],10),
          t(220,79,cc["totalPullRequestContributions"],p["text"],24),t(220,95,"Pull Requests",p["muted"],10),
          t(412,79,cc["totalIssueContributions"],p["text"],24),t(412,95,"Issues",p["muted"],10),
          t(604,79,cc["totalRepositoryContributions"],p["text"],24),t(604,95,"Repositories",p["muted"],10)]
    body.append(f'<line x1="50" y1="255" x2="870" y2="255" stroke="{p["grid"]}"/>')
    for i,((y,m),v) in enumerate(ordered):
        h=135*(v/maxv if maxv else 0)
        x=65+i*132
        body.append(f'<rect x="{x}" y="{255-h:.1f}" width="72" height="{h:.1f}" rx="3" fill="{p["accent"]}"/>')
        body.append(t(x+36,278,date(y,m,1).strftime("%b"),p["muted"],10,anchor="middle"))
        body.append(t(x+36,247-h,str(v),p["text"],10,"700",anchor="middle"))
    return shell(900,310,p,"".join(body))

def main():
    u=gql()
    (ROOT/"profile_dark.svg").write_text(render_card(u,True),encoding="utf-8")
    (ROOT/"profile_light.svg").write_text(render_card(u,False),encoding="utf-8")
    (ROOT/"graph_dark.svg").write_text(render_graph(u,True),encoding="utf-8")
    (ROOT/"graph_light.svg").write_text(render_graph(u,False),encoding="utf-8")
    (ROOT/"activity_dark.svg").write_text(render_activity(u,True),encoding="utf-8")
    (ROOT/"activity_light.svg").write_text(render_activity(u,False),encoding="utf-8")

if __name__=="__main__":
    main()
