# ======================================================================
# main.py — точка входа: пиксельный лаунчер и Classic UI
# ======================================================================
import hardware_setup
import asyncio
import os
import sys

from gui.core.ugui import ssd, Screen
from gui.core.colors import BLACK, WHITE, AMBER, DIM

from config import SCREEN_W, STATUS_BAR_ENABLED
from core.ui import make_writer, redraw_status_bar, wait_release_all
from core.logger import error
from core.pixel_ui import (
    PixelMenu, PixelClose, header, footer, screen_bg,
    big_c, text_c, text, text_r, fill, frame, MARGIN,
)
import core.status_bar as status_bar
import core.shutdown   as shutdown
import core.time_sync  as time_sync


from core import app_registry

APPS_SOURCES = app_registry.SOURCES
APP_CLASS    = app_registry.CLASS_ATTR


def _scan_apps():
    # В классическом меню только приложения с app.py.
    return app_registry.classic_apps()


APPS = _scan_apps()


def _fw_versions():
    """Реальная версия MicroPython и дата сборки прошивки."""
    release = ''
    build = ''
    try:
        u = os.uname()
        release = getattr(u, 'release', '') or ''
        ver = getattr(u, 'version', '') or ''
        marker = ' on '
        pos = ver.find(marker)
        if pos >= 0:
            tail = ver[pos + len(marker):]
            semi = tail.find(';')
            build = tail if semi < 0 else tail[:semi]
    except Exception:
        pass
    return release, build


_FW_RELEASE, _FW_BUILD = _fw_versions()


def _draw_fw_info():
    """Нижний блок лаунчера: версия прошивки вместо декоративной подписи."""
    ssd.hline(MARGIN, 238, SCREEN_W - 2 * MARGIN, DIM)
    text('MICROPYTHON', MARGIN, 246, DIM)
    text_r(_FW_RELEASE or '?', SCREEN_W - MARGIN, 246, WHITE)
    if _FW_BUILD:
        text('BUILD', MARGIN, 258, DIM)
        text_r(_FW_BUILD, SCREEN_W - MARGIN, 258, DIM)


def _load_screen(module_path):
    __import__(module_path)
    mod = sys.modules[module_path]
    return getattr(mod, APP_CLASS)


# ----------------------------------------------------------------------
# Стартовый экран
# ----------------------------------------------------------------------
class LauncherScreen(Screen):
    def __init__(self):
        Screen.__init__(self)
        self._busy = False
        self.wri = make_writer()

        big_c('ESP32', 20, 2, AMBER)
        big_c('HUB', 38, 2, WHITE)

        y = 20 + 36
        ssd.hline(MARGIN, y, SCREEN_W - 2 * MARGIN, AMBER)
        ssd.fill_rect(MARGIN - 4, y - 1, 3, 3, AMBER)
        ssd.fill_rect(SCREEN_W - MARGIN + 1, y - 1, 3, 3, AMBER)
        text_c('// SELECT INTERFACE', y + 8, DIM)

        self.menu = PixelMenu(
            self.wri,
            ('WEB UI', 'CLASSIC UI', 'POWER OFF'),
            top=84, row_h=44, gap=6, kind='cards',
            on_select=self._pick,
        )

        # нижняя информационная строка
        _draw_fw_info()

        footer('UP/DN', 'MOVE', 'SEL', 'OK')

    def after_open(self):
        self._busy = False
        screen_bg()
        big_c('ESP32', 20, 2, AMBER)
        big_c('HUB', 38, 2, WHITE)
        y = 56
        ssd.hline(MARGIN, y, SCREEN_W - 2 * MARGIN, AMBER)
        ssd.fill_rect(MARGIN - 4, y - 1, 3, 3, AMBER)
        ssd.fill_rect(SCREEN_W - MARGIN + 1, y - 1, 3, 3, AMBER)
        text_c('// SELECT INTERFACE', y + 8, DIM)
        _draw_fw_info()
        footer('UP/DN', 'MOVE', 'SEL', 'OK')
        redraw_status_bar()
        try:
            self.move_to(self.menu)
        except Exception:
            pass
        _start_boot_restore()

    def _pick(self, idx):
        if self._busy:
            return
        self._busy = True
        if idx == 2:
            asyncio.create_task(self._power_off())
        else:
            asyncio.create_task(self._goto(idx == 0))

    async def _power_off(self):
        try:
            await wait_release_all(1200)
            await asyncio.sleep_ms(120)
            await shutdown.run()
        except Exception as e:
            error('Launcher power:', type(e).__name__, e)
        self._busy = False

    async def _goto(self, web):
        await wait_release_all(1200)
        await asyncio.sleep_ms(100)
        try:
            if web:
                from apps.system.explorer.app_web import WebScreen
                WebScreen.return_screen = LauncherScreen
                self._busy = False
                Screen.change(WebScreen)
            else:
                self._busy = False
                Screen.change(MenuScreen)
        except Exception as e:
            error('Launcher:', type(e).__name__, e)
            self._busy = False


# ----------------------------------------------------------------------
# Classic UI — список приложений на устройстве
# ----------------------------------------------------------------------
class MenuScreen(Screen):
    def __init__(self):
        Screen.__init__(self)
        self._shutting_down = False
        self.wri = make_writer()
        ssd.fill(0)

        header('CLASSIC UI', '// SELECT APPLICATION')

        self._names = [a[0] for a in APPS]
        els = [n.replace('_', ' ').upper() for n in self._names] or ['NO APPS']

        self.menu = PixelMenu(
            self.wri, els, top=84, row_h=24, gap=3, kind='rows',
            on_select=self._on_select,
        )
        self.cb = PixelClose(self.wri, 20, SCREEN_W - 36, self._on_close)

        footer('UP/DN', 'MOVE', 'SEL', 'OK')

    def after_open(self):
        screen_bg()
        header('CLASSIC UI', '// SELECT APPLICATION')
        footer('UP/DN', 'MOVE', 'SEL', 'OK')
        redraw_status_bar()
        try:
            self.move_to(self.menu)
        except Exception:
            pass
        self.cb.show()
        ey = self.menu.top + len(APPS) * (self.menu.row_h + self.menu.gap)
        if ey < 268:
            text('// END OF LIST', MARGIN + 4, ey + 2, DIM)

    def _on_select(self, idx):
        if self._shutting_down:
            return
        if idx < 0 or idx >= len(APPS):
            return
        name, mod_path = APPS[idx]
        try:
            cls = _load_screen(mod_path)
            cls.return_screen = MenuScreen
            print('Menu:', name)
            asyncio.create_task(self._goto(cls))
        except Exception as e:
            error('Menu:', type(e).__name__, e)

    def _on_close(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.parent is not None:
            Screen.back()
        else:
            asyncio.create_task(shutdown.run())

    async def _goto(self, screen_cls):
        await asyncio.sleep_ms(160)
        if self._shutting_down:
            return
        Screen.change(screen_cls)


def main():
    print('main: opening launcher')
    if APPS:
        print('main: apps found:', [a[0] for a in APPS])
    else:
        print('main: no apps found in', APPS_SOURCES)
    Screen.change(LauncherScreen)


if STATUS_BAR_ENABLED:
    status_bar.attach()


_boot_started = False


def _start_boot_restore():
    """Запустить восстановление сети изнутри работающего asyncio."""
    global _boot_started
    if _boot_started:
        return
    _boot_started = True
    try:
        asyncio.create_task(_boot_restore())
    except Exception as e:
        error('boot start:', type(e).__name__, e)


async def _boot_restore():
    """Поднять последнюю сеть после включения/пробуждения.

    В deep sleep RTC продолжает идти, поэтому время уже сохранено.
    Wi-Fi нужно восстановить вручную: берём последнюю удачную сеть из
    core/power_state.json и, если веб-сервер работал перед сном,
    поднимаем его снова.
    """
    try:
        import network
        from core import power
        from core.connection_state import conn_state

        last = power.last_wifi()
        if not last:
            return
        ssid = last.get('ssid') or ''
        password = last.get('password') or ''
        if not ssid:
            return

        wlan = network.WLAN(network.STA_IF)
        try:
            if not wlan.active():
                wlan.active(True)
        except Exception:
            pass

        current = ''
        try:
            if wlan.isconnected():
                current = wlan.config('essid') or ''
                if isinstance(current, bytes):
                    current = current.decode('utf-8')
        except Exception:
            current = ''

        if not wlan.isconnected() or current != ssid:
            if wlan.isconnected():
                try:
                    wlan.disconnect()
                except Exception:
                    pass
                await asyncio.sleep_ms(400)
            try:
                wlan.config(pm=0x11111111)  # disable modem sleep: keeps link stable
            except Exception:
                pass
            try:
                wlan.connect(ssid, password)
            except Exception as e:
                error('boot wifi connect:', type(e).__name__, e)
            for _ in range(24):  # ~12 s
                if wlan.isconnected():
                    break
                await asyncio.sleep_ms(500)

        if not wlan.isconnected():
            return

        try:
            ip = wlan.ifconfig()[0]
        except Exception:
            ip = ''
        try:
            rssi = wlan.status('rssi')
        except Exception:
            rssi = None
        conn_state.wifi_connected = True
        conn_state.wifi_rssi = rssi if isinstance(rssi, int) else None

        try:
            from apps.system.wifi.app import wifi_state
            wifi_state.wlan = wlan
            wifi_state.ssid = ssid
            wifi_state.password = password
            wifi_state.ip = ip
            wifi_state.connected = True
        except Exception:
            pass

        await time_sync.sync_ntp_retry(3, 1500)
    except Exception as e:
        error('boot restore:', type(e).__name__, e)


if __name__ == '__main__':
    main()
