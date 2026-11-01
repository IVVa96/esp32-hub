# ======================================================================
# pixel_ui.py — пиксельный терминальный интерфейс (DOS / BIOS / Flipper)
#
# Всё рисуется встроенным 8x8 шрифтом framebuf: чёткая пиксельная сетка,
# никаких сглаженных букв. Заголовки масштабируются x2 вручную.
# ======================================================================
import framebuf

from gui.core.ugui import Screen, Widget, ssd
from gui.core.colors import BLACK, WHITE, AMBER, DIM, RED
from config import SCREEN_W, SCREEN_H, STATUS_BAR_H


CW = 8          # ширина символа
CH = 8          # высота символа
MARGIN = 16


# ----------------------------------------------------------------------
# Текст и примитивы
# ----------------------------------------------------------------------
def text(s, x, y, color=WHITE):
    try:
        ssd.text(s, x, y, color)
    except Exception:
        pass


def text_c(s, y, color=WHITE):
    text(s, (SCREEN_W - len(s) * CW) // 2, y, color)


def text_r(s, right, y, color=WHITE):
    text(s, right - len(s) * CW, y, color)


def frame(x, y, w, h, color):
    ssd.hline(x, y, w, color)
    ssd.hline(x, y + h - 1, w, color)
    ssd.vline(x, y, h, color)
    ssd.vline(x + w - 1, y, h, color)


def fill(x, y, w, h, color):
    ssd.fill_rect(x, y, w, h, color)


# Один общий буфер для масштабирования глифов.
_fbuf = bytearray(8)
_fb = framebuf.FrameBuffer(_fbuf, 8, 8, framebuf.MONO_HLSB)


def big(s, x, y, scale, color=WHITE):
    """Пиксельный текст с целым масштабом (2 = заголовок)."""
    cx = x
    for ch in s:
        _fb.fill(0)
        try:
            _fb.text(ch, 0, 0, 1)
        except Exception:
            cx += CW * scale
            continue
        for gy in range(8):
            for gx in range(8):
                if _fb.pixel(gx, gy):
                    ssd.fill_rect(cx + gx * scale, y + gy * scale,
                                  scale, scale, color)
        cx += CW * scale
    return cx - x


def big_c(s, y, scale, color=WHITE):
    big(s, (SCREEN_W - len(s) * CW * scale) // 2, y, scale, color)


def keycap(x, y, label, fg=WHITE, bd=DIM):
    w = len(label) * CW + 8
    frame(x, y, w, 14, bd)
    text(label, x + 4, y + 3, fg)
    return w


def footer(left_key, left_txt, right_key, right_txt):
    y = 286
    w = keycap(MARGIN, y, left_key)
    text(left_txt, MARGIN + w + 6, y + 3, DIM)

    rw = len(right_key) * CW + 8
    rx = SCREEN_W - MARGIN - rw
    text_r(right_txt, rx - 6, y + 3, DIM)
    keycap(rx, y, right_key)


def header(title, subtitle, scale=2):
    """Заголовок: крупный пиксельный текст, янтарная линейка, подпись."""
    big_c(title, 20, scale, WHITE)
    y = 20 + CH * scale + 4
    ssd.hline(MARGIN, y, SCREEN_W - 2 * MARGIN, AMBER)
    ssd.fill_rect(MARGIN - 4, y - 1, 3, 3, AMBER)
    ssd.fill_rect(SCREEN_W - MARGIN + 1, y - 1, 3, 3, AMBER)
    text_c(subtitle, y + 8, DIM)
    return y + 8


def screen_bg():
    fill(0, 0, SCREEN_W, SCREEN_H, BLACK)


# ----------------------------------------------------------------------
# Меню: карточки (лаунчер) или строки (списки)
# ----------------------------------------------------------------------
class PixelMenu(Widget):
    def __init__(self, writer, items, top, row_h, gap=4,
                 x=MARGIN, width=SCREEN_W - 2 * MARGIN,
                 kind='rows', on_select=None, tags=None,
                 descriptions=None, icons=None, start=0, center_labels=False):
        self.items = list(items)
        self.tags = list(tags) if tags else None
        self.descriptions = list(descriptions) if descriptions else None
        self.center_labels = center_labels
        self.icons = list(icons) if icons else None
        self.top = top
        self.row_h = row_h
        self.gap = gap
        self.kind = kind
        self.on_select = on_select
        self.idx = start
        self.ntop = 0
        self.nvis = max(1, (SCREEN_H - top - 40) // (row_h + gap))
        if self.nvis > len(self.items):
            self.nvis = len(self.items)
        height = self.nvis * (row_h + gap)
        super().__init__(writer, top, x, height, width,
                         None, None, False, value=start, active=True)

    # ---- навигация ----
    def do_adj(self, button, val):
        if not self.items:
            return
        if val > 0:
            self.idx = (self.idx - 1) % len(self.items)
        else:
            self.idx = (self.idx + 1) % len(self.items)
        self.show()

    def do_sel(self):
        if self.on_select:
            self.on_select(self.idx)

    def enter(self):
        self.draw = True
        self.show()

    def leave(self):
        self.draw = True
        self.show()

    def value(self, v=None):
        if v is not None:
            self.idx = max(0, min(v, len(self.items) - 1))
            self.show()
        return self.idx

    # ---- рисование ----
    def show(self):
        if self.screen is not Screen.current_screen:
            return
        self.draw = False
        fill(self.col, self.top, self.width, self.height, BLACK)
        if self.idx < self.ntop:
            self.ntop = self.idx
        elif self.idx >= self.ntop + self.nvis:
            self.ntop = self.idx - self.nvis + 1

        for slot in range(self.nvis):
            i = self.ntop + slot
            if i >= len(self.items):
                break
            y = self.top + slot * (self.row_h + self.gap)
            if self.kind == 'cards':
                self._card(i, y)
            else:
                self._row(i, y)

        # индикаторы прокрутки
        if self.ntop > 0:
            text('^', self.col + self.width - 8, self.top - 9, DIM)
        if self.ntop + self.nvis < len(self.items):
            y = self.top + self.nvis * (self.row_h + self.gap) - 2
            text('v', self.col + self.width - 8, y, DIM)

    def _style(self, selected):
        focused = self.has_focus()
        if selected and focused:
            return AMBER, BLACK, WHITE, BLACK
        if selected:
            return BLACK, AMBER, AMBER, DIM
        return BLACK, WHITE, DIM, DIM

    def _card(self, i, y):
        selected = i == self.idx
        bg, fg, bd, sub = self._style(selected)
        x, w, h = self.col, self.width, self.row_h
        fill(x, y, w, h, bg)
        frame(x, y, w, h, bd)

        # иконка 22x22
        icon = self.icons[i] if self.icons and i < len(self.icons) else (
            'web' if i == 0 else 'apps')
        ix, iy = x + 8, y + (h - 22) // 2
        if icon == 'power':
            # ровный круг с вырезом сверху и вертикальной палочкой
            cx, cy, r = ix + 11, iy + 11, 8
            try:
                ssd.ellipse(cx, cy, r, r, fg)
            except Exception:
                for dy in range(-r, r + 1):
                    dx = int((r * r - dy * dy) ** 0.5)
                    ssd.hline(cx - dx, cy + dy, 2, fg)
                    ssd.hline(cx + dx - 1, cy + dy, 2, fg)
            fill(cx - 2, cy - r - 1, 5, 6, bg)
            fill(cx - 1, iy, 2, 10, fg)
        elif icon == 'bt':
            # Классический рунический значок Bluetooth
            ssd.line(ix + 8, iy + 1, ix + 8, iy + 20, fg)
            ssd.line(ix + 8, iy + 1, ix + 12, iy + 6, fg)
            ssd.line(ix + 12, iy + 6, ix + 4, iy + 15, fg)
            ssd.line(ix + 8, iy + 20, ix + 12, iy + 15, fg)
            ssd.line(ix + 12, iy + 15, ix + 4, iy + 6, fg)
        elif icon == 'usb':
            # Ровный симметричный значок USB: стрелка, ствол, две ветви
            ssd.hline(ix + 11, iy + 0, 1, fg)
            ssd.hline(ix + 10, iy + 1, 3, fg)
            ssd.hline(ix + 9, iy + 2, 5, fg)
            ssd.hline(ix + 8, iy + 3, 7, fg)
            ssd.vline(ix + 11, iy + 4, 16, fg)
            ssd.line(ix + 11, iy + 13, ix + 5, iy + 9, fg)
            ssd.line(ix + 11, iy + 13, ix + 17, iy + 9, fg)
            fill(ix + 3, iy + 5, 4, 4, fg)
            fill(ix + 15, iy + 5, 4, 4, fg)
            fill(ix + 10, iy + 19, 3, 3, fg)
        elif icon == 'web':
            # миниатюра плиток приложений (Web UI)
            for bx, by in ((0, 0), (12, 0), (0, 12), (12, 12)):
                frame(ix + bx, iy + by, 10, 10, fg)
                fill(ix + bx + 3, iy + by + 3, 4, 3, fg)
        else:
            # миниатюра списка (Classic UI)
            for n in range(4):
                ry = iy + 1 + n * 5
                fill(ix, ry + 1, 3, 3, fg)
                ssd.hline(ix + 6, ry + 2, 16, fg)

        label = self.items[i].upper()
        has_desc = bool(self.descriptions)
        # Текстовая колонка: заголовок 16 px + зазор 2 px + описание 8 px.
        # Блок центрируется по высоте кнопки, иконка — по центру блока.
        text_h = 26 if has_desc else 16
        ty = y + (h - text_h) // 2
        tw = len(label) * CW * 2
        tx = x + 40
        if tx + tw > x + w - 6:
            tx = max(x + 36, x + w - 6 - tw)
        big(label, tx, ty, 2, fg)
        if has_desc:
            text(self.descriptions[i], tx, ty + 18, sub)

    def _row(self, i, y):
        selected = i == self.idx
        bg, fg, bd, sub = self._style(selected)
        x, w, h = self.col, self.width, self.row_h
        fill(x, y, w, h, bg)
        frame(x, y, w, h, bd)
        ty = y + (h - CH) // 2

        if self.tags:
            tag = self.tags[i].upper()
            text(tag, x + 10, ty, fg)
            text(self.items[i].upper(), x + 10 + len(tag) * CW + 12, ty, fg)
        else:
            text(self.items[i].upper(), x + 10, ty, fg)

        if selected:
            text('>', x + w - 16, ty, fg)


# ----------------------------------------------------------------------
# Кнопка закрытия в стиле терминала: [X] / [X] инвертируется в фокусе
# ----------------------------------------------------------------------
class PixelClose(Widget):
    def __init__(self, writer, row, col, callback, size=16):
        super().__init__(writer, row, col, size, size,
                         None, None, False, value=None, active=True)
        self.callback = callback

    def show(self):
        if self.screen is not Screen.current_screen:
            return
        self.draw = False
        focused = self.has_focus()
        fill(self.col, self.row, self.width, self.height,
             AMBER if focused else BLACK)
        frame(self.col, self.row, self.width, self.height,
              WHITE if focused else DIM)
        text('X', self.col + 4, self.row + 4,
             BLACK if focused else WHITE)

    def enter(self):
        self.draw = True
        self.show()

    def leave(self):
        self.draw = True
        self.show()

    def do_sel(self):
        if self.callback:
            self.callback()
