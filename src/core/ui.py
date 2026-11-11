# ======================================================================
# ui.py — общие UI-хелперы и паддинги (без клавиатуры)
# ======================================================================
import asyncio
import hardware_setup
from gui.core.ugui import ssd, Screen
from gui.core.writer import CWriter
from config import (
    FONT, TEXT_COLOR, BG_COLOR, CLOSE_BTN_Y,
)


# ======================================================================
# Базовые UI-утилиты
# ======================================================================
def make_writer(fg=None, bg=None):
    return CWriter(ssd, FONT, fg or TEXT_COLOR, bg or BG_COLOR, verbose=False)


def place_close_btn(btn):
    if btn is None:
        return
    try:
        btn.row = CLOSE_BTN_Y
        btn.show()
    except Exception:
        pass


async def wait_release_all(timeout_ms=2000):
    try:
        pins = [
            hardware_setup.nxt, hardware_setup.sel, hardware_setup.prev,
            hardware_setup.increase, hardware_setup.decrease,
        ]
    except Exception:
        return
    t = 0
    while t < timeout_ms:
        ok = True
        for p in pins:
            try:
                if p.value() == 0:
                    ok = False
                    break
            except Exception:
                pass
        if ok:
            return
        await asyncio.sleep_ms(30)
        t += 30


async def delayed_focus(widget, delay_ms=100, release_timeout_ms=2000):
    await wait_release_all(release_timeout_ms)
    await asyncio.sleep_ms(delay_ms)
    try:
        widget.enter()
    except Exception:
        pass


def redraw_status_bar():
    try:
        import core.status_bar as sb
        sb.redraw(True)
    except Exception:
        pass


def return_to(screen, target=None):
    """Close an app without growing the screen stack.

    If the requested class is already the live parent, reuse that instance
    (Screen.BACK). Otherwise replace the current screen, keeping the original
    parent, so successive Close presses do not walk back through old apps.
    """
    try:
        if target is None:
            Screen.back()
            return
        if isinstance(target, type):
            parent = getattr(screen, 'parent', None)
            if parent is not None and isinstance(parent, target):
                Screen.change(parent, Screen.BACK)
            else:
                Screen.change(target, Screen.REPLACE)
        else:
            Screen.change(target, Screen.BACK)
    except Exception:
        pass


# ======================================================================
# Паддинг в пикселях
# ======================================================================
def _sp_width(wri):
    try:
        sp = wri.stringlen(' ')
    except Exception:
        sp = 4
    return sp if sp > 0 else 4


def pad_right(wri, s, width_px):
    """Дополнить строку пробелами справа до width_px пикселей.
    Если длиннее — обрезать."""
    sp = _sp_width(wri)
    cur = wri.stringlen(s)
    if cur > width_px:
        while s and wri.stringlen(s) > width_px:
            s = s[:-1]
        cur = wri.stringlen(s)
    n = (width_px - cur) // sp
    return s + ' ' * n if n > 0 else s


def pad_left_num(wri, s, width_px):
    """Вправо-выровнять ЧИСЛО (без обрезки содержимого)."""
    sp = _sp_width(wri)
    cur = wri.stringlen(s)
    if cur >= width_px:
        return s
    n = (width_px - cur) // sp
    return ' ' * n + s if n > 0 else s