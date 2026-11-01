# ======================================================================
# keyboard_widget.py — экранная клавиатура для ввода текста
# ======================================================================
from gui.widgets import Button
from gui.core.ugui import ssd
from gui.core.colors import *
from config import (
    KEY_BG, KEY_FG, KEY_BORDER, HIGHLIGHT_BG, HIGHLIGHT_FG,
    _sy,
)
import asyncio
import hardware_setup


DEFAULT_LAYOUT = [
    ([('1',1),('2',1),('3',1),('4',1),('5',1),('6',1),('7',1),('8',1),('9',1),('0',1)], _sy(26)),
    ([('q',1),('w',1),('e',1),('r',1),('t',1),('y',1),('u',1),('i',1),('o',1),('p',1)], _sy(26)),
    ([('a',1),('s',1),('d',1),('f',1),('g',1),('h',1),('j',1),('k',1),('l',1),('-',1)], _sy(26)),
    ([('CL',1.5),('z',1),('x',1),('c',1),('v',1),('b',1),('n',1),('m',1),('Bs',1.5)], _sy(30)),
    ([('Sh',2),('.',1),('_',1),('@',1),('!',1),('#',1),('$',1),('%',1),('&',1)], _sy(30)),
    ([('Sp',6),('OK',2),('Cancel',2)], _sy(32)),
]

ROW_SAVED = len(DEFAULT_LAYOUT)

ROW_GAP   = _sy(2)
SAVED_GAP = _sy(4)
SAVED_H   = _sy(34)

POLL_MS = 30


class _HiddenHost(Button):
    def show(self):
        pass

    def do_adj(self, *_a, **_k):
        pass


class Keyboard:
    def __init__(self, writer, row, col,
                 layout=None, cell_w=22, cell_h=None, callback=None,
                 show_saved=True):
        if layout is None:
            layout = DEFAULT_LAYOUT
        self._cell_w = cell_w
        self.row = row
        self.col = col
        self._buf = ''
        self._shift = False
        self._capslock = False
        self._cursor_r = 0
        self._cursor_c = 0
        self._callback = callback
        self._wri = writer

        self._rows_px = []
        y = row
        for keys, row_h in layout:
            if cell_h is not None:
                row_h = cell_h
            row_px = []
            x = col
            for label, w_mult in keys:
                w = int(cell_w * w_mult)
                row_px.append((label, x, y, w, row_h))
                x += w
            self._rows_px.append(row_px)
            y += row_h + ROW_GAP

        if show_saved:
            self._saved_row_idx = len(layout)
            self._saved_x = col
            self._saved_y = y + SAVED_GAP - ROW_GAP
            self._saved_w = 10 * cell_w
            self._saved_h = SAVED_H
            self._n_rows = len(layout) + 1
            self.height = self._saved_y + self._saved_h - row
        else:
            self._saved_row_idx = None
            self._saved_x = 0
            self._saved_y = 0
            self._saved_w = 0
            self._saved_h = 0
            self._n_rows = len(layout)
            self.height = y - row

        self.width = 10 * cell_w

        def _noop(*_a, **_k):
            pass
        try:
            self._host = _HiddenHost(
                writer, 200, 200, text=' ', callback=_noop,
                width=1, height=1,
            )
        except Exception as e:
            print("Keyboard: host EXC:", e)
            self._host = None

        self._btn = {
            'inc': hardware_setup.increase,
            'dec': hardware_setup.decrease,
            'nxt': hardware_setup.nxt,
            'prv': hardware_setup.prev,
            'sel': hardware_setup.sel,
        }
        self._last = {k: 1 for k in self._btn}
        self._running = False
        self._task = None

        self.show()

    def start_poll(self):
        self.stop_poll()
        self._running = True
        self._task = asyncio.create_task(self._poll())

    def stop_poll(self):
        self._running = False
        t = self._task
        self._task = None
        if t is not None and not t.done():
            try:
                t.cancel()
            except Exception:
                pass

    async def _poll(self):
        try:
            for name, p in self._btn.items():
                try:
                    self._last[name] = p.value()
                except Exception:
                    self._last[name] = 1
            await asyncio.sleep_ms(POLL_MS)

            while self._running:
                for name, p in self._btn.items():
                    if not self._running:
                        return
                    try:
                        v = p.value()
                    except Exception:
                        v = 1
                    if v == 0 and self._last[name] == 1:
                        try:
                            self._on_press(name)
                        except Exception as e:
                            print("Keyboard press EXC:", e)
                    self._last[name] = v
                await asyncio.sleep_ms(POLL_MS)
        except asyncio.CancelledError:
            pass

    def _on_press(self, name):
        if   name == 'inc': self.do_prev()
        elif name == 'dec': self.do_next()
        elif name == 'nxt': self.do_increase()
        elif name == 'prv': self.do_decrease()
        elif name == 'sel': self.do_sel()

    @property
    def text(self): return self._buf
    @text.setter
    def text(self, v): self._buf = v or ''

    @property
    def shift(self): return self._shift
    @shift.setter
    def shift(self, v): self._shift = bool(v)

    @property
    def capslock(self): return self._capslock
    @capslock.setter
    def capslock(self, v): self._capslock = bool(v)

    @property
    def cursor_r(self): return self._cursor_r
    @cursor_r.setter
    def cursor_r(self, v): self._cursor_r = v

    @property
    def cursor_c(self): return self._cursor_c
    @cursor_c.setter
    def cursor_c(self, v): self._cursor_c = v

    def enter(self):
        if self._host is not None:
            try:
                self._host.enter()
            except Exception:
                pass
        self.start_poll()

    def value(self, v=None):
        if v is None:
            return self._buf
        self._buf = v or ''
        self.show()

    def _display_label(self, key):
        if key == 'Sh': return 'SH' if self._shift else 'Sh'
        if key == 'CL': return 'CL*' if self._capslock else 'CL'
        if key == 'Sp': return 'SPACE'
        if key == 'Bs': return 'Bs'
        if key == 'OK': return 'OK'
        if key == 'Cancel': return 'X'
        if len(key) == 1 and key.isalpha():
            return key.upper() if (self._capslock ^ self._shift) else key.lower()
        return key

    def show(self):
        for r, row_px in enumerate(self._rows_px):
            for c, (label, x, y, w, h) in enumerate(row_px):
                focused = (r == self._cursor_r and c == self._cursor_c)
                self._draw_key(label, x, y, w, h, focused)
        if self._saved_row_idx is not None:
            self._draw_saved_row(self._cursor_r == self._saved_row_idx)

    def _draw_key(self, label, x, y, w, h, focused):
        bg = HIGHLIGHT_BG if focused else KEY_BG
        fg = HIGHLIGHT_FG if focused else KEY_FG
        try:
            ssd.fill_rect(x, y, w - 1, h - 1, bg)
            ssd.rect(x, y, w - 1, h - 1, KEY_BORDER)
        except Exception:
            pass
        if label == 'CL' and self._capslock and not focused:
            fg = YELLOW
        disp = self._display_label(label)
        tw = len(disp) * 8
        tx = x + max(0, (w - tw) // 2)
        ty = y + max(0, (h - 8) // 2)
        try:
            ssd.text(disp, tx, ty, fg)
        except Exception:
            pass

    def _draw_saved_row(self, focused):
        x = self._saved_x
        y = self._saved_y
        w = self._saved_w
        h = self._saved_h
        bg = HIGHLIGHT_BG if focused else KEY_BG
        fg = HIGHLIGHT_FG if focused else KEY_FG
        try:
            ssd.fill_rect(x, y, w - 1, h - 1, bg)
            ssd.rect(x, y, w - 1, h - 1, KEY_BORDER)
        except Exception:
            pass
        text = 'Use saved password'
        tw = len(text) * 8
        tx = x + max(0, (w - tw) // 2)
        ty = y + max(0, (h - 8) // 2)
        try:
            ssd.text(text, tx, ty, fg)
        except Exception:
            pass

    def _max_c(self, r):
        if self._saved_row_idx is not None and r == self._saved_row_idx:
            return 0
        return len(self._rows_px[r]) - 1

    def _clamp_cursor(self):
        if self._cursor_c > self._max_c(self._cursor_r):
            self._cursor_c = self._max_c(self._cursor_r)
        if self._cursor_c < 0:
            self._cursor_c = 0

    def do_next(self):
        if self._saved_row_idx is not None:
            if self._cursor_r < self._saved_row_idx:
                self._cursor_r += 1
        else:
            if self._cursor_r < len(self._rows_px) - 1:
                self._cursor_r += 1
        self._clamp_cursor()
        self.show()

    def do_prev(self):
        if self._cursor_r > 0:
            self._cursor_r -= 1
        self._clamp_cursor()
        self.show()

    def do_increase(self):
        if self._cursor_c < self._max_c(self._cursor_r):
            self._cursor_c += 1
        else:
            self._cursor_c = 0
        self.show()

    def do_decrease(self):
        if self._cursor_c > 0:
            self._cursor_c -= 1
        else:
            self._cursor_c = self._max_c(self._cursor_r)
        self.show()

    def do_sel(self):
        if self._saved_row_idx is not None and \
                self._cursor_r == self._saved_row_idx:
            if self._callback:
                self._callback('SAVED', self._buf)
            return
        row_px = self._rows_px[self._cursor_r]
        if self._cursor_c >= len(row_px):
            return
        self._press(row_px[self._cursor_c][0])

    def _press(self, key):
        if key == 'CL':
            self._capslock = not self._capslock
        elif key == 'Sh':
            self._shift = not self._shift
        elif key == 'Sp':
            self._buf += ' '
        elif key == 'Bs':
            self._buf = self._buf[:-1]
        elif key == 'OK':
            if self._callback:
                self._callback('OK', self._buf)
            return
        elif key == 'Cancel':
            if self._callback:
                self._callback('CANCEL', self._buf)
            return
        else:
            ch = key
            if len(ch) == 1 and ch.isalpha():
                if self._capslock ^ self._shift:
                    ch = ch.upper()
                else:
                    ch = ch.lower()
                self._shift = False
            self._buf += ch

        if self._callback:
            self._callback('CHANGED', self._buf)
        self.show()