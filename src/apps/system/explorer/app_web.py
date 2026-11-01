# ======================================================================
# app_web.py — веб-версия проводника: экран запуска веб-портала
#
# Сам веб-интерфейс живёт в apps/system/explorer/utils/server.py и
# обслуживает главный портал, проводник файлов и API.
# ======================================================================
import asyncio
import network

from gui.core.ugui import ssd, Screen
from gui.core.colors import BLACK, WHITE, AMBER, DIM, RED

from config import SCREEN_W, STATUS_BAR_ENABLED
from core.ui import make_writer, redraw_status_bar, wait_release_all, return_to
from core.logger import error
from core import power
from core import time_sync
from core.pixel_ui import (
    PixelMenu, PixelClose, header, footer, screen_bg,
    text, fill, frame, MARGIN,
)
import core.status_bar as status_bar

from apps.system.explorer.utils import server
from apps.system.explorer.config import (
    AP_SSID, AP_PASSWORD, FILES_HTTP_PORT, WEB_PASSWORD,
)


TITLE = 'EXPLORER'
PAGE = 'utils/index.html'
# В обычном режиме веб-версия полностью вытесняет classic-экран.
# Приложениям с совместной работой двух режимов можно ставить True.
DUAL_MODE = False


_wifi_return_prev = None
_wifi_return_pending = False


class WebScreen(Screen):
    return_screen = None

    _ITEMS = ('WI-FI NETWORK', 'HOTSPOT')
    _TAGS  = ('STA', 'AP')
    _DESCR = ('Connect to saved Wi-Fi', 'Create access point')

    def __init__(self):
        Screen.__init__(self)
        self.wri = make_writer()
        self._alive = True
        self._busy = False
        self._drawn = False
        self._ap = None
        self._timer = None
        self._conn_state = 'idle'

        self._mode = 'OFFLINE'
        self._url = '-'
        self._ip = '-'
        self._hint = 'SELECT A MODE'
        self._hint_color = WHITE
        self._panel_key = None

        self.menu = PixelMenu(
            self.wri, self._ITEMS, top=78, row_h=34, gap=6,
            kind='rows', tags=self._TAGS, on_select=self._on_pick,
        )
        self.cb = PixelClose(self.wri, 20, SCREEN_W - 36, self._on_close)

    # ------------------------------------------------------------------
    # Панель статуса
    # ------------------------------------------------------------------
    def _set_panel(self, mode=None, url=None, ip=None, hint=None,
                   hint_color=DIM, force=False):
        if mode is not None:
            self._mode = mode
        if url is not None:
            self._url = url
        if ip is not None:
            self._ip = ip
        if hint is not None:
            self._hint = hint
            self._hint_color = hint_color
        key = (self._mode, self._url, self._ip)
        if not force and key == self._panel_key:
            return
        self._panel_key = key
        if self._drawn:
            self._draw_panel()

    def _panel_line(self, y, label, value, color):
        text(label, 24, y, DIM)
        text(str(value)[:15], 100, y, color)

    def _draw_panel(self):
        x, y, w, h = MARGIN, 166, SCREEN_W - 2 * MARGIN, 92
        fill(x, y, w, h, BLACK)
        frame(x, y, w, h, DIM)
        text('STATUS', x + 8, y + 6, DIM)

        self._panel_line(y + 24, 'MODE', self._mode, WHITE)
        self._panel_line(y + 42, 'IP', self._ip, WHITE)
        self._panel_line(y + 60, 'UI PASS', WEB_PASSWORD, AMBER)
        ap = (server.running() and
              server.STATUS.get('mode') == 'ap')
        self._panel_line(y + 78, 'AP PASS',
                         AP_PASSWORD if ap else '-',
                         AMBER if ap else DIM)

    def _update_status(self):
        if not self._alive or not self._drawn or self._busy:
            return
        st = server.STATUS
        if server.running():
            mode = st.get('mode')
            ssid = st.get('ssid') or ''
            if mode == 'ap':
                mtxt = 'AP ' + (ssid or AP_SSID)
            elif mode == 'sta':
                mtxt = 'STA ' + ssid
            else:
                mtxt = 'ONLINE'
            self._set_panel(
                mode=mtxt[:19],
                url='http://{}/'.format(st.get('host') or st.get('ip') or ''),
                ip=st.get('ip') or '-',
                hint='OPEN IN BROWSER',
                hint_color=WHITE,
            )
        elif st.get('error'):
            self._set_panel(mode='ERROR', url='-', ip='-',
                            hint=str(st.get('error'))[:19],
                            hint_color=RED)
        elif self._conn_state == 'no-wifi':
            self._set_panel(mode='NO WIFI', url='-', ip='-',
                            hint='OPEN WI-FI APP', hint_color=DIM)
        else:
            self._set_panel(mode='OFFLINE', url='-', ip='-',
                            hint='SELECT A MODE', hint_color=WHITE)

    # ------------------------------------------------------------------
    # Выбор режима
    # ------------------------------------------------------------------
    def _on_pick(self, idx):
        if self._busy:
            return
        self._busy = True
        asyncio.create_task(self._do_pick(idx))

    async def _do_pick(self, idx):
        try:
            await wait_release_all()
            await asyncio.sleep_ms(80)
            if idx == 0:
                try:
                    sta = network.WLAN(network.STA_IF)
                    connected = sta.isconnected()
                except Exception:
                    connected = False
                if connected:
                    await self._start_sta()
                else:
                    await self._open_wifi()
            elif idx == 1:
                await self._start_ap()
        except Exception as e:
            error('web pick:', e)
            self._set_panel(mode='ERROR', hint=str(e)[:19], hint_color=RED)
        finally:
            self._busy = False
            self._update_status()

    # ------------------------------------------------------------------
    # Wi-Fi приложение
    # ------------------------------------------------------------------
    async def _open_wifi(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        global _wifi_return_prev, _wifi_return_pending
        try:
            from apps.system.wifi.app import WiFiScannerScreen
        except Exception as e:
            error('wifi app:', e)
            self._set_panel(hint='WI-FI APP MISSING', hint_color=RED)
            return
        # Сеть может смениться — сервер поднимем заново после возврата.
        self._stop_all()
        _wifi_return_prev = WiFiScannerScreen.return_screen
        WiFiScannerScreen.return_screen = WebScreen
        _wifi_return_pending = True
        Screen.change(WiFiScannerScreen)

    def _restore_wifi_return(self):
        global _wifi_return_pending
        if not _wifi_return_pending:
            return
        _wifi_return_pending = False
        try:
            from apps.system.wifi.app import WiFiScannerScreen
            WiFiScannerScreen.return_screen = _wifi_return_prev
        except Exception:
            pass

    # ------------------------------------------------------------------
    # STA / AP
    # ------------------------------------------------------------------
    async def _start_sta(self):
        self._conn_state = 'checking'
        self._set_panel(mode='STA CHECKING', url='-', ip='-',
                        hint='PLEASE WAIT', hint_color=DIM)
        self._stop_all()
        try:
            wlan = network.WLAN(network.STA_IF)
            try:
                wlan.active(True)
            except Exception:
                pass
            if not wlan.isconnected():
                self._conn_state = 'no-wifi'
                self._set_panel(mode='NO WIFI', url='-', ip='-',
                                hint='OPEN WI-FI APP', hint_color=DIM)
                return
            self._conn_state = 'sta'
            ip = wlan.ifconfig()[0]
            try:
                ssid = wlan.config('essid') or ''
            except Exception:
                ssid = ''
            try:
                power.remember_wifi(ssid)
            except Exception:
                pass
            try:
                rssi = wlan.status('rssi')
            except Exception:
                rssi = 0
            try:
                from core.connection_state import conn_state
                conn_state.wifi_connected = True
                conn_state.wifi_rssi = rssi
            except Exception:
                pass
            server.start('sta', ssid, ip)
            try:
                if not time_sync.is_synced():
                    asyncio.create_task(time_sync.sync_ntp_retry(3, 1500))
            except Exception as e:
                error('web ntp:', e)
            self._set_panel(mode='STA ' + ssid, ip=ip,
                            url='http://{}/'.format(ip or ''),
                            hint='OPEN IN BROWSER')
        except Exception as e:
            error('sta:', e)
            self._conn_state = 'error'
            self._set_panel(mode='STA ERROR', hint=str(e)[:19], hint_color=RED)

    async def _auto_sta(self):
        if self._busy:
            return
        self._busy = True
        try:
            await self._start_sta()
        finally:
            self._busy = False
            self._update_status()

    async def _start_ap(self):
        self._conn_state = 'ap'
        self._set_panel(mode='AP STARTING', url='-', ip='-',
                        hint='PLEASE WAIT', hint_color=DIM)
        self._stop_all()
        try:
            network.WLAN(network.STA_IF).active(False)
        except Exception:
            pass
        try:
            ap = network.WLAN(network.AP_IF)
            ap.active(True)
            try:
                ap.config(essid=AP_SSID, password=AP_PASSWORD,
                          authmode=network.AUTH_WPA2_PSK)
            except Exception:
                ap.config(essid=AP_SSID, password=AP_PASSWORD)
            self._ap = ap
            ip = ap.ifconfig()[0]
            # Wait until the AP has a real address.
            for _ in range(20):
                if ip and ip != '0.0.0.0':
                    break
                await asyncio.sleep_ms(100)
                ip = ap.ifconfig()[0]
            server.start('ap', AP_SSID, ip)
            self._set_panel(mode='AP ' + AP_SSID, ip=ip,
                            url='http://{}/'.format(ip or ''),
                            hint='OPEN IN BROWSER')
        except Exception as e:
            error('ap:', e)
            self._conn_state = 'error'
            self._set_panel(mode='AP ERROR', hint=str(e)[:19], hint_color=RED)

    def _stop_all(self):
        try:
            server.stop()
        except Exception:
            pass
        if self._ap is not None:
            try:
                self._ap.active(False)
            except Exception:
                pass
            self._ap = None

    # ------------------------------------------------------------------
    # Рисование экрана
    # ------------------------------------------------------------------
    def _draw_all(self):
        screen_bg()
        header('WEB PORTAL', '// SELECT MODE')
        footer('UP/DN', 'MODE', 'SEL', 'START')
        self._panel_key = None
        self._draw_panel()
        self.menu.show()
        self.cb.show()

    def after_open(self):
        global _wifi_return_pending
        was_wifi_return = _wifi_return_pending
        self._alive = True
        self._restore_wifi_return()
        self._drawn = True
        self._draw_all()
        redraw_status_bar()
        try:
            self.move_to(self.menu)
        except Exception:
            pass
        self._update_status()
        if was_wifi_return:
            try:
                asyncio.create_task(self._auto_sta())
            except Exception as e:
                error('web auto sta:', e)
        try:
            self._timer = asyncio.create_task(self._timer_loop())
        except Exception as e:
            error('web timer:', e)

    def on_hide(self):
        # Сервер НЕ останавливаем: из веб-портала можно запустить
        # классическое приложение, и HTTP-сервер должен продолжать жить.
        self._alive = False
        self._drawn = False
        t = self._timer
        self._timer = None
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass
        try:
            super().on_hide()
        except Exception:
            pass

    async def _timer_loop(self):
        while self._alive:
            try:
                self._update_status()
            except Exception:
                pass
            await asyncio.sleep_ms(1000)

    def _on_close(self):
        asyncio.create_task(self._do_close())

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        self._stop_all()
        ret = WebScreen.return_screen
        WebScreen.return_screen = None
        if ret is None:
            ret = self.parent
        return_to(self, ret)
