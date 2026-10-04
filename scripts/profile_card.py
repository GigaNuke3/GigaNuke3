#!/usr/bin/env python3
from __future__ import annotations
import html, json, re, urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER = "GigaNuke3"

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "GigaNuke3-profile"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def fetch_contributions():
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "GigaNuke3-profile"})
    with urllib.request.urlopen(req, timeout=30) as response:
        page = response.read().decode("utf-8")
    cells = re.findall(r'data-date="([\d-]+)"[^>]*data-level="(\d)"', page)
    if len(cells) < 300:
        raise RuntimeError(f"Could not parse GitHub contribution calendar: {len(cells)}")
    return [{"date": date.fromisoformat(iso), "level": int(level)} for iso, level in cells]

def stats():
    profile = fetch_json(f"https://api.github.com/users/{USER}")
    repos = fetch_json(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=updated")
    return {
        "repos": profile.get("public_repos", 0),
        "stars": sum(int(r.get("stargazers_count", 0)) for r in repos),
        "followers": profile.get("followers", 0),
        "following": profile.get("following", 0),
    }

def esc(v): return html.escape(str(v), quote=True)

def tx(x, y, v, c, size=14, weight="400", anchor="start"):
    return f'<text x="{x}" y="{y}" fill="{c}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{esc(v)}</text>'

def palette(dark):
    return ({"bg":"#161b22","text":"#c9d1d9","key":"#ffa657","value":"#a5d6ff","dim":"#616e7f"}
            if dark else
            {"bg":"#f6f8fa","text":"#24292f","key":"#953800","value":"#0a3069","dim":"#9aa6b5"})

ASCII = [
"                           .-=========-.",
"                       .-''               ''-.",
"                     .'       .-------.       '.",
"                    /       .'  .---.  '.       \\",
"                   /       /   /  @  \\   \\       \\",
"                  |       |    \\  _  /    |       |",
"                  |       |     '---'     |       |",
"                  |       |   .---|---.   |       |",
"                  |       |  /    |    \\  |       |",
"                  |       | /   .-^-.   \\ |       |",
"                   \\       \\  /     \\  /       /",
"                    '.       '-------'       .'",
"                      '-.                 .-'",
"                         '------. .------'",
"                                '---'",
]

def profile_svg(dark, s):
    p = palette(dark)
    out = [
        tx(28,35,"GigaNuke3 // README.md",p["dim"],10),
        f'<rect x="28" y="50" width="5" height="392" fill="{p["key"]}"/>'
    ]
    for i, line in enumerate(ASCII):
        out.append(f'<text x="50" y="{75+i*21}" fill="{p["text"]}" font-size="10" textLength="445" lengthAdjust="spacing">{esc(line)}</text>')
    out += [
        f'<rect x="474" y="48" width="1" height="394" fill="{p["dim"]}" opacity=".45"/>',
        tx(495,62,"giganuke3@github",p["text"],14,"700"),
        tx(495,88,"OS:",p["key"],11), tx(615,88,"Fedora Linux / Windows",p["value"],11),
        tx(495,109,"Role:",p["key"],11), tx(615,109,"AI Engineer / Software Developer",p["value"],11),
        tx(495,130,"Focus:",p["key"],11), tx(615,130,"AI / Local LLMs / Applications",p["value"],11),
        tx(495,151,"Languages:",p["key"],11), tx(615,151,"Python, Kotlin, PHP, JavaScript, SQL",p["value"],11),
        tx(495,172,"AI:",p["key"],11), tx(615,172,"Ollama, LLMs, Embeddings, Memory",p["value"],11),
        tx(495,213,"> systems",p["key"],11,"700"),
        tx(495,236,"Axie Flash      [AI / EDUCATION]",p["text"],11),
        tx(495,257,"Callama         [LOCAL AI / DESKTOP]",p["text"],11),
        tx(495,278,"LMIS            [INFORMATION SYSTEM]",p["text"],11),
        tx(495,319,"> github.stats",p["key"],11,"700"),
        tx(495,342,f'Repos .......... {s["repos"]}',p["text"],11),
        tx(495,362,f'Stars .......... {s["stars"]}',p["text"],11),
        tx(495,382,f'Followers ...... {s["followers"]}',p["text"],11),
        tx(495,402,f'Following ...... {s["following"]}',p["text"],11),
        tx(495,429,"Build. Break. Understand. Rebuild.",p["dim"],11),
    ]
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1037" height="470" viewBox="0 0 1037 470" font-family="Consolas, Courier New, monospace"><rect width="1037" height="470" rx="15" fill="{p["bg"]}"/><rect x="1" y="1" width="1035" height="468" rx="15" fill="none" stroke="{p["dim"]}"/>{"" .join(out)}</svg>'

def graph_svg(dark, ds):
    p = palette(dark)
    today = date.today()
    cutoff = today - timedelta(days=364)
    data = {d["date"]: d["level"] for d in ds if cutoff <= d["date"] <= today}
    body = [tx(28,39,"Contribution Graph",p["key"],15,"700"),
            tx(872,39,f"daily · {today:%B %Y}",p["dim"],10,anchor="end"),
            tx(28,79,sum(1 for v in data.values() if v),p["text"],24),
            tx(28,95,"Active Days",p["dim"],10),
            tx(200,79,len(data),p["text"],24),
            tx(200,95,"Calendar Days",p["dim"],10)]
    for d, level in sorted(data.items()):
        pos = (d - cutoff).days
        col, row = divmod(pos, 7)
        body.append(f'<rect x="{30+col*14}" y="{112+row*15}" width="11" height="11" rx="2" fill="{p["key"]}" fill-opacity="{0.16+0.18*min(level,4):.2f}"><title>{esc(d)} · level {level}</title></rect>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300" font-family="Consolas, Courier New, monospace"><rect width="900" height="300" rx="15" fill="{p["bg"]}"/>{"" .join(body)}</svg>'

def activity_svg(dark, ds, s):
    p = palette(dark)
    today = date.today()
    buckets = defaultdict(int)
    for d in ds:
        if today - timedelta(days=120) <= d["date"] <= today:
            buckets[d["date"].strftime("%b")] += d["level"]
    names = list(buckets)[-4:]
    peak = max([buckets[n] for n in names] or [1])
    body = [tx(28,39,"Contribution Activity",p["key"],15,"700"),
            tx(872,39,"last 4 months",p["dim"],10,anchor="end"),
            tx(28,79,s["repos"],p["text"],24), tx(28,95,"Repositories",p["dim"],10),
            tx(220,79,s["stars"],p["text"],24), tx(220,95,"Stars",p["dim"],10),
            tx(372,79,s["followers"],p["text"],24), tx(372,95,"Followers",p["dim"],10)]
    for i, n in enumerate(names):
        h = 150 * buckets[n] / peak if peak else 0
        x = 90 + i*170
        body += [f'<rect x="{x}" y="{260-h:.1f}" width="90" height="{h:.1f}" rx="3" fill="{p["key"]}"/>',
                 tx(x+45,283,n,p["dim"],10,anchor="middle"),
                 tx(x+45,250-h,buckets[n],p["text"],10,"700",anchor="middle")]
    body.append(f'<line x1="50" y1="260" x2="870" y2="260" stroke="{p["dim"]}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="310" viewBox="0 0 900 310" font-family="Consolas, Courier New, monospace"><rect width="900" height="310" rx="15" fill="{p["bg"]}"/>{"" .join(body)}</svg>'

def main():
    s = stats()
    ds = fetch_contributions()
    for dark, suffix in [(True,"dark"),(False,"light")]:
        (ROOT/f"profile_{suffix}.svg").write_text(profile_svg(dark,s), encoding="utf-8")
        (ROOT/f"graph_{suffix}.svg").write_text(graph_svg(dark,ds), encoding="utf-8")
        (ROOT/f"activity_{suffix}.svg").write_text(activity_svg(dark,ds,s), encoding="utf-8")

if __name__ == "__main__":
    main()
