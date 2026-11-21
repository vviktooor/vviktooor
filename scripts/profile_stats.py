#!/usr/bin/env python3
"""Generuje karty statystyk profilu GitHub w kolorach WR v4.0.

Pobiera dane z GitHub GraphQL API (token w GH_TOKEN) albo z pliku --fixture
i zapisuje cztery pliki SVG: activity-{light,dark}.svg, languages-{light,dark}.svg.

Autor: WR
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"

# Tokeny WR v4.0 (WR-Colors.json + neutralne z WR-Colors.css).
INK, SIGNAL, BLUE, SLATE, PAPER, LINE, WHITE = (
    "#121B2B", "#20C9B0", "#3267E9", "#526077", "#F5F7FB", "#D9DEE6", "#FFFFFF")

THEMES = {
    "light": {"bg": PAPER, "border": LINE, "text": INK, "muted": SLATE,
              "accent": BLUE, "grid": LINE,
              "series": [SIGNAL, BLUE, INK, SLATE], "other": LINE},
    "dark": {"bg": INK, "border": SLATE, "text": WHITE, "muted": LINE,
             "accent": SIGNAL, "grid": "#283346",
             "series": [SIGNAL, BLUE, PAPER, SLATE], "other": "#283346"},
}
FONT = "Poppins, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"
TOP_LANGUAGES = 4  # paleta WR ma 4 kolory serii + „Other”


# ---------------------------------------------------------------- dane

def graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "wr-profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL: {body['errors']}")
    return body["data"]


def fetch(token: str, login: str, today: dt.date) -> dict:
    """Zwraca {'days': [(iso, count)], 'languages': {name: bytes}, 'since': rok}."""
    user = graphql(token, "query($l:String!){user(login:$l){createdAt}}", {"l": login})["user"]
    start_year = int(user["createdAt"][:4])

    days: dict[str, int] = {}
    for year in range(start_year, today.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z"
        data = graphql(token, """query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){
            contributionsCollection(from:$f,to:$t){contributionCalendar{
            weeks{contributionDays{date contributionCount}}}}}}""",
                       {"l": login, "f": frm, "t": to})
        for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    languages: dict[str, int] = {}
    cursor = None
    while True:
        data = graphql(token, """query($l:String!,$c:String){user(login:$l){
            repositories(first:100,after:$c,ownerAffiliations:OWNER,isFork:false){
            pageInfo{hasNextPage endCursor}
            nodes{languages(first:20,orderBy:{field:SIZE,direction:DESC}){
            edges{size node{name}}}}}}}""", {"l": login, "c": cursor})
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                languages[name] = languages.get(name, 0) + edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    return {"days": sorted(days.items()), "languages": languages, "since": start_year}


# ---------------------------------------------------------------- obliczenia

def streaks(days: list[tuple[str, int]], today: dt.date) -> dict:
    """Total, bieżąca i najdłuższa seria. Brak wpisu za dziś nie przerywa serii."""
    counts = {dt.date.fromisoformat(d): c for d, c in days if dt.date.fromisoformat(d) <= today}
    total = sum(counts.values())

    longest = (0, None, None)
    run_start, run_len = None, 0
    for day in sorted(counts):
        if counts[day] > 0:
            if run_len and day - dt.timedelta(days=1) in counts and counts[day - dt.timedelta(days=1)] > 0:
                run_len += 1
            else:
                run_start, run_len = day, 1
            if run_len > longest[0]:
                longest = (run_len, run_start, day)

    end = today if counts.get(today, 0) > 0 else today - dt.timedelta(days=1)
    current, day = 0, end
    while counts.get(day, 0) > 0:
        current += 1
        day -= dt.timedelta(days=1)
    current_range = (day + dt.timedelta(days=1), end) if current else (None, None)

    return {"total": total, "current": current, "current_range": current_range,
            "longest": longest[0], "longest_range": longest[1:]}


def weekly(days: list[tuple[str, int]], today: dt.date, weeks: int = 52) -> list[tuple[dt.date, int]]:
    """Suma kontrybucji w ostatnich `weeks` tygodniach (tydzień od poniedziałku)."""
    first = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks - 1)
    buckets = [[first + dt.timedelta(weeks=i), 0] for i in range(weeks)]
    for iso, count in days:
        day = dt.date.fromisoformat(iso)
        if first <= day <= today:
            buckets[(day - first).days // 7][1] += count
    return [(start, total) for start, total in buckets]


def language_shares(languages: dict[str, int], exclude: set[str]) -> list[tuple[str, float]]:
    items = sorted(((n, b) for n, b in languages.items() if n not in exclude and b > 0),
                   key=lambda x: -x[1])
    total = sum(b for _, b in items)
    if not total:
        return []
    shares = [(n, b / total) for n, b in items[:TOP_LANGUAGES]]
    rest = sum(b for _, b in items[TOP_LANGUAGES:])
    if rest:
        shares.append(("Other", rest / total))
    return shares


# ---------------------------------------------------------------- SVG

def fmt_range(rng: tuple) -> str:
    start, end = rng
    if not start:
        return "No active streak"
    a, b = start.strftime("%b %-d"), end.strftime("%b %-d, %Y")
    return b if start == end else f"{a} – {b}"


def card(width: int, height: int, theme: dict, label: str, body: str, aria: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria)}">'
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" '
            f'fill="{theme["bg"]}" stroke="{theme["border"]}"/>'
            f'<rect x="40" y="38" width="4" height="20" rx="2" fill="{SIGNAL}"/>'
            f'<text x="56" y="54" font-family="{MONO}" font-size="16" letter-spacing="2" '
            f'fill="{theme["muted"]}">{escape(label)}</text>{body}</svg>\n')


def activity_svg(stats: dict, weeks: list, since: int, theme: dict) -> str:
    w, h = 1200, 430
    kpis = [("Total contributions", f'{stats["total"]:,}'.replace(",", " "), f"Since {since}"),
            ("Current streak", f'{stats["current"]} d', fmt_range(stats["current_range"])),
            ("Longest streak", f'{stats["longest"]} d', fmt_range(stats["longest_range"]))]
    parts = []
    col = (w - 80) / 3
    for i, (title, value, sub) in enumerate(kpis):
        x = 40 + i * col
        if i:
            parts.append(f'<rect x="{x - 1:.0f}" y="96" width="1" height="104" fill="{theme["grid"]}"/>')
        tx = x + (24 if i else 0)
        parts.append(
            f'<text x="{tx:.0f}" y="118" font-family="{FONT}" font-size="16" fill="{theme["muted"]}">{title}</text>'
            f'<text x="{tx:.0f}" y="172" font-family="{FONT}" font-size="48" font-weight="700" '
            f'fill="{theme["text"]}">{escape(value)}</text>'
            f'<text x="{tx:.0f}" y="198" font-family="{MONO}" font-size="14" fill="{theme["accent"]}">{escape(sub)}</text>')

    # Słupki tygodniowe: jedna seria, jeden odcień (signal), zaokrąglony wierzch.
    top, base, left, right = 266, 372, 40, w - 40
    peak = max((c for _, c in weeks), default=0)
    step = (right - left) / len(weeks)
    bar = max(step - 4, 2)
    parts.append(f'<text x="{left}" y="244" font-family="{FONT}" font-size="16" fill="{theme["muted"]}">'
                 f'Contributions per week · last 12 months · peak {peak}</text>')
    parts.append(f'<rect x="{left}" y="{base}" width="{right - left}" height="1" fill="{theme["grid"]}"/>')
    for i, (start, count) in enumerate(weeks):
        x = left + i * step + (step - bar) / 2
        if count:
            bh = max((base - top) * count / peak, 4)
            parts.append(f'<path d="M{x:.1f} {base} V{base - bh + 4:.1f} q0 -4 4 -4 H{x + bar - 4:.1f} '
                         f'q4 0 4 4 V{base} Z" fill="{SIGNAL}"/>')
        if i and start.month != weeks[i - 1][0].month:
            parts.append(f'<text x="{x:.1f}" y="{base + 24}" font-family="{MONO}" font-size="13" '
                         f'fill="{theme["muted"]}">{start.strftime("%b")}</text>')
    aria = (f'Activity: {stats["total"]} total contributions since {since}, current streak '
            f'{stats["current"]} days, longest streak {stats["longest"]} days.')
    return card(w, h, theme, "ACTIVITY", "".join(parts), aria)


def languages_svg(shares: list, theme: dict) -> str:
    w, h = 1200, 230
    left, right, y = 40, w - 40, 92
    parts = []
    if not shares:
        parts.append(f'<text x="{left}" y="130" font-family="{FONT}" font-size="18" '
                     f'fill="{theme["muted"]}">No language data yet</text>')
    else:
        # Jeden pasek „część całości”, 2 px przerwy między segmentami.
        avail = right - left - 2 * (len(shares) - 1)
        x = left
        for i, (name, share) in enumerate(shares):
            color = theme["other"] if name == "Other" else theme["series"][i]
            seg = max(avail * share, 3)
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{seg:.1f}" height="20" rx="4" fill="{color}"/>')
            x += seg + 2
        col = (right - left) / len(shares)
        for i, (name, share) in enumerate(shares):
            color = theme["other"] if name == "Other" else theme["series"][i]
            lx = left + i * col
            parts.append(
                f'<circle cx="{lx + 7:.0f}" cy="{154}" r="7" fill="{color}" stroke="{theme["border"]}"/>'
                f'<text x="{lx + 24:.0f}" y="160" font-family="{FONT}" font-size="18" font-weight="600" '
                f'fill="{theme["text"]}">{escape(name)}</text>'
                f'<text x="{lx + 24:.0f}" y="188" font-family="{MONO}" font-size="16" '
                f'fill="{theme["muted"]}">{share * 100:.1f}%</text>')
    aria = "Languages: " + ", ".join(f"{n} {s * 100:.1f}%" for n, s in shares)
    return card(w, h, theme, "MOST USED LANGUAGES", "".join(parts), aria or "Languages")


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--login", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "vviktooor"))
    p.add_argument("--out", default="dist")
    p.add_argument("--fixture", help="plik JSON z danymi zamiast API (testy)")
    p.add_argument("--today", help="data YYYY-MM-DD (testy)")
    p.add_argument("--exclude", default=os.environ.get("EXCLUDE_LANGUAGES", ""),
                   help="języki pomijane, rozdzielone przecinkami")
    args = p.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            print("Brak GH_TOKEN", file=sys.stderr)
            return 2
        data = fetch(token, args.login, today)

    stats = streaks(data["days"], today)
    weeks = weekly(data["days"], today)
    shares = language_shares(data["languages"], {x.strip() for x in args.exclude.split(",") if x.strip()})

    os.makedirs(args.out, exist_ok=True)
    for mode, theme in THEMES.items():
        with open(os.path.join(args.out, f"activity-{mode}.svg"), "w", encoding="utf-8") as fh:
            fh.write(activity_svg(stats, weeks, data["since"], theme))
        with open(os.path.join(args.out, f"languages-{mode}.svg"), "w", encoding="utf-8") as fh:
            fh.write(languages_svg(shares, theme))
    print(json.dumps({"total": stats["total"], "current": stats["current"],
                      "longest": stats["longest"], "languages": shares}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
