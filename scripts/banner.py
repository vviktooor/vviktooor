#!/usr/bin/env python3
"""Generuje animowany baner profilu WR v4.0 w klimacie terminala i glitcha.

Użycie: python scripts/banner.py <katalog z SVG logo WR> [--out assets]
Monogram WR jest wklejany 1:1 z oficjalnego pliku WR-07 (negatyw), bez zmiany geometrii;
efekt glitch to przesunięte kopie znaku w kolorach marki, nie zmiana jego kształtu.
Animacje: CSS + SMIL w SVG (GitHub nie uruchamia JS); stan końcowy jest stanem bazowym.
Baner jest „ekranem” (zawsze ciemny), więc wygląda tak samo w jasnym i ciemnym motywie.

Autor: WR
"""
from __future__ import annotations

import argparse
import os
import re

INK, SIGNAL, BLUE, SLATE, LINE, WHITE = "#121B2B", "#20C9B0", "#3267E9", "#526077", "#D9DEE6", "#FFFFFF"
MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"
W, H = 1200, 300
HANDLE = "vviktooor"
PROMPT = "wr@root:~$ whoami"
STATUS = "> access granted"
X0 = 600  # początek kolumny terminala

CSS = """<style>
.flicker{animation:flicker 7s steps(1) infinite}
.glitch-a{animation:glitch-a 4.5s steps(1) infinite}
.glitch-b{animation:glitch-b 4.5s steps(1) infinite}
.slice{animation:slice 4.5s steps(1) infinite}
.blink{animation:blink 1s steps(1) infinite}
.beam{animation:beam 6s linear infinite}
@keyframes flicker{0%,100%{opacity:1}31%{opacity:.86}32%{opacity:1}77%{opacity:.92}78%{opacity:1}}
@keyframes glitch-a{0%,100%{opacity:0;transform:none}88%{opacity:.9;transform:translate(-9px,0)}90%{opacity:.9;transform:translate(7px,-3px)}92%{opacity:.9;transform:translate(-4px,2px)}94%{opacity:0;transform:none}}
@keyframes glitch-b{0%,100%{opacity:0;transform:none}88%{opacity:.9;transform:translate(8px,2px)}90%{opacity:.9;transform:translate(-6px,0)}92%{opacity:.9;transform:translate(5px,-2px)}94%{opacity:0;transform:none}}
@keyframes slice{0%,100%{transform:none}89%{transform:translate(14px,0)}91%{transform:translate(-10px,0)}93%{transform:none}}
@keyframes blink{50%{fill-opacity:0}}
@keyframes beam{from{transform:translateY(-60px)}to{transform:translateY(320px)}}
@media (prefers-reduced-motion:reduce){.flicker,.glitch-a,.glitch-b,.slice,.blink,.beam{animation:none}}
</style>"""


def mark(path: str) -> str:
    """Oficjalny monogram (300x156) jako <svg id="mark"> do wielokrotnego użycia przez <use>."""
    with open(path, encoding="utf-8") as fh:
        svg = fh.read().strip()
    svg = svg.replace('width="300" height="156"', 'width="420" height="218"', 1)
    return re.sub(r"^<svg ", '<svg id="mark" ', svg, count=1)


def typed(x: int, y: int, text: str, size: int, char_w: float, begin: float, dur: float,
          cid: str, attrs: str) -> tuple[str, str]:
    """Tekst „pisany” znak po znaku: (clipPath do <defs>, element tekstu)."""
    width = round(len(text) * char_w) + 8
    steps = ";".join(str(round(width * i / len(text))) for i in range(len(text) + 1))
    # stan bazowy = pełna szerokość (widoczny tekst bez animacji); do chwili `begin` szerokość 0
    total = begin + dur
    times = ";".join(f"{(begin + dur * i / len(text)) / total:.4f}" for i in range(len(text) + 1))
    clip = (f'<clipPath id="{cid}"><rect x="{x - 4}" y="{y - size}" width="{width}" height="{size + 12}">'
            f'<animate attributeName="width" values="0;{steps}" keyTimes="0;{times}" dur="{total}s" '
            f'calcMode="discrete" fill="freeze"/></rect></clipPath>')
    body = text.replace(" █", '<tspan class="blink"> █</tspan>')
    return clip, (f'<text x="{x}" y="{y}" clip-path="url(#{cid})" font-family="{MONO}" '
                  f'font-size="{size}" {attrs}>{body}</text>')


def grid() -> str:
    """Perspektywiczna siatka „podłogi” przesuwająca się w stronę widza."""
    vx, horizon = 900, 150
    lines = [f'<line x1="{vx}" y1="{horizon}" x2="{x}" y2="{H}"/>' for x in range(-600, 2401, 150)]
    rows = "".join(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}"/>' for y in (168, 186, 210, 240, 276))
    return (f'<g stroke="{SIGNAL}" stroke-width="1" mask="url(#floor)" opacity=".5">{"".join(lines)}'
            f'<g>{rows}<animateTransform attributeName="transform" type="translate" values="0 0;0 18" '
            f'dur="1.6s" repeatCount="indefinite"/></g></g>')


def scanlines() -> str:
    """Linie CRT jako zwykła ścieżka: <pattern> w części przeglądarek obrazów maluje czarny prostokąt."""
    d = "".join(f"M0 {y}h{W}" for y in range(1, H, 4))
    return f'<path d="{d}" stroke="#000000" stroke-width="2" stroke-opacity=".28"/>'


def banner(logos: str) -> str:
    c1, t1 = typed(X0, 112, PROMPT, 20, 13, .4, .9, "t1", f'fill="{LINE}"')
    c2, t2 = typed(X0, 196, HANDLE, 72, 46, 1.5, .8, "t2", f'font-weight="700" fill="{WHITE}"')
    c3, t3 = typed(X0, 238, STATUS + " █", 20, 13, 2.5, .7, "t3", f'fill="{SIGNAL}"')
    handle_copy = (f'<text x="{X0}" y="196" font-family="{MONO}" font-size="72" font-weight="700" '
                   f'clip-path="url(#t2)"')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="WR · {HANDLE}">
{CSS}
<defs>
{mark(os.path.join(logos, "WR-07-Negative.svg"))}
<clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath>
<clipPath id="band1"><rect x="0" y="40" width="440" height="34"/></clipPath>
<clipPath id="band2"><rect x="0" y="150" width="440" height="22"/></clipPath>
{c1}{c2}{c3}
<filter id="tint-signal"><feFlood flood-color="{SIGNAL}"/><feComposite in2="SourceAlpha" operator="in"/></filter>
<filter id="tint-blue"><feFlood flood-color="{BLUE}"/><feComposite in2="SourceAlpha" operator="in"/></filter>
<linearGradient id="floor-fade" x1="0" y1="0" x2="0" y2="1"><stop offset=".5" stop-color="{WHITE}" stop-opacity="0"/><stop offset="1" stop-color="{WHITE}" stop-opacity=".9"/></linearGradient>
<mask id="floor"><rect width="{W}" height="{H}" fill="url(#floor-fade)"/></mask>
<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{SIGNAL}" stop-opacity="0"/><stop offset=".5" stop-color="{SIGNAL}" stop-opacity=".09"/><stop offset="1" stop-color="{SIGNAL}" stop-opacity="0"/></linearGradient>
<linearGradient id="shine" x1="0" x2="1"><stop offset="0" stop-color="{WHITE}" stop-opacity="0"/><stop offset=".5" stop-color="{WHITE}" stop-opacity=".75"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/></linearGradient>
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="{INK}"/>
{grid()}
<g class="flicker">
<g transform="translate(60 41)">
<g class="glitch-a" opacity="0"><use href="#mark" xlink:href="#mark" filter="url(#tint-signal)"/></g>
<g class="glitch-b" opacity="0"><use href="#mark" xlink:href="#mark" filter="url(#tint-blue)"/></g>
<use href="#mark" xlink:href="#mark"/>
<g class="slice" clip-path="url(#band1)"><rect y="40" width="440" height="34" fill="{INK}"/><use href="#mark" xlink:href="#mark"/></g>
<g class="slice" clip-path="url(#band2)"><rect y="150" width="440" height="22" fill="{INK}"/><use href="#mark" xlink:href="#mark"/></g>
</g>
<rect x="{X0 - 36}" y="96" width="3" height="150" fill="{SLATE}"/>
{t1}
<g class="glitch-a" opacity="0">{handle_copy} fill="{SIGNAL}">{HANDLE}</text></g>
<g class="glitch-b" opacity="0">{handle_copy} fill="{BLUE}">{HANDLE}</text></g>
{t2}
{t3}
</g>
<rect class="beam" width="{W}" height="60" fill="url(#beam)"/>
{scanlines()}
<rect x="0" y="292" width="{W}" height="8" fill="{SIGNAL}"/>
<rect x="-240" y="292" width="240" height="8" fill="url(#shine)"><animateTransform attributeName="transform" type="translate" from="0 0" to="{W + 240} 0" begin="1s" dur="3.2s" repeatCount="indefinite"/></rect>
</g>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="{SLATE}"/>
</svg>
'''


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("logos", help="katalog z oficjalnymi SVG WR (WR-07)")
    p.add_argument("--out", default="assets")
    args = p.parse_args()
    with open(os.path.join(args.out, "wr-banner.svg"), "w", encoding="utf-8") as fh:
        fh.write(banner(args.logos))


if __name__ == "__main__":
    main()
