#!/usr/bin/env python3
"""Generuje karty statystyk profilu GitHub w kolorach WR v4.0.

Pobiera dane z GitHub GraphQL API (token w GH_TOKEN) albo z pliku --fixture
i zapisuje karty SVG: activity-, languages- i (jeśli jest surowy wąż) snake-{light,dark}.svg.

Autor: WR
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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
             "accent": SIGNAL, "grid": "#283346", "scan": True,
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
    """Zwraca {'days': [(iso, count)], 'languages': {name: udział sumowany po repo}, 'since': rok}."""
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

    languages: dict[str, float] = {}
    counted = {"public": 0, "private": 0}
    # Prywatne repo zwraca tylko `viewer` (właściciel tokenu), nie `user(login:)`.
    try:
        own = graphql(token, "query{viewer{login}}", {})["viewer"]["login"].lower() == login.lower()
    except (RuntimeError, KeyError, TypeError):
        own = False  # np. GITHUB_TOKEN w Actions
    root, args = ("viewer", "") if own else ("user(login:$l)", "$l:String!,")
    cursor = None
    while True:
        data = graphql(token, f"""query({args}$c:String){{{root}{{
            repositories(first:100,after:$c,ownerAffiliations:OWNER,isFork:false){{
            pageInfo{{hasNextPage endCursor}}
            nodes{{isPrivate languages(first:20,orderBy:{{field:SIZE,direction:DESC}}){{
            edges{{size node{{name}}}}}}}}}}}}}}""", {"c": cursor, **({} if own else {"l": login})})
        repos = data["viewer" if own else "user"]["repositories"]
        for repo in repos["nodes"]:
            counted["private" if repo.get("isPrivate") else "public"] += 1
            # Każde repo waży tyle samo: jeden duży projekt nie zagłusza reszty.
            edges = repo["languages"]["edges"]
            repo_total = sum(e["size"] for e in edges)
            for edge in edges:
                name = edge["node"]["name"]
                languages[name] = languages.get(name, 0) + edge["size"] / repo_total
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    # Diagnostyka: bez STATS_TOKEN prywatnych repo będzie 0.
    print(f"Token: {os.environ.get('TOKEN_SOURCE', '?')}, zapytanie: {'viewer' if own else 'user'}", file=sys.stderr)
    print(f"Repozytoria: {counted['public']} publicznych, {counted['private']} prywatnych", file=sys.stderr)
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


def language_shares(languages: dict[str, float], exclude: set[str]) -> list[tuple[str, float]]:
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
# Animacje: tylko CSS/SMIL wewnątrz SVG (GitHub nie uruchamia JS w README).
# Stan końcowy jest stanem bazowym, więc bez animacji karta wygląda poprawnie.

EASE = "cubic-bezier(.22,1,.36,1)"
CSS = f"""<style>
.wr-in{{animation:wr-in .7s {EASE} both}}
.wr-grow-y{{transform-box:fill-box;transform-origin:50% 100%;animation:wr-grow-y .9s {EASE} both}}
.wr-grow-x{{transform-box:fill-box;transform-origin:0 50%;animation:wr-grow-x 1s {EASE} both}}
.wr-blink{{animation:wr-blink 1s steps(1) infinite}}
@keyframes wr-in{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
@keyframes wr-grow-y{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes wr-grow-x{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes wr-blink{{50%{{fill-opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.wr-in,.wr-grow-y,.wr-grow-x,.wr-blink{{animation:none}}}}
</style>"""


def delay(seconds: float) -> str:
    return f' style="animation-delay:{seconds:.2f}s"'


def count_up(x: float, y: float, value: int, suffix: str, attrs: str, start: float = .3,
             steps: int = 14, duration: float = 1.1) -> str:
    """Licznik „od zera” z klatek tekstu przełączanych przez SMIL; bez SMIL widać wartość końcową."""
    if value <= 0:
        return f'<text x="{x:.0f}" y="{y}" {attrs}>{value}{suffix}</text>'
    frames = sorted({round(value * (1 - (1 - i / steps) ** 3)) for i in range(steps)} - {value})
    slot = duration / (len(frames) + 1)
    out = []
    for i, v in enumerate(frames):
        out.append(f'<text x="{x:.0f}" y="{y}" {attrs} opacity="0">{fmt_int(v)}{suffix}'
                   f'<set attributeName="opacity" to="1" begin="{start + i * slot:.3f}s" dur="{slot:.3f}s"/></text>')
    end = start + len(frames) * slot
    out.append(f'<text x="{x:.0f}" y="{y}" {attrs}>{fmt_int(value)}{suffix}'
               f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{end / (end + .01):.4f};1" '
               f'dur="{end + .01:.3f}s" fill="freeze"/></text>')
    return "".join(out)


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def fmt_range(rng: tuple) -> str:
    start, end = rng
    if not start:
        return "No active streak"
    a, b = start.strftime("%b %-d"), end.strftime("%b %-d, %Y")
    return b if start == end else f"{a} – {b}"


PROMPT = "wr@root:~$ "
CHAR_W = 10.5  # górne oszacowanie szerokości znaku MONO przy 16 px (fonty zastępcze)


def card(width: int, height: int, theme: dict, label: str, body: str, aria: str) -> str:
    """Karta WR w stylu terminala: pisany nagłówek z kursorem i linie CRT (w ciemnym motywie)."""
    full = len(PROMPT) + len(label) + 2
    text_w = round(full * CHAR_W)
    steps = ";".join(str(round(text_w * i / full)) for i in range(full + 1))
    scan = ""
    if theme.get("scan"):
        # linie CRT jako zwykła ścieżka, bez <pattern>: część przeglądarek obrazów
        # (np. aplikacja GitHub na telefonie) nie obsługuje wzorców i maluje wtedy czarny prostokąt
        lines = "".join(f"M1 {y}h{width - 2}" for y in range(3, height - 1, 4))
        scan = (f'<path d="{lines}" stroke="#000000" stroke-width="2" stroke-opacity=".22" '
                f'pointer-events="none"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria)}">{CSS}'
            f'<defs><clipPath id="wr-label"><rect x="36" y="36" width="{text_w + 8}" height="26">'
            f'<animate attributeName="width" values="{steps}" dur=".6s" calcMode="discrete" fill="freeze"/>'
            f'</rect></clipPath></defs>'
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" '
            f'fill="{theme["bg"]}" stroke="{theme["border"]}"/>'
            f'<text x="40" y="54" clip-path="url(#wr-label)" font-family="{MONO}" font-size="16">'
            f'<tspan fill="{theme["accent"]}">{PROMPT}</tspan>'
            f'<tspan fill="{theme["muted"]}">{escape(label)}</tspan>'
            f'<tspan class="wr-blink" fill="{theme["accent"]}"> █</tspan></text>'
            f'{body}{scan}</svg>\n')


def activity_svg(stats: dict, weeks: list, since: int, theme: dict) -> str:
    w, h = 1200, 430
    kpis = [("Total contributions", stats["total"], "", f"Since {since}"),
            ("Current streak", stats["current"], " d", fmt_range(stats["current_range"])),
            ("Longest streak", stats["longest"], " d", fmt_range(stats["longest_range"]))]
    parts = []
    col = (w - 80) / 3
    big = f'font-family="{FONT}" font-size="48" font-weight="700" fill="{theme["text"]}"'
    for i, (title, value, suffix, sub) in enumerate(kpis):
        x = 40 + i * col
        if i:
            parts.append(f'<rect class="wr-grow-y" x="{x - 1:.0f}" y="96" width="1" height="104" '
                         f'fill="{theme["grid"]}"{delay(.2 + i * .1)}/>')
        tx = x + (24 if i else 0)
        parts.append(
            f'<g class="wr-in"{delay(.1 + i * .12)}>'
            f'<text x="{tx:.0f}" y="118" font-family="{FONT}" font-size="16" fill="{theme["muted"]}">{title}</text>'
            f'{count_up(tx, 172, value, suffix, big, start=.3 + i * .12)}'
            f'<text x="{tx:.0f}" y="198" font-family="{MONO}" font-size="14" fill="{theme["accent"]}">'
            f'{escape(sub)}</text></g>')

    # Słupki tygodniowe: jedna seria, jeden odcień (signal), zaokrąglony wierzch, rosną po kolei.
    top, base, left, right = 266, 372, 40, w - 40
    peak = max((c for _, c in weeks), default=0)
    step = (right - left) / len(weeks)
    bar = max(step - 4, 2)
    parts.append(f'<text class="wr-in" x="{left}" y="244" font-family="{FONT}" font-size="16" '
                 f'fill="{theme["muted"]}"{delay(.5)}>Contributions per week · last 12 months · peak {peak}</text>')
    parts.append(f'<rect class="wr-grow-x" x="{left}" y="{base}" width="{right - left}" height="1" '
                 f'fill="{theme["grid"]}"{delay(.4)}/>')
    for i, (start, count) in enumerate(weeks):
        x = left + i * step + (step - bar) / 2
        if count:
            bh = max((base - top) * count / peak, 4)
            parts.append(f'<path class="wr-grow-y" d="M{x:.1f} {base} V{base - bh + 4:.1f} q0 -4 4 -4 '
                         f'H{x + bar - 4:.1f} q4 0 4 4 V{base} Z" fill="{SIGNAL}"{delay(.6 + i * .02)}/>')
        if i and start.month != weeks[i - 1][0].month:
            parts.append(f'<text x="{x:.1f}" y="{base + 24}" font-family="{MONO}" font-size="13" '
                         f'fill="{theme["muted"]}">{start.strftime("%b")}</text>')
    aria = (f'Activity: {stats["total"]} total contributions since {since}, current streak '
            f'{stats["current"]} days, longest streak {stats["longest"]} days.')
    return card(w, h, theme, "./activity --all-time", "".join(parts), aria)


def languages_svg(shares: list, theme: dict) -> str:
    w, h = 1200, 230
    left, right, y = 40, w - 40, 92
    parts = []
    if not shares:
        parts.append(f'<text x="{left}" y="130" font-family="{FONT}" font-size="18" '
                     f'fill="{theme["muted"]}">No language data yet</text>')
    else:
        # Jeden pasek „część całości”, 2 px przerwy między segmentami, segmenty wjeżdżają po kolei.
        avail = right - left - 2 * (len(shares) - 1)
        x = left
        col = (right - left) / len(shares)
        for i, (name, share) in enumerate(shares):
            color = theme["other"] if name == "Other" else theme["series"][i]
            seg = max(avail * share, 3)
            parts.append(f'<rect class="wr-grow-x" x="{x:.1f}" y="{y}" width="{seg:.1f}" height="20" rx="4" '
                         f'fill="{color}"{delay(.2 + i * .15)}/>')
            x += seg + 2
            lx = left + i * col
            parts.append(
                f'<g class="wr-in"{delay(.4 + i * .1)}>'
                f'<circle cx="{lx + 7:.0f}" cy="154" r="7" fill="{color}" stroke="{theme["border"]}"/>'
                f'<text x="{lx + 24:.0f}" y="160" font-family="{FONT}" font-size="18" font-weight="600" '
                f'fill="{theme["text"]}">{escape(name)}</text>'
                f'<text x="{lx + 24:.0f}" y="188" font-family="{MONO}" font-size="16" '
                f'fill="{theme["muted"]}">{share * 100:.1f}%</text></g>')
    aria = "Languages: " + ", ".join(f"{n} {s * 100:.1f}%" for n, s in shares)
    return card(w, h, theme, "./languages --top", "".join(parts), aria or "Languages")


def snake_svg(raw: str, theme: dict) -> str:
    """Wkłada SVG węża (Platane/snk) do karty WR, żeby cały profil miał jeden styl."""
    raw = raw.strip()
    if raw.startswith("<?xml"):
        raw = raw[raw.index("?>") + 2:].lstrip()
    m = re.match(r'<svg[^>]*viewBox="([-\d. ]+)"[^>]*>', raw)
    if not m:
        raise ValueError("Nieoczekiwany format SVG węża")
    vx, vy, vw, vh = (float(v) for v in m.group(1).split())
    w, inner_w = 1200, 1120
    inner_h = round(inner_w * vh / vw)
    h = 84 + inner_h + 24
    inner = (f'<svg x="40" y="84" width="{inner_w}" height="{inner_h}" viewBox="{m.group(1)}">'
             + raw[m.end():])
    return card(w, h, theme, "./contributions --snake", inner, "Snake eating the contribution graph")


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

    def write(name: str, content: str) -> None:
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            fh.write(content)

    for mode, theme in THEMES.items():
        write(f"activity-{mode}.svg", activity_svg(stats, weeks, data["since"], theme))
        write(f"languages-{mode}.svg", languages_svg(shares, theme))
        raw = os.path.join(args.out, f"snake-raw-{mode}.svg")
        if os.path.exists(raw):
            with open(raw, encoding="utf-8") as fh:
                write(f"snake-{mode}.svg", snake_svg(fh.read(), theme))
            os.remove(raw)
    print(json.dumps({"total": stats["total"], "current": stats["current"],
                      "longest": stats["longest"], "languages": shares}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
