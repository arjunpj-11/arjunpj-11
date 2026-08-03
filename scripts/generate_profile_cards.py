#!/usr/bin/env python3
'''Generate dependency-free GitHub profile SVG cards.

Uses the authenticated GitHub GraphQL API, then writes local SVG assets so the
README does not depend on the rate-limited public github-readme-stats instance.
'''

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

API_URL = "https://api.github.com/graphql"
OUT_DIR = Path(__file__).resolve().parents[1] / "assets"
COPPER = "#B87333"
FG = "#F5F1EA"
MUTED = "#8A8A8A"
BG = "#000000"
RULE = "#1A1A1A"
PALETTE = ["#B87333", "#D39A69", "#8A4F25", "#F5F1EA", "#8A8A8A", "#4A2A16"]

QUERY = r"""
query ProfileCards($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      isFork: false
      orderBy: { field: UPDATED_AT, direction: DESC }
    ) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges {
            size
            node { name }
          }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
"""


def graphql(token: str, username: str) -> dict[str, Any]:
    body = json.dumps({"query": QUERY, "variables": {"login": username}}).encode()
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "arjunpj-11-profile-cards",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc

    if payload.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + json.dumps(payload["errors"]))
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user {username!r} was not found")
    return user


def streaks(days: list[dict[str, Any]]) -> tuple[int, int]:
    counts = {
        dt.date.fromisoformat(day["date"]): int(day["contributionCount"])
        for day in days
    }
    if not counts:
        return 0, 0

    start, end = min(counts), max(counts)
    longest = running = 0
    cursor = start
    while cursor <= end:
        if counts.get(cursor, 0) > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0
        cursor += dt.timedelta(days=1)

    current_end = end
    if counts.get(current_end, 0) == 0:
        current_end -= dt.timedelta(days=1)
    current = 0
    while current_end >= start and counts.get(current_end, 0) > 0:
        current += 1
        current_end -= dt.timedelta(days=1)
    return current, longest


def flatten_days(calendar: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        day
        for week in calendar.get("weeks", [])
        for day in week.get("contributionDays", [])
    ]


def xml_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def metric(x: int, y: int, value: Any, label: str, note: str = "") -> str:
    return f"""
      <g transform="translate({x},{y})">
        <text class="value" x="0" y="0">{xml_text(value)}</text>
        <text class="label" x="0" y="28">{xml_text(label)}</text>
        <text class="note" x="0" y="49">{xml_text(note)}</text>
      </g>"""


def render_stats(username: str, user: dict[str, Any]) -> str:
    repos = user["repositories"]
    nodes = repos.get("nodes") or []
    stars = sum(int(repo.get("stargazerCount") or 0) for repo in nodes)
    forks = sum(int(repo.get("forkCount") or 0) for repo in nodes)
    contributions = user["contributionsCollection"]
    calendar = contributions["contributionCalendar"]
    current, longest = streaks(flatten_days(calendar))

    metrics = [
        (80, 128, calendar.get("totalContributions", 0), "TOTAL CONTRIBUTIONS", "LAST 12 MONTHS"),
        (430, 128, current, "CURRENT STREAK", "DAYS"),
        (780, 128, longest, "LONGEST STREAK", "LAST 12 MONTHS"),
        (80, 235, repos.get("totalCount", 0), "PUBLIC REPOSITORIES", "OWNER · NON-FORK"),
        (430, 235, stars, "STARS EARNED", f"{forks} FORKS"),
        (780, 235, contributions.get("totalPullRequestContributions", 0), "PULL REQUESTS", f"{contributions.get('totalIssueContributions', 0)} ISSUES"),
    ]
    metric_svg = "".join(metric(*item) for item in metrics)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("UPDATED %d %b %Y · %H:%M UTC").upper()

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 300" role="img" aria-label="{xml_text(username)} GitHub signals">
  <style><![CDATA[
    .bg{{fill:{BG}}}.frame{{fill:none;stroke:{RULE}}}.copper{{fill:{COPPER}}}
    .head,.label,.note,.meta{{font-family:'JetBrains Mono','Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em}}
    .head{{fill:{MUTED};font-size:11px}}.value{{fill:{FG};font-family:Georgia,'Times New Roman',serif;font-size:36px;font-style:italic}}
    .label{{fill:{FG};font-size:11px}}.note{{fill:{MUTED};font-size:9px}}.meta{{fill:{MUTED};font-size:9px}}
  ]]></style>
  <rect class="bg" width="1200" height="300"/>
  <rect class="frame" x="1" y="1" width="1198" height="298"/>
  <text class="head" x="48" y="46">GITHUB SIGNALS · @{xml_text(username.upper())}</text>
  <line x1="48" y1="62" x2="190" y2="62" stroke="{COPPER}" stroke-width="1.5"/>
  <text class="meta" x="1152" y="46" text-anchor="end">{stamp}</text>
  <line x1="400" y1="82" x2="400" y2="265" stroke="{RULE}"/>
  <line x1="750" y1="82" x2="750" y2="265" stroke="{RULE}"/>
  <line x1="48" y1="183" x2="1152" y2="183" stroke="{RULE}"/>
  {metric_svg}
</svg>
'''


def render_languages(username: str, user: dict[str, Any]) -> str:
    totals: defaultdict[str, int] = defaultdict(int)
    for repo in user["repositories"].get("nodes") or []:
        for edge in (repo.get("languages") or {}).get("edges") or []:
            name = edge.get("node", {}).get("name")
            size = int(edge.get("size") or 0)
            if name and size > 0:
                totals[name] += size

    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:6]
    grand_total = sum(totals.values())
    if not ordered or grand_total <= 0:
        ordered = [("No public language data", 1)]
        grand_total = 1

    percents = [(name, size / grand_total * 100) for name, size in ordered]
    # Keep the rounded bar visually complete by assigning residual width to the final segment.
    bar_x, bar_y, bar_w = 48.0, 92.0, 1104.0
    parts: list[str] = []
    cursor = bar_x
    for index, (name, pct) in enumerate(percents):
        width = bar_x + bar_w - cursor if index == len(percents) - 1 else bar_w * pct / 100
        parts.append(f'<rect x="{cursor:.2f}" y="{bar_y}" width="{max(width, 1):.2f}" height="18" fill="{PALETTE[index % len(PALETTE)]}"/>')
        cursor += width

    rows: list[str] = []
    for index, (name, pct) in enumerate(percents):
        col = index // 3
        row = index % 3
        x = 70 + col * 575
        y = 157 + row * 43
        color = PALETTE[index % len(PALETTE)]
        rows.append(f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="-11" width="10" height="10" rx="2" fill="{color}"/>
      <text class="lang" x="24" y="0">{xml_text(name)}</text>
      <text class="pct" x="510" y="0" text-anchor="end">{pct:.1f}%</text>
    </g>''')

    stamp = dt.datetime.now(dt.timezone.utc).strftime("UPDATED %d %b %Y · %H:%M UTC").upper()
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 300" role="img" aria-label="{xml_text(username)} top languages">
  <style><![CDATA[
    .bg{{fill:{BG}}}.frame{{fill:none;stroke:{RULE}}}
    .head,.lang,.pct,.meta,.foot{{font-family:'JetBrains Mono','Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}}
    .head{{fill:{MUTED};font-size:11px}}.lang{{fill:{FG};font-size:12px}}.pct{{fill:{MUTED};font-size:11px}}
    .meta,.foot{{fill:{MUTED};font-size:9px}}
  ]]></style>
  <rect class="bg" width="1200" height="300"/>
  <rect class="frame" x="1" y="1" width="1198" height="298"/>
  <text class="head" x="48" y="46">TOP LANGUAGES · PUBLIC OWNER REPOSITORIES</text>
  <line x1="48" y1="62" x2="190" y2="62" stroke="{COPPER}" stroke-width="1.5"/>
  <text class="meta" x="1152" y="46" text-anchor="end">{stamp}</text>
  <rect x="48" y="92" width="1104" height="18" fill="#141414"/>
  {''.join(parts)}
  {''.join(rows)}
  <text class="foot" x="48" y="277">BYTES OF CODE · EXCLUDES FORKS · NOT A MEASURE OF PROFICIENCY</text>
</svg>
'''


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    username = os.environ.get("GITHUB_USERNAME", "").strip()
    if not token or not username:
        print("GITHUB_TOKEN and GITHUB_USERNAME are required", file=sys.stderr)
        return 2

    try:
        user = graphql(token, username)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "github-stats.svg").write_text(render_stats(username, user), encoding="utf-8")
        (OUT_DIR / "top-languages.svg").write_text(render_languages(username, user), encoding="utf-8")
    except Exception as exc:  # Keep previous cards intact if the API is temporarily unavailable.
        print(f"Profile card generation failed: {exc}", file=sys.stderr)
        return 1

    print("Generated assets/github-stats.svg and assets/top-languages.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
