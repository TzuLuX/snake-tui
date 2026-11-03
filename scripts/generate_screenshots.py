#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera le "screenshot" del gioco per il README.

Il trucco: si fa girare la *vera* funzione `snake.render()` su uno schermo
finto che cattura tutte le chiamate `addstr()`, poi ogni cella viene
ridisegnata in PNG con Pillow dentro una finestra "stile terminale".
Blocchi (█ ▀ ▄ ▟ …) e linee (─ ━ ╭ …) sono disegnati come rettangoli e archi,
esattamente come fanno i terminali moderni (kitty, VTE, Windows Terminal),
invece di affidarsi ai glifi del font.

Uso:
    python3 scripts/generate_screenshots.py

Dipendenza: Pillow (solo per generare le immagini, non serve al gioco).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import curses  # usato solo per le costanti A_BOLD / A_REVERSE / A_COLOR
from PIL import Image, ImageDraw, ImageFont

import snake

# ---------------------------------------------------------------- tema ---
BG = (18, 19, 24)            # sfondo del terminale (colore "default")
FG = (205, 211, 217)         # testo di default
BAR_BG = (38, 43, 51)        # barra del titolo della "finestra"
TITLE_FG = (148, 156, 167)
DOTS = ((255, 95, 87), (254, 188, 46), (40, 200, 64))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs"))

# quadranti: bit 1 = alto-sx, 2 = alto-dx, 4 = basso-sx, 8 = basso-dx
QUADS = {'▘': 1, '▝': 2, '▖': 4, '▗': 8, '▀': 3, '▄': 12, '▌': 5, '▐': 10,
         '▚': 9, '▞': 6, '▙': 13, '▛': 7, '▜': 11, '▟': 14, '█': 15}
# linee dal centro verso i lati (L R U D); ultima cifra: 1 sottile, 2 spessa
LINES = {'─': 'LR1', '━': 'LR2', '│': 'UD1', '┃': 'UD2', '╴': 'L1', '╶': 'R1',
         '╵': 'U1', '╷': 'D1', '╸': 'L2', '╺': 'R2', '╹': 'U2', '╻': 'D2'}
ARCS = {'╭': 'DR', '╮': 'DL', '╯': 'UL', '╰': 'UR'}


def load_fonts(size):
    """Font mono (regolare + grasso) per testo e simboli (• × · …)."""
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


class FakePen:
    """Come snake.make_pen() in un terminale a 256 colori, ma ricorda le
    coppie (fg, bg) per poterle ridisegnare."""

    def __init__(self):
        self.ids = {}          # (fg, bg) -> numero di coppia
        self.colors = {}       # numero di coppia -> (fg, bg)

    def __call__(self, fg, bg, extra=0):
        n = self.ids.setdefault((fg, bg), len(self.ids) + 1)
        self.colors[n] = (fg, bg)
        return (n << 8) | extra            # come curses.color_pair(n)

    def rgb(self, attr):
        fg, bg = self.colors.get((attr & curses.A_COLOR) >> 8, (None, None))
        fg = FG if fg is None else snake.rgb256(fg)
        bg = BG if bg is None else snake.rgb256(bg)
        return (bg, fg) if attr & curses.A_REVERSE else (fg, bg)


def capture(state, game, note="", best=0, glow=(), assists=()):
    """Rende lo stato usando la funzione render() vera del gioco."""
    scr = FakeScreen(game.h + 4, 2 * game.w + 2)
    pen = FakePen()
    snake.render(scr, game, state, note, best, pen, glow, assists)
    return scr, pen


def draw_cell(d, x, y, cw, ch, glyph, fg, font):
    """Disegna un carattere: blocchi e linee a mano, il resto col font."""
    hw, hh = cw // 2, ch // 2
    if glyph in QUADS:
        m = QUADS[glyph]
        for bit, qx, qy in ((1, 0, 0), (2, 1, 0), (4, 0, 1), (8, 1, 1)):
            if m & bit:
                d.rectangle([x + qx * hw, y + qy * hh,
                             x + (cw if qx else hw) - 1, y + (ch if qy else hh) - 1],
                            fill=fg)
    elif glyph in '▏▕':                      # ottavi verticali sx / dx
        t = max(1, cw // 8)
        x0 = x if glyph == '▏' else x + cw - t
        d.rectangle([x0, y, x0 + t - 1, y + ch - 1], fill=fg)
    elif glyph in LINES:
        spec = LINES[glyph]
        t = max(1, round(cw / 9)) * (2 if spec[-1] == '2' else 1)
        cx, cy = x + hw - t // 2, y + hh - t // 2   # angolo alto-sx del tratto
        for side in spec[:-1]:
            box = {'L': [x, cy, cx + t - 1, cy + t - 1],
                   'R': [cx, cy, x + cw - 1, cy + t - 1],
                   'U': [cx, y, cx + t - 1, cy + t - 1],
                   'D': [cx, cy, cx + t - 1, y + ch - 1]}[side]
            d.rectangle(box, fill=fg)
    elif glyph in ARCS:                       # quarto di ellisse tra due lati
        sides = ARCS[glyph]
        t = max(1, round(cw / 9))
        ox = x + cw if 'R' in sides else x
        oy = y + ch if 'D' in sides else y
        start = {'DR': 180, 'DL': 270, 'UL': 0, 'UR': 90}[sides]
        d.arc([ox - hw - t / 2, oy - hh - t / 2, ox + hw + t / 2 - 1, oy + hh + t / 2 - 1],
              start, start + 90, fill=fg, width=t)
    elif glyph != ' ':
        d.text((x + hw, y + font.getmetrics()[0]), glyph, font=font, fill=fg,
               anchor="ms")


def draw_terminal(scr, pen, title, path, size=26):
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
    d.text((img.width / 2, bar / 2), title, font=font, fill=TITLE_FG, anchor="mm")

    # griglia di caratteri: prima tutti gli sfondi, poi i glifi
    for (r, c), (_, attr) in scr.cells.items():
        x, y = pad + c * cw, bar + pad + r * ch
        d.rectangle([x, y, x + cw - 1, y + ch - 1], fill=pen.rgb(attr)[1])
    for (r, c), (glyph, attr) in scr.cells.items():
        f = bold_font if attr & curses.A_BOLD else font
        draw_cell(d, pad + c * cw, bar + pad + r * ch, cw, ch, glyph,
                  pen.rgb(attr)[0], f)

    img.save(path)
    print(f"  ok: {path} ({img.width}x{img.height})")


# ------------------------------------------------------------- scenari ---
def game_playing():
    """Serpente con un tornante (file adiacenti) in un campo 18x30."""
    g = snake.Game(18, 30)
    g.snake = ([(5, c) for c in range(22, 7, -1)]     # fila 5: testa -> col 8
               + [(6, c) for c in range(8, 19)]       # tornante: fila 6 -> col 18
               + [(r, 18) for r in range(7, 12)]      # colonna 18: giù fino a riga 11
               + [(11, c) for c in range(17, 9, -1)])  # fila 11: verso sinistra (coda)
    g.direction = g.pending = snake.RIGHT
    g.score = len(g.snake) - 3
    g.food = (13, 25)
    return g


def game_aiming():
    """Come game_playing, ma col frutto sulla traiettoria (per il mirino)."""
    g = game_playing()
    g.food = (5, 27)
    return g


def game_wrapping():
    """Bordi aperti: il serpente è uscito a destra ed è rientrato da sinistra."""
    g = snake.Game(18, 30)
    g.wrap = True
    g.snake = ([(14, c) for c in range(3, -1, -1)]     # testa a col 3, verso destra
               + [(14, c) for c in range(29, 21, -1)]  # ... rientrato da destra
               + [(r, 22) for r in range(13, 1, -1)]   # colonna 22 verso l'alto
               + [(2, c) for c in range(23, 28)])      # fila 2 (coda)
    g.direction = g.pending = snake.RIGHT
    g.score = len(g.snake) - 3
    g.delay_ms = 160                                   # frenato
    g.food = (14, 9)
    return g


def game_gameover():
    """Testa contro il muro in alto, punteggio 19."""
    g = snake.Game(18, 30)
    g.snake = ([(r, 14) for r in range(0, 8)]
               + [(7, c) for c in range(13, 4, -1)]
               + [(r, 5) for r in range(8, 13)])
    g.direction = g.pending = snake.UP
    g.score = len(g.snake) - 3
    g.food = (12, 22)
    return g


def game_won():
    """Campo 10x20 completamente pieno (vittoria)."""
    g = snake.Game(10, 20)
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
    jobs = [  # file, stato, partita, nota, record, bocconi, aiuti
        ("screenshot-gioco.png", "playing", playing, "", 41, (17,), ()),
        ("screenshot-mirino.png", "playing", game_aiming(), "", 41, (1, 24), {"mirino"}),
        ("screenshot-bordi.png", "playing", game_wrapping(), "", 41, (10,),
         {"mirino", "bordi", "freno"}),
        ("screenshot-pausa.png", "paused", game_playing(), "", 41, (17,), {"bordi", "freno"}),
        ("screenshot-gameover.png", "gameover", game_gameover(), "", 36, (), ()),
        ("screenshot-vittoria.png", "won", game_won(), "", 197, (), ()),
    ]
    print("Genero le screenshot in docs/")
    for name, state, g, note, best, glow, assists in jobs:
        if "bordi" in assists:
            g.wrap = True
        scr, pen = capture(state, g, note, best, glow, assists)
        draw_terminal(scr, pen, "snake.py - terminale", os.path.join(OUT_DIR, name))


if __name__ == "__main__":
    main()
