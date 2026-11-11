# ======================================================================
# clock.py — полноэкранные часы с плагинными циферблатами
# ======================================================================
import hardware_setup
import asyncio
import gc
import framebuf

from gui.core.ugui import ssd, Screen
from gui.widgets import Button
from gui.core.colors import *

from config import (
    STATUS_BAR_ENABLED, STATUS_BAR_H,
    FULLSCREEN,
)
from apps.user.clock.config import CLOCK_DEFAULT_STYLE
import core.time_sync as time_sync
import core.status_bar as status_bar
from core.ui import make_writer, wait_release_all, redraw_status_bar, return_to
from core.logger import error, info, verbose

from apps.user.clock.utils import registry


_glyph_cache = {}
_glyph_buf   = None


def _get_glyph(ch):
    m = _glyph_cache.get(ch)
    if m is not None:
        return m
    global _glyph_buf
    if _glyph_buf is None:
        _glyph_buf = bytearray(8 * 8 * 2)
    fb = framebuf.FrameBuffer(_glyph_buf, 8, 8, framebuf.RGB565)
    fb.fill(0)
    fb.text(ch, 0, 0, 0xFFFF)
    mask = bytearray(8)
    for py in range(8):
        b = 0
        base = py * 16
        for px in range(8):
            idx = base + px * 2
            if _glyph_buf[idx] or _glyph_buf[idx + 1]:
                b |= (1 << (7 - px))
        mask[py] = b
    _glyph_cache[ch] = mask
    return mask


class _RotSSD:
    def __init__(self, ssd, rotation):
        self._ssd = ssd
        self._rot = rotation % 360
        # База — горизонтальный экран 320x240. При повороте на 90/270
        # виртуальный холст становится портретным 240x320.
        if self._rot in (90, 270):
            self.width  = ssd.height
            self.height = ssd.width
        else:
            self.width  = ssd.width
            self.height = ssd.height

    def _point(self, x, y):
        r = self._rot
        pw, ph = self._ssd.width, self._ssd.height
        if r == 90:  return y, ph - 1 - x
        if r == 180: return pw - 1 - x, ph - 1 - y
        if r == 270: return pw - 1 - y, x
        return x, y

    def _rect(self, x, y, w, h):
        r = self._rot
        pw, ph = self._ssd.width, self._ssd.height
        if r == 90:  return y, ph - x - w, h, w
        if r == 180: return pw - x - w, ph - y - h, w, h
        if r == 270: return pw - y - h, x, h, w
        return x, y, w, h

    def fill(self, c):
        self._ssd.fill(c)

    def pixel(self, x, y, c):
        px, py = self._point(x, y)
        self._ssd.pixel(px, py, c)

    def line(self, x0, y0, x1, y1, c):
        a = self._point(x0, y0)
        b = self._point(x1, y1)
        self._ssd.line(a[0], a[1], b[0], b[1], c)

    def hline(self, x, y, w, c):
        if self._rot == 0:
            self._ssd.hline(x, y, w, c)
            return
        rx, ry, rw, rh = self._rect(x, y, w, 1)
        self._ssd.fill_rect(rx, ry, rw, rh, c)

    def vline(self, x, y, h, c):
        if self._rot == 0:
            self._ssd.vline(x, y, h, c)
            return
        rx, ry, rw, rh = self._rect(x, y, 1, h)
        self._ssd.fill_rect(rx, ry, rw, rh, c)

    def rect(self, x, y, w, h, c):
        rx, ry, rw, rh = self._rect(x, y, w, h)
        self._ssd.rect(rx, ry, rw, rh, c)

    def fill_rect(self, x, y, w, h, c):
        rx, ry, rw, rh = self._rect(x, y, w, h)
        self._ssd.fill_rect(rx, ry, rw, rh, c)

    def circle(self, cx, cy, r, c):
        px, py = self._point(cx, cy)
        self._ssd.circle(px, py, r, c)

    def fill_circle(self, cx, cy, r, c):
        px, py = self._point(cx, cy)
        self._ssd.fill_circle(px, py, r, c)

    def ellipse(self, cx, cy, xr, yr, c):
        px, py = self._point(cx, cy)
        if self._rot in (90, 270):
            xr, yr = yr, xr
        self._ssd.ellipse(px, py, xr, yr, c)

    def fill_ellipse(self, cx, cy, xr, yr, c):
        px, py = self._point(cx, cy)
        if self._rot in (90, 270):
            xr, yr = yr, xr
        self._ssd.fill_ellipse(px, py, xr, yr, c)

    def text(self, s, x, y, c):
        if self._rot == 0:
            self._ssd.text(s, x, y, c)
            return
        for i, ch in enumerate(s):
            mask = _get_glyph(ch)
            vx = x + i * 8
            for py in range(8):
                row = mask[py]
                if row == 0:
                    continue
                for px in range(8):
                    if row & (1 << (7 - px)):
                        self.pixel(vx + px, y + py, c)


class _Host(Button):
    def show(self):
        pass
    def do_adj(self, *_a, **_k):
        pass


class ClockScreen(Screen):
    return_screen = None
    _style    = CLOCK_DEFAULT_STYLE
    _rotation = 0

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        self.wri = make_writer()
        self._alive = True
        self._poll_task = None
        self._clock_task = None
        self._last_draw = None
        self._top = 0
        self._hide_sb = FULLSCREEN and STATUS_BAR_ENABLED
        self._rot_cache = None

        def _noop(*_a, **_k):
            pass
        try:
            self._host = _Host(
                self.wri, 200, 200, text=' ',
                callback=_noop, width=1, height=1,
            )
        except Exception as e:
            error("host:", e)
            self._host = None

    def _target(self):
        r = ClockScreen._rotation
        if r == 0:
            return ssd
        if self._rot_cache is None or self._rot_cache[0] != r:
            self._rot_cache = (r, _RotSSD(ssd, r))
        return self._rot_cache[1]

    def _get_time(self):
        try:
            return time_sync.localtime()
        except Exception:
            import time
            return time.localtime()

    def _draw(self, force=False):
        mod = registry.load(ClockScreen._style)
        if mod is None:
            return

        try:
            t = self._get_time()
        except Exception:
            return

        has_sec = getattr(mod, 'HAS_SECONDS', True)
        if has_sec:
            key = (ClockScreen._style, ClockScreen._rotation,
                   t[3], t[4], t[5])
        else:
            key = (ClockScreen._style, ClockScreen._rotation,
                   t[3], t[4], 0)
        if not force and key == self._last_draw:
            return
        self._last_draw = key

        landscape = ClockScreen._rotation in (0, 180)
        fn = None
        if landscape:
            fn = getattr(mod, 'draw_face_h', None)
            if fn is None:
                verbose("[CLOCK]", mod.__name__, "no draw_face_h")
                try:
                    tgt = self._target()
                    tgt.fill(0)
                    tgt.text('No H', tgt.width // 2 - 16,
                             tgt.height // 2 - 4, RED)
                except Exception:
                    pass
                return
        else:
            fn = getattr(mod, 'draw_face_v', None) or \
                 getattr(mod, 'draw_face', None)
            if fn is None:
                return

        try:
            fn(self._target(), t, self._top)
        except Exception as e:
            error("face draw:", e)

        if not self._hide_sb:
            try:
                redraw_status_bar()
            except Exception:
                pass

    def _next_style(self):
        total = registry.count()
        if total <= 0:
            return
        ClockScreen._style = (ClockScreen._style + 1) % total
        self._draw(force=True)
        asyncio.create_task(self._flash_hint())

    def _prev_style(self):
        total = registry.count()
        if total <= 0:
            return
        ClockScreen._style = (ClockScreen._style - 1) % total
        self._draw(force=True)
        asyncio.create_task(self._flash_hint())

    def _rotate(self, delta):
        ClockScreen._rotation = (ClockScreen._rotation + delta) % 360
        info("[CLOCK] rotation ->", ClockScreen._rotation)
        self._rot_cache = None
        self._last_draw = None
        self._draw(force=True)
        asyncio.create_task(
            self._flash_hint('Rot {}'.format(ClockScreen._rotation)))

    async def _flash_hint(self, message=None):
        try:
            if message is None:
                mod = registry.load(ClockScreen._style)
                name = ''
                if mod is not None:
                    name = getattr(mod, 'NAME', '')
                if not name:
                    name = registry.display_name(ClockScreen._style)
                total = registry.count()
                hint = '{}/{} {}'.format(
                    ClockScreen._style + 1, total, name)
            else:
                hint = message

            if len(hint) > 26:
                hint = hint[:25] + '…'

            tgt = self._target()
            tw = len(hint) * 8
            x = (tgt.width - tw) // 2
            y = tgt.height - 20
            tgt.fill_rect(x - 4, y - 2, tw + 8, 14, BLACK)
            tgt.text(hint, x, y, WHITE)
        except Exception:
            pass
        await asyncio.sleep_ms(800)
        self._last_draw = None

    async def _clock_loop(self):
        while self._alive:
            try:
                self._draw(force=False)
            except Exception as e:
                error("clock draw:", e)
            await asyncio.sleep_ms(500)

    async def _poll_buttons(self):
        btn = {
            'inc': hardware_setup.increase,
            'dec': hardware_setup.decrease,
            'nxt': hardware_setup.nxt,
            'prv': hardware_setup.prev,
            'sel': hardware_setup.sel,
        }
        last = {k: 1 for k in btn}
        await asyncio.sleep_ms(100)

        while self._alive:
            for name, p in btn.items():
                try:
                    v = p.value()
                except Exception:
                    v = 1
                if v == 0 and last[name] == 1:
                    try:
                        if name == 'inc':
                            self._next_style()
                        elif name == 'dec':
                            self._prev_style()
                        elif name == 'nxt':
                            self._rotate(90)
                        elif name == 'prv':
                            self._rotate(-90)
                        elif name == 'sel':
                            asyncio.create_task(self._do_close())
                    except Exception as e:
                        error("poll:", e)
                last[name] = v
            await asyncio.sleep_ms(30)

    def after_open(self):
        try: super().after_open()
        except Exception:
            pass
        self._alive = True
        self._last_draw = None
        self._rot_cache = None

        registry.invalidate()
        total = registry.count()
        verbose("[CLOCK] after_open: faces={} rot={}".format(
            total, ClockScreen._rotation))

        if total <= 0:
            ClockScreen._style = 0
        elif ClockScreen._style >= total:
            ClockScreen._style = total - 1

        if self._hide_sb:
            try:
                status_bar.stop()
            except Exception:
                pass
            self._top = 0
        else:
            self._top = STATUS_BAR_H if STATUS_BAR_ENABLED else 0
            try:
                redraw_status_bar()
            except Exception:
                pass

        if self._host is not None:
            try:
                self._host.enter()
            except Exception:
                pass

        self._draw(force=True)

        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_buttons())
        if self._clock_task is None or self._clock_task.done():
            self._clock_task = asyncio.create_task(self._clock_loop())

    def on_hide(self):
        self._alive = False
        for t in (self._poll_task, self._clock_task):
            if t and not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass
        self._poll_task = None
        self._clock_task = None

        if self._hide_sb:
            try:
                status_bar.attach()
            except Exception:
                pass

        gc.collect()

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        tgt = ClockScreen.return_screen
        ClockScreen.return_screen = None
        return_to(self, tgt)


AppScreen = ClockScreen