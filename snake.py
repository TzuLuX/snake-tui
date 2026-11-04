#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Snake in TUI — curses, Python 3 (Linux / macOS / WSL).

Uso:
    python3 snake.py

Controlli:
    frecce o WASD : muovi il serpente
    m             : mirino laser on/off (mostra dove stai andando)
    b             : bordi aperti on/off (si esce da un lato, si rientra dall'altro)
    f             : freno on/off (il tasto opposto alla marcia rallenta;
                    spegnendolo si torna alla velocità normale)
    p             : pausa / riprendi (e stato degli aiuti)
    r             : nuovo gioco (dopo lo scontro)
    q             : esci

Il serpente accelera a ogni frutto mangiato; muri e corpo = game over.
"""

import curses
import math
import random
import time

__version__ = "1.1.1"        # da aggiornare anche nel badge del README

MIN_H, MIN_W = 10, 20        # area di gioco minima (in celle)
START_DELAY_MS = 130         # passo iniziale (ms)
MIN_DELAY_MS = 55            # velocità massima
SPEEDUP_MS = 4               # accelerazione per cibo mangiato
BRAKE_MS = 15                # rallentamento per ogni colpo di freno
MAX_DELAY_MS = 250           # velocità minima (con il freno)

UP, DOWN, LEFT, RIGHT = (-1, 0), (1, 0), (0, -1), (0, 1)
KEYMAP = {
    curses.KEY_UP: UP, ord('w'): UP, ord('W'): UP,
    curses.KEY_DOWN: DOWN, ord('s'): DOWN, ord('S'): DOWN,
    curses.KEY_LEFT: LEFT, ord('a'): LEFT, ord('A'): LEFT,
    curses.KEY_RIGHT: RIGHT, ord('d'): RIGHT, ord('D'): RIGHT,
}
# aiuti per chi inizia: tasto -> (nome, etichetta nel riquadro di pausa)
ASSISTS = {ord('m'): ('mirino', 'mirino laser'),
           ord('b'): ('bordi', 'bordi aperti'),
           ord('f'): ('freno', "freno all'indietro")}


class Game:
    """Logica pura (senza curses): facile da testare in headless."""

    def __init__(self, h, w):
        self.wrap = False            # bordi aperti: si rientra dal lato opposto
        self.reset(h, w)

    def reset(self, h, w):
        self.h, self.w = h, w
        mid = h // 2
        self.snake = [(mid, 5), (mid, 4), (mid, 3)]      # testa per prima
        self.direction = RIGHT
        self.pending = RIGHT
        self.score = 0
        self.delay_ms = START_DELAY_MS
        self.food = self._spawn_food()

    def _spawn_food(self):
        occupied = set(self.snake)
        free = [(r, c) for r in range(self.h) for c in range(self.w)
                if (r, c) not in occupied]
        return random.choice(free) if free else None

    def set_direction(self, d):
        # proibito il giro a U (180°)
        if (d[0], d[1]) != (-self.direction[0], -self.direction[1]):
            self.pending = d

    def brake(self):
        """Rallenta di un passo (il cibo poi riaccelera come sempre)."""
        self.delay_ms = min(MAX_DELAY_MS, self.delay_ms + BRAKE_MS)

    def release_brake(self):
        """Annulla le frenate: torna alla velocità che avrebbe senza freno."""
        self.delay_ms = max(MIN_DELAY_MS, START_DELAY_MS - self.score * SPEEDUP_MS)

    def step(self):
        """Avanza di un tick. Restituisce 'ok', 'ate', 'dead' o 'won'."""
        self.direction = self.pending
        head = self.snake[0]
        nh = (head[0] + self.direction[0], head[1] + self.direction[1])
        if self.wrap:
            nh = (nh[0] % self.h, nh[1] % self.w)
        eating = self.food is not None and nh == self.food
        body = self.snake if eating else self.snake[:-1]
        if not (0 <= nh[0] < self.h and 0 <= nh[1] < self.w) or nh in body:
            return 'dead'
        self.snake = [nh] + body
        if eating:
            self.score += 1
            self.delay_ms = max(MIN_DELAY_MS, self.delay_ms - SPEEDUP_MS)
            self.food = self._spawn_food()
            return 'won' if self.food is None else 'ate'
        return 'ok'


# ------------------------------------------------------------- grafica ---
# Ogni cella del campo è larga 2 colonne: nel terminale un carattere è alto
# circa il doppio di quanto è largo, così le celle risultano quadrate.
# Colori: indici xterm-256 dal 16 in su (fissi, non dipendono dal tema).
ARENA_BG = (234, 235)        # prato a scacchiera
WALL, PORTAL = 239, 238     # muro pieno / bordo aperto (tratteggiato)
HEAD, EYE = 191, 232
BODY = [(46, 40), (40, 34), (34, 28), (28, 22)]
#        (luce, ombra) dalla testa verso la coda
FRUITS = (196, 208, 134)     # mela, arancia, prugna (cambia a ogni frutto)
LEAF = 70
TEXT, DIM, ACCENT, ALERT, PANEL = 252, 244, 113, 203, 236
LASER, LASER_HIT = 52, 131    # mirino: normale / con il frutto sotto tiro
GLOW = [(231, 230), (230, 229), (229, 192), (192, 156), (156, 120)]
#        boccone: (luce, ombra) per ogni tick dopo il pasto; dopo il lampo
#        iniziale resta l'ultimo colore, finché la coda non lo raggiunge

# corpo come tubo illuminato dall'alto a sinistra: fg = luce, bg = ombra
SHADE = {frozenset((LEFT, RIGHT)): '▀▀', frozenset((UP, DOWN)): '█ ',
         frozenset((UP, LEFT)): '▀ '}            # altre curve: '█▀'
# verso la coda il tubo si assottiglia: resta la metà in ombra, poi una linea
TAPER = {frozenset((LEFT, RIGHT)): '▄▄', frozenset((UP, DOWN)): ' █'}
EYES = {'gameover': '×', 'paused': '-'}          # altrimenti '●'

BASIC8 = ((0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
          (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229))


def rgb256(n):
    """Indice xterm-256 (16-255) -> (r, g, b)."""
    if n >= 232:
        v = 8 + 10 * (n - 232)
        return v, v, v
    n -= 16
    return tuple(55 + 40 * x if x else 0 for x in (n // 36, n // 6 % 6, n % 6))


def _to8(n):
    """Colore più vicino tra gli 8 base (terminali senza 256 colori)."""
    if n is None or n < 8:
        return n
    rgb = rgb256(n)
    return min(range(8), key=lambda i: sum((a - b) ** 2
                                           for a, b in zip(BASIC8[i], rgb)))


def make_pen():
    """pen(fg, bg, extra) -> attributo curses (None = colore di default).

    Le coppie colore vengono allocate al primo uso. Con meno di 256 colori si
    approssima agli 8 base; senza colori si ripiega sul video inverso.
    """
    if not curses.has_colors():
        return lambda fg, bg, extra=0: extra | (
            curses.A_REVERSE if bg not in (None,) + ARENA_BG else 0)
    curses.start_color()
    try:
        curses.use_default_colors()
        dfg = dbg = -1
    except curses.error:
        dfg, dbg = curses.COLOR_WHITE, curses.COLOR_BLACK
    rich = curses.COLORS >= 256
    limit = min(curses.COLOR_PAIRS, 256)
    pairs = {}

    def pen(fg, bg, extra=0):
        key = (fg, bg) if rich else (_to8(fg), _to8(bg))
        if key not in pairs:
            n = len(pairs) + 1
            if n >= limit:
                return extra
            curses.init_pair(n, dfg if key[0] is None else key[0],
                             dbg if key[1] is None else key[1])
            pairs[key] = curses.color_pair(n)
        return pairs[key] | extra

    return pen


def fits(h_term, w_term):
    ph = h_term - 4           # intestazione + muri + piè di pagina
    pw = (w_term - 2) // 2    # muri laterali, celle da 2 colonne
    return ph >= MIN_H and pw >= MIN_W, ph, pw


def snake_cells(snake, state, glow=()):
    """(riga, colonna, 2 glifi, fg, bg) per ogni segmento del serpente.

    glow: indici dei segmenti "boccone". Il segmento nato da un pasto ha
    indice pari ai tick trascorsi (a ogni passo nasce una nuova testa), quindi
    l'indice è anche l'età del boccone e sceglie il colore in GLOW.
    """
    n = len(snake)
    for i, (r, c) in enumerate(snake):
        def toward(j):
            # un vicino oltre il bordo (bordi aperti) dista ±(lato-1): vale ∓1
            return tuple(d if abs(d) <= 1 else (1 if d < 0 else -1)
                         for d in (snake[j][0] - r, snake[j][1] - c))
        grass = ARENA_BG[(r + c) % 2]
        if i == 0:                                # testa: occhi in avanti
            eye = EYES.get(state, '●')
            glyphs = {LEFT: ' ' + eye, RIGHT: eye + ' '}.get(toward(1), eye * 2)
            yield r, c, glyphs, EYE, GLOW[0][0] if 0 in glow else HEAD
            continue
        if i in glow:
            light, dark = GLOW[min(i, len(GLOW) - 1)]
        else:
            light, dark = BODY[i * len(BODY) // n]
        if i == n - 1:                            # punta della coda
            tip = '━━' if toward(i - 1)[0] == 0 else '▕▏'
            yield r, c, tip, light, grass
            continue
        bend = frozenset((toward(i - 1), toward(i + 1)))
        if i == n - 2 and bend in TAPER:
            yield r, c, TAPER[bend], dark, grass
        else:
            yield r, c, SHADE.get(bend, '█▀'), light, dark


_bg = {}


def background(game, pen):
    """Finestra con muri (tratteggiati se i bordi sono aperti) e prato.

    Si ridisegna solo quando cambiano le dimensioni del campo, i bordi o pen.
    """
    ph, pw = game.h, game.w
    key = (ph, pw, game.wrap, pen)
    if _bg.get('key') != key:
        right = 2 * pw + 1
        win = curses.newwin(ph + 2, right + 1, 1, 0)

        def put(r, c, s, attr):
            try:          # l'angolo in basso a destra solleva sempre errore
                win.addstr(r, c, s, attr)
            except curses.error:
                pass

        wall = pen(PORTAL if game.wrap else WALL, None)
        top, bottom, side = ('▄ ', '▀ ', '█ ') if game.wrap else ('▄', '▀', '█')
        put(0, 0, (top * (right + 1))[:right + 1], wall)
        for r in range(ph):
            put(1 + r, 0, side[r % len(side)], wall)
            put(1 + r, right, side[r % len(side)], wall)
            # spazio o spazio non separabile (identici a video) scrivono in
            # binario l'indice di riga: senza, le righe di solo prato sono
            # uguali a due a due e ncurses, quando la coda ne libera una, crede
            # che il campo sia scorso e lo ridipinge tutto (sfarfallio quando
            # il serpente scende)
            for c in range(pw):
                blank = ''.join('\u00a0' if r >> (2 * c + k) & 1 else ' '
                                for k in range(2))
                put(1 + r, 1 + 2 * c, blank, pen(None, ARENA_BG[(r + c) % 2]))
        put(1 + ph, 0, (bottom * (right + 1))[:right + 1], wall)
        _bg.update(key=key, win=win)
    return _bg['win']


def render(stdscr, game, state, note, best, pen, glow=(), assists=()):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    ph, pw = game.h, game.w
    right = 2 * pw + 1                            # colonna del muro destro

    def put(r, c, s, attr=0):
        if 0 <= r < h and 0 <= c < w:
            try:
                stdscr.addstr(r, c, s[:max(0, w - c)], attr)
            except curses.error:
                pass

    def cell(r, c, glyphs, fg, bg, extra=0):
        put(2 + r, 1 + 2 * c, glyphs, pen(fg, bg, extra))

    # intestazione
    put(0, 0, " SNAKE ", pen(16, ACCENT, curses.A_BOLD))
    # tachimetro: 8 tacche, dalla velocità minima (freno) alla massima
    level = round(8 * (MAX_DELAY_MS - game.delay_ms) / (MAX_DELAY_MS - MIN_DELAY_MS))
    for i, bar in enumerate('▁▂▃▄▅▆▇█'):
        put(0, 8 + i, bar, pen(ACCENT if i < max(1, level) else PANEL, None))
    stats = f"punti {game.score}  ·  record {best} "
    flash = min(glow, default=len(GLOW)) < len(GLOW) - 1   # pasto appena fatto
    put(0, max(17, right + 1 - len(stats)), stats,
        pen(HEAD, None, curses.A_BOLD) if flash else pen(TEXT, None))

    # muri e prato: finestra pre-disegnata, copiata in C a ogni frame
    background(game, pen).overwrite(stdscr)

    # mirino laser: dalla testa fino al muro (o tutto il giro, a bordi aperti)
    if 'mirino' in assists and state in ('playing', 'paused'):
        dr, dc = game.pending
        r, c = game.snake[0]
        ray = []
        for _ in range((pw if dr == 0 else ph) - 1):
            r, c = r + dr, c + dc
            if game.wrap:
                r, c = r % ph, c % pw
            elif not (0 <= r < ph and 0 <= c < pw):
                break
            ray.append((r, c))
        beam = LASER_HIT if game.food in ray else LASER
        for r, c in ray:
            cell(r, c, '━━' if dr == 0 else '▕▏', beam, ARENA_BG[(r + c) % 2])

    # frutto: polpa a cupola + foglia verde in alto a destra
    if game.food:
        fr, fc = game.food
        fruit = FRUITS[game.score % len(FRUITS)]
        put(2 + fr, 1 + 2 * fc, '▟', pen(fruit, ARENA_BG[(fr + fc) % 2]))
        put(2 + fr, 2 + 2 * fc, '▙', pen(fruit, LEAF))

    for r, c, glyphs, fg, bg in snake_cells(game.snake, state, glow):
        cell(r, c, glyphs, fg, bg, curses.A_BOLD if fg == EYE else 0)

    def panel(lines):
        """Riquadro centrato sul campo; lines = [(testo, fg, attr)]."""
        inner = max(len(t) for t, _, _ in lines) + 4
        top = 2 + max(0, (ph - len(lines) - 2) // 2)
        left = 1 + max(0, (2 * pw - inner - 2) // 2)
        frame = pen(DIM, PANEL)
        put(top, left, '╭' + '─' * inner + '╮', frame)
        for i, (text, fg, attr) in enumerate(lines, 1):
            put(top + i, left, '│', frame)
            put(top + i, left + 1, text.center(inner), pen(fg, PANEL, attr))
            put(top + i, left + inner + 1, '│', frame)
        put(top + len(lines) + 1, left, '╰' + '─' * inner + '╯', frame)

    bold = curses.A_BOLD
    if state == 'paused':
        rows = [(f"{chr(k)}  {label:<18} {'on' if name in assists else 'off':>3}",
                 ACCENT if name in assists else DIM, 0)
                for k, (name, label) in ASSISTS.items()]
        panel([("PAUSA", ACCENT, bold), ("", TEXT, 0)] + rows
              + [("", TEXT, 0), ("p riprendi · q esci", DIM, 0)])
    elif state == 'gameover':
        panel([("GAME OVER", ALERT, bold), (f"punteggio {game.score}", TEXT, 0),
               ("", TEXT, 0), ("r riprova · q esci", DIM, 0)])
    elif state == 'won':
        panel([("VITTORIA!", HEAD, bold), ("campo pieno", TEXT, 0),
               (f"punteggio {game.score}", TEXT, 0), ("", TEXT, 0),
               ("r ancora · q esci", DIM, 0)])
    # piè di pagina: note o richiamo comandi (in partita), versione a destra
    footer = ''
    if state == 'playing':
        footer = "WASD/frecce · m mirino · b bordi · f freno · p pausa · q esci"
        if len(footer) > 2 * pw:
            footer = "WASD/frecce · p pausa e aiuti · q esci"
        footer = note or footer
    put(3 + ph, 1, footer, pen(DIM, None))
    version = f"v{__version__}"
    if len(footer) + len(version) + 2 <= 2 * pw:        # solo se non si tocca
        put(3 + ph, right - len(version), version, pen(DIM, None))

    stdscr.refresh()


def main(stdscr):
    try:
        curses.curs_set(0)
    except curses.error:      # terminali che non sanno nascondere il cursore
        pass
    pen = make_pen()
    state = 'playing'
    note = ''
    game = None
    best = 0
    assists = set()          # aiuti attivi: 'mirino', 'bordi', 'freno'
    glow = []                # età dei bocconi in viaggio (vedi snake_cells)
    next_tick = 0.0          # istante (time.monotonic) del prossimo passo

    def later():
        return time.monotonic() + game.delay_ms / 1000

    while True:
        h, w = stdscr.getmaxyx()
        ok, ph, pw = fits(h, w)
        if not ok:
            stdscr.erase()
            msg = (f"Terminale troppo piccolo: serve almeno "
                   f"{MIN_H + 4}x{2 * MIN_W + 2}. q = esci")
            try:
                stdscr.addstr(0, 1, msg[:max(0, w - 2)])
            except curses.error:
                pass
            stdscr.refresh()
            if stdscr.getch() in (ord('q'), ord('Q')):
                return
            continue

        resized = game is not None and (game.h, game.w) != (ph, pw)
        if game is None or resized:
            game = Game(ph, pw)
            state = 'playing'
            glow = []
            next_tick = later()
            note = "dimensioni cambiate — nuovo gioco" if resized else ''
            game.wrap = 'bordi' in assists

        # attesa fino al prossimo passo: i tasti che non muovono il serpente
        # (aiuti, freno) non fanno ripartire il conto alla rovescia
        if state == 'playing':
            stdscr.timeout(max(0, math.ceil((next_tick - time.monotonic()) * 1000)))
        else:
            stdscr.timeout(50)
        key = stdscr.getch()

        if key in (ord('q'), ord('Q')):
            return
        toggle = ASSISTS.get(ord(chr(key).lower())) if 0 < key < 128 else None
        if toggle:
            assists ^= {toggle[0]}
            game.wrap = 'bordi' in assists
            if toggle[0] == 'freno' and 'freno' not in assists:
                game.release_brake()             # freno spento: velocità normale

        if state == 'playing':
            stepped = False
            if key in KEYMAP:
                d = KEYMAP[key]
                if 'freno' in assists and d == (-game.direction[0], -game.direction[1]):
                    game.brake()                 # indietro = frena
                else:
                    game.set_direction(d)
                    stepped = True
            elif key in (ord('p'), ord('P')):
                state = 'paused'
            if state == 'playing' and time.monotonic() >= next_tick:
                stepped = True                   # è scaduto il tick
            if stepped:
                result = game.step()
                next_tick = later()
                if result != 'dead':   # nuova testa: i bocconi scivolano verso la coda
                    glow = [a + 1 for a in glow if a + 1 < len(game.snake)]
                    if result in ('ate', 'won'):
                        glow.append(0)
                if result == 'dead':
                    state = 'gameover'
                    best = max(best, game.score)
                elif result == 'won':
                    state = 'won'
                    best = max(best, game.score)
        elif state == 'paused' and key in (ord('p'), ord('P')):
            state = 'playing'
            next_tick = later()
        elif state in ('gameover', 'won') and key in (ord('r'), ord('R')):
            game.reset(ph, pw)
            state = 'playing'
            glow = []
            next_tick = later()

        render(stdscr, game, state, note, best, pen, glow, assists)

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
