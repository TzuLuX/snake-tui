#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Snake in TUI — curses, Python 3 (Linux / macOS / WSL).

Uso:
    python3 snake.py

Controlli:
    frecce o WASD : muovi il serpente
    p             : pausa / riprendi
    r             : nuovo gioco (dopo lo scontro)
    q             : esci

Il serpente accelera a ogni cibo mangiato; muri e corpo = game over.
"""

import curses
import random

MIN_H, MIN_W = 10, 24        # area di gioco minima
START_DELAY_MS = 130         # passo iniziale (ms)
MIN_DELAY_MS = 55            # velocità massima
SPEEDUP_MS = 4               # accelerazione per cibo mangiato

KEYMAP = {
    curses.KEY_UP: (-1, 0), ord('w'): (-1, 0), ord('W'): (-1, 0),
    curses.KEY_DOWN: (1, 0), ord('s'): (1, 0), ord('S'): (1, 0),
    curses.KEY_LEFT: (0, -1), ord('a'): (0, -1), ord('A'): (0, -1),
    curses.KEY_RIGHT: (0, 1), ord('d'): (0, 1), ord('D'): (0, 1),
}


class Game:
    """Logica pura (senza curses): facile da testare in headless."""

    def __init__(self, h, w):
        self.reset(h, w)

    def reset(self, h, w):
        self.h, self.w = h, w
        mid = h // 2
        self.snake = [(mid, 5), (mid, 4), (mid, 3)]      # testa per prima
        self.direction = (0, 1)
        self.pending = (0, 1)
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

    def step(self):
        """Avanza di un tick. Restituisce 'ok', 'ate', 'dead' o 'won'."""
        self.direction = self.pending
        head = self.snake[0]
        nh = (head[0] + self.direction[0], head[1] + self.direction[1])
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


def make_attrs():
    """Attributi colore (con fallback se il terminale non ha colori)."""
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        curses.init_pair(1, curses.COLOR_GREEN, bg)
        curses.init_pair(2, curses.COLOR_RED, bg)
        curses.init_pair(3, curses.COLOR_CYAN, bg)
        return (curses.color_pair(1) | curses.A_BOLD,
                curses.color_pair(2),
                curses.color_pair(3))
    return curses.A_BOLD, 0, 0


def fits(h_term, w_term):
    ph = h_term - 4   # intestazione + bordi + piè di pagina
    pw = w_term - 2
    return ph >= MIN_H and pw >= MIN_W, ph, pw


def _center(stdscr, game, lines, attr):
    ph, pw = game.h, game.w
    y0 = 2 + max(0, (ph - len(lines)) // 2)
    for i, line in enumerate(lines):
        x = 1 + max(0, (pw - len(line)) // 2)
        try:
            stdscr.addstr(y0 + i, x, line, attr | curses.A_REVERSE)
        except curses.error:
            pass


def render(stdscr, game, state, note, best, attrs):
    a_snake, a_food, a_ui = attrs
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    ph, pw = game.h, game.w

    def put(r, c, s, attr=0):
        if 0 <= r < h and 0 <= c < w:
            try:
                stdscr.addstr(r, c, s[:max(0, w - c)], attr)
            except curses.error:
                pass

    # intestazione
    put(0, 1, " SNAKE ", a_ui | curses.A_REVERSE)
    put(0, 9, f"punti: {game.score}   record: {best}", a_ui)

    # bordo del campo
    put(1, 0, '┌' + '─' * pw + '┐', a_ui)
    mid_row = '│' + ' ' * pw + '│'
    for r in range(ph):
        put(2 + r, 0, mid_row, a_ui)
    put(2 + ph, 0, '└' + '─' * pw + '┘', a_ui)

    # cibo e serpente
    if game.food:
        fr, fc = game.food
        put(2 + fr, 1 + fc, '★', a_food | curses.A_BOLD)
    for i, (r, c) in enumerate(game.snake):
        attr = a_snake | (curses.A_BOLD if i == 0 else 0)
        put(2 + r, 1 + c, '█', attr)

    # stati speciali / note
    if state == 'paused':
        _center(stdscr, game, ["PAUSA", "p = riprendi   q = esci"], a_ui)
    elif state == 'gameover':
        _center(stdscr, game,
                ["GAME OVER", f"punteggio: {game.score}",
                 "r = riprova   q = esci"], a_food)
    elif state == 'won':
        _center(stdscr, game,
                ["VITTORIA! Campo pieno.", f"punteggio: {game.score}",
                 "r = ancora   q = esci"], a_snake)
    else:  # riga di piè di pagina: note o richiamo comandi
        hint = "frecce/WASD muovi · p pausa · q esci"
        put(2 + ph + 1, 1, note if note else hint, a_ui)

    stdscr.refresh()


def main(stdscr):
    curses.curs_set(0)
    attrs = make_attrs()
    state = 'playing'
    note = ''
    game = None
    best = 0

    while True:
        h, w = stdscr.getmaxyx()
        ok, ph, pw = fits(h, w)
        if not ok:
            stdscr.erase()
            msg = (f"Terminale troppo piccolo: serve almeno "
                   f"{MIN_H + 4}x{MIN_W + 2}. q = esci")
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
            note = "dimensioni cambiate — nuovo gioco" if resized else ''

        stdscr.timeout(game.delay_ms if state == 'playing' else 50)
        key = stdscr.getch()

        if key in (ord('q'), ord('Q')):
            return

        if state == 'playing':
            stepped = False
            if key in KEYMAP:
                game.set_direction(KEYMAP[key])
                stepped = True
            elif key in (ord('p'), ord('P')):
                state = 'paused'
            elif key == -1:                      # timeout: un tick
                stepped = True
            if stepped:
                result = game.step()
                if result == 'dead':
                    state = 'gameover'
                    best = max(best, game.score)
                elif result == 'won':
                    state = 'won'
                    best = max(best, game.score)
        elif state == 'paused' and key in (ord('p'), ord('P')):
            state = 'playing'
        elif state in ('gameover', 'won') and key in (ord('r'), ord('R')):
            game.reset(ph, pw)
            state = 'playing'

        render(stdscr, game, state, note, best, attrs)


if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
