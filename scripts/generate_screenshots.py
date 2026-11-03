#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera le "screenshot" del gioco per il README.

Il trucco: si fa girare la *vera* funzione `snake.render()` su uno schermo
finto che cattura tutte le chiamate `addstr()`, poi ogni cella viene
ridisegnata in PNG con Pillow, riproducendo i colori del terminale
(serpente verde, cibo rosso, interfaccia ciana) dentro una finestra
"stile terminale".

Uso:
    python3 scripts/generate_screenshots.py

Dipendenza: Pillow (solo per generare le immagini, non serve al gioco).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import curses  # usato solo per le costanti A_BOLD / A_REVERSE
from PIL import Image, ImageDraw, ImageFont

import snake

# ---------------------------------------------------------------- tema ---
BG = (23, 26, 31)            # sfondo del terminale
FG = (205, 211, 217)         # testo di default
PAIRS = {                    # id colore -> RGB (come nel gioco: verde/rosso/ciano)
    1: (98, 206, 112),
    2: (231, 94, 94),
    3: (94, 199, 214),
}
BAR_BG = (38, 43, 51)        # barra del titolo della "finestra"
TITLE_FG = (148, 156, 167)
DOTS = ((255, 95, 87), (254, 188, 46), (40, 200, 64))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs"))


def load_fonts(size):
    """Font mono (regolare + grasso) con i glifi usati dal gioco: █ ★ ─ │ ecc."""
    candidates = [
        ("/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf",
         "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
        ("/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf", None),
    ]
    for reg, bold in candidates:
        if os.path.exists(reg):
            f = ImageFont.truetype(reg, size)
            b = ImageFont.truetype(bold, size) if bold and os.path.exists(bold) else f
            return f, b
    try:
        f = ImageFont.load_default(size=size)
    except TypeError:  # Pillow molto vecchio
        f = ImageFont.load_default()
    return f, f


class FakeScreen:
    """Schermo finto: cattura le addstr() della vera snake.render()."""

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.cells = {}

    def getmaxyx(self):
        return self.h, self.w

    def erase(self):
        self.cells.clear()

    def addstr(self, r, c, s, attr=0):
        for i, ch in enumerate(s):
            cc = c + i
            if 0 <= r < self.h and 0 <= cc < self.w:
                self.cells[(r, cc)] = (ch, attr)

    def refresh(self):
        pass


def capture(state, game, note="", best=0):
    """Rende lo stato usando la funzione render() vera del gioco."""
    scr = FakeScreen(game.h + 4, game.w + 2)
    attrs = (1 | curses.A_BOLD, 2, 3)  # id fittizi: verde / rosso / ciano
    snake.render(scr, game, state, note, best, attrs)
    return scr


def draw_terminal(scr, title, path, size=26):
    font, bold_font = load_fonts(size)
    ascent, descent = font.getmetrics()
    cw = max(int(round(font.getlength("M"))), 8)
    ch = ascent + descent
    pad, bar = 16, 40

    img = Image.new("RGB", (scr.w * cw + 2 * pad, bar + scr.h * ch + 2 * pad), BG)
    d = ImageDraw.Draw(img)

    # barra del titolo "finestra terminale"
    d.rectangle([0, 0, img.width - 1, bar - 1], fill=BAR_BG)
    for i, col in enumerate(DOTS):
        x = pad + i * 24
        d.ellipse([x, bar // 2 - 8, x + 16, bar // 2 + 8], fill=col)
    tw = font.getlength(title)
    d.text(((img.width - tw) / 2, bar / 2), title, font=font, fill=TITLE_FG, anchor="mm")

    # griglia di caratteri
    for (r, c), (glyph, attr) in sorted(scr.cells.items()):
        x = pad + c * cw
        y = bar + pad + r * ch
        color = PAIRS.get(attr & 0x03, FG)
        if attr & curses.A_REVERSE:  # video inverso: sfondo colorato, testo scuro
            d.rectangle([x, y, x + cw - 1, y + ch - 1], fill=color)
            fg = BG
        else:
            fg = color
        f = bold_font if (attr & curses.A_BOLD) else font
        d.text((x + 1, y + ch // 2), glyph, font=f, fill=fg, anchor="lm")

    img.save(path)
    print(f"  ok: {path} ({img.width}x{img.height})")


# ------------------------------------------------------------- scenari ---
def game_playing():
    """Serpente a S in un campo 20x60, punteggio 26."""
    g = snake.Game(20, 60)
    g.snake = ([(7, 34)]
               + [(7, c) for c in range(33, 19, -1)]   # fila 7: col 33 -> 20
               + [(r, 20) for r in range(8, 12)]       # colonna 20: riga 8 -> 11
               + [(11, c) for c in range(21, 31)])     # fila 11: col 21 -> 30 (coda)
    g.direction = g.pending = (0, 1)
    g.score = len(g.snake) - 3
    g.food = (15, 42)
    return g


def game_gameover():
    """Testa appoggiata al muro destro, punteggio 18."""
    g = snake.Game(20, 60)
    g.snake = [(9, c) for c in range(59, 38, -1)]
    g.direction = g.pending = (0, 1)
    g.score = len(g.snake) - 3
    g.food = (4, 12)
    return g


def game_won():
    """Campo 10x24 completamente pieno (vittoria)."""
    g = snake.Game(10, 24)
    path = []
    for r in range(g.h):
        cols = range(g.w) if r % 2 == 0 else range(g.w - 1, -1, -1)
        path.extend((r, c) for c in cols)
    g.snake = list(reversed(path))          # testa per prima
    g.score = len(g.snake) - 3
    g.food = None
    return g


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    playing = game_playing()
    jobs = [
        ("screenshot-gioco.png", "playing", playing, "", 34),
        ("screenshot-pausa.png", "paused", playing, "", 34),
        ("screenshot-gameover.png", "gameover", game_gameover(), "", 27),
        ("screenshot-vittoria.png", "won", game_won(), "", 237),
    ]
    print("Genero le screenshot in docs/")
    for name, state, g, note, best in jobs:
        scr = capture(state, g, note, best)
        draw_terminal(scr, "snake.py - terminale", os.path.join(OUT_DIR, name))


if __name__ == "__main__":
    main()
