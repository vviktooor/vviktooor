#!/usr/bin/env python3
"""Generuje animowany baner profilu (WR v4.0) w wersji jasnej i ciemnej.

Użycie: python scripts/banner.py <katalog z SVG logo WR> [--out assets]
Monogram WR jest wklejany 1:1 z oficjalnych plików (WR-06 / WR-07), bez zmiany geometrii.
Animacje: CSS + SMIL w SVG; stan końcowy jest stanem bazowym.

Autor: WR
"""
from __future__ import annotations

import argparse
import os
import re

INK, SIGNAL, BLUE, SLATE, PAPER, LINE, WHITE = (
    "#121B2B", "#20C9B0", "#3267E9", "#526077", "#F5F7FB", "#D9DEE6", "#FFFFFF")
FONT = "Poppins, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"
W, H = 1200, 300
HANDLE = "vviktooor"

THEMES = {
    "dark": {"bg": INK, "fg": WHITE, "border": SLATE, "dots": SLATE, "accent": SIGNAL,
             "logo": "WR-07-Negative.svg"},
    "light": {"bg": PAPER, "fg": INK, "border": LINE, "dots": LINE, "accent": BLUE,
              "logo": "WR-06-Positive.svg"},
}

CSS = """<style>
.in{animation:in .9s cubic-bezier(.22,1,.36,1) both}
.grow{transform-box:fill-box;transform-origin:50% 50%;animation:grow .7s cubic-bezier(.22,1,.36,1) .5s both}
.blink{animation:blink 1s steps(1) infinite}
@keyframes in{from{opacity:0;transform:translateX(-24px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){.in,.grow,.blink{animation:none}}
</style>"""


def logo(path: str) -> str:
    """Oficjalny monogram jako zagnieżdżony <svg> (300x156 → 450x234)."""
    with open(path, encoding="utf-8") as fh:
        svg = fh.read().strip()
    svg = svg.replace('width="300" height="156"', 'width="450" height="234"', 1)
    return re.sub(r"^<svg ", '<svg x="70" y="33" ', svg, count=1)


def banner(theme: dict, logos: str) -> str:
    chars, char_w, x0 = len(HANDLE), 46, 620
    text_w = chars * char_w
    typing = ";".join(str(round(text_w * i / chars)) for i in range(chars + 1))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="WR · {HANDLE}">
{CSS}
<defs>
<clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath>
<clipPath id="handle"><rect x="{x0 - 4}" y="90" width="{text_w + 20}" height="110"><animate attributeName="width" values="{typing}" begin=".8s" dur="1.1s" calcMode="discrete" fill="freeze"/></rect></clipPath>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.5" fill="{theme["dots"]}"/><animateTransform attributeName="patternTransform" type="translate" from="0 0" to="24 24" dur="8s" repeatCount="indefinite"/></pattern>
<linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{theme["bg"]}"/><stop offset="1" stop-color="{theme["bg"]}" stop-opacity="0"/></linearGradient>
<linearGradient id="shine" x1="0" x2="1"><stop offset="0" stop-color="{WHITE}" stop-opacity="0"/><stop offset=".5" stop-color="{WHITE}" stop-opacity=".75"/><stop offset="1" stop-color="{WHITE}" stop-opacity="0"/></linearGradient>
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="{theme["bg"]}"/>
<rect x="560" width="640" height="{H}" fill="url(#dots)" opacity=".45"/>
<rect x="560" width="360" height="{H}" fill="url(#fade)"/>
<g class="in">{logo(os.path.join(logos, theme["logo"]))}</g>
<rect x="0" y="292" width="{W}" height="8" fill="{SIGNAL}"/>
<rect x="-240" y="292" width="240" height="8" fill="url(#shine)"><animateTransform attributeName="transform" type="translate" from="0 0" to="{W + 240} 0" begin="1s" dur="3.2s" repeatCount="indefinite"/></rect>
</g>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="{theme["border"]}"/>
<rect class="grow" x="576" y="96" width="4" height="108" rx="2" fill="{SIGNAL}"/>
<text x="{x0}" y="174" clip-path="url(#handle)" font-family="{MONO}" font-size="76" font-weight="700" fill="{theme["fg"]}">{HANDLE}</text>
<rect class="blink" x="{x0 + text_w + 8}" y="112" width="14" height="70" fill="{theme["accent"]}"/>
</svg>
'''


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("logos", help="katalog z oficjalnymi SVG WR (WR-10, WR-11)")
    p.add_argument("--out", default="assets")
    args = p.parse_args()
    for mode, theme in THEMES.items():
        with open(os.path.join(args.out, f"wr-banner-{mode}.svg"), "w", encoding="utf-8") as fh:
            fh.write(banner(theme, args.logos))


if __name__ == "__main__":
    main()
