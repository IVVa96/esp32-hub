# ======================================================================
# web_mode.py — режим работы веб-приложения
#
# По умолчанию веб-версия полностью вытесняет classic-интерфейс:
# экран очищается и гаснет, кнопки и таймеры classic-экрана отключаются,
# а HTTP-сервер продолжает работать.
#
# Если приложение заявляет DUAL_MODE = True в app_web.py, экран и
# classic-версия остаются живыми: оба режима работают одновременно.
# ======================================================================
import gc

import gui.core.ugui as ugui
from gui.core.ugui import Screen, ssd
import core.status_bar as status_bar


_active = False
_dual = False
_screen = None


def active():
    return _active


def dual():
    return _dual


def _backlight(on):
    try:
        import hardware_setup
        hardware_setup.pled.value(1 if on else 0)
    except Exception:
        pass


def enter(dual=False):
    """Включить веб-режим. dual=True — не выключать classic-экран."""
    global _active, _dual, _screen

    dual = bool(dual)
    if _active:
        if dual == _dual:
            return
        exit()

    _screen = Screen.current_screen
    _dual = dual
    _active = True

    if dual:
        # Совместный режим: classic-интерфейс остаётся на экране.
        return

    if _screen is not None:
        try:
            _screen.on_hide()
        except Exception:
            pass

    try:
        status_bar.stop()
    except Exception:
        pass

    ugui.input_enabled = False
    ugui.display_enabled = False

    try:
        ssd.fill(0)
        ssd.show()
    except Exception:
        pass

    _backlight(False)
    gc.collect()


def exit():
    """Выключить веб-режим и вернуть classic-интерфейс."""
    global _active, _dual, _screen

    if not _active:
        return

    was_dual = _dual
    _active = False
    _dual = False

    if was_dual:
        # Совместный режим ничего не выключал — возвращать нечего.
        _screen = None
        return

    ugui.input_enabled = True
    ugui.display_enabled = True
    _backlight(True)

    screen = _screen
    _screen = None

    if screen is not None and Screen.current_screen is screen:
        try:
            screen.after_open()
        except Exception:
            pass
    else:
        try:
            Screen.show(True)
        except Exception:
            pass

    try:
        status_bar.attach()
    except Exception:
        pass

    gc.collect()
