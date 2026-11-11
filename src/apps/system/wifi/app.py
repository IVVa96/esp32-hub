# ======================================================================
# app.py — WiFi-сканер: ESP32-S3 как клиент
# ======================================================================
NAME = 'wifi'
# AppScreen = WiFiScannerScreen

import hardware_setup
import asyncio
import gc
import time
import network
from gui.core.ugui import ssd, Screen
from gui.widgets import Label, Listbox, Button
from gui.core.colors import *

from config import (
    TITLE_Y, TITLE_X, STATUS_LBL_GAP,
    LB_Y, LB_X, LB_WIDTH, LB_DLINES, LB_BORDER_COLOR,
    CS_Y_HEADER, CS_Y_NAME, CS_Y_STATUS, CS_MARGIN,
    LINE_H, TEXT_W,
    KB_CELL_W, KB_CELL_H, KB_X,
    BG_COLOR,
    CLOSE_BTN_X, CLOSE_BTN_Y, CLOSE_BTN_W, CLOSE_BTN_H,
    SCREEN_W,
)
from apps.system.wifi.config import (
    WIFI_SCAN_INTERVAL_MS, WIFI_CONNECT_TIMEOUT_MS,
    WIFI_MAX_NETWORKS, WIFI_SAVED_MARKER,
    PW_Y_TITLE, PW_Y_SSID, PW_Y_INPUT, PW_Y_HINT, PW_KB_Y,
)
from core.ui import (
    make_writer, place_close_btn, wait_release_all, delayed_focus,
    redraw_status_bar, pad_right, pad_left_num,
)
from core.keyboard_widget import Keyboard, ROW_SAVED
from apps.system.wifi.utils import passwords as wp
import core.time_sync as time_sync
from core.connection_state import conn_state
from core import power
from core.logger import info, error


TITLE_TEXT            = 'WIFI SCAN'
SUCCESS_MENU_DELAY_MS = 1800

_wlan_reset_needed = False
_aborting_task     = None


def _auth_label(authmode):
    return 'open' if authmode == 0 else 'sec'


def _exit_to(target):
    """Return to the screen instance that opened the Wi-Fi flow.

    Using the live parent instance keeps a single navigation stack: the
    previous code re-created MenuScreen as a child of the connecting screen,
    so closing Classic UI went back to Wi-Fi instead of the launcher.
    """
    if target is None:
        try:
            Screen.back()
        except Exception:
            pass
    elif isinstance(target, type):
        Screen.change(target, Screen.REPLACE)
    else:
        Screen.change(target, Screen.BACK)


class WiFiState:
    def __init__(self):
        self.wlan      = None
        self.ssid      = None
        self.password  = None
        self.ip        = None
        self.connected = False

    def clear(self):
        self.wlan = self.ssid = self.password = self.ip = None
        self.connected = False
        conn_state.clear_wifi()


wifi_state = WiFiState()


class WiFiScannerScreen(Screen):
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        self.networks   = []
        self.els        = [' ']
        self._leaving   = False
        self._exit_target = None
        self.scan_task  = None
        self._goto_task = None
        self.scan_count = 0

        self.wri = make_writer()

        self.title_lbl = Label(self.wri, TITLE_Y, TITLE_X, TITLE_TEXT)
        title_w = self.wri.stringlen(TITLE_TEXT)
        lbl_x   = TITLE_X + title_w + STATUS_LBL_GAP
        lbl_w   = ssd.width - lbl_x - 40
        if lbl_w < 20:
            lbl_w = 20
        self.status_lbl = Label(self.wri, TITLE_Y, lbl_x, lbl_w, justify=1)
        self.status_lbl.value('Scan 0')

        def on_select(*args):
            try:
                if self._leaving:
                    return
                idx = args[0].value()
                if idx < 0 or idx >= len(self.networks):
                    return
                ssid, rssi, authmode = self.networks[idx]
                self._leaving = True
                if self.scan_task:
                    try:
                        self.scan_task.cancel()
                    except Exception:
                        pass
                    self.scan_task = None

                if authmode == 0:
                    WiFiConnectingScreen.target   = ssid
                    WiFiConnectingScreen.authmode = 0
                    WiFiConnectingScreen.password = ''
                    WiFiConnectingScreen.return_screen = self._exit_target
                    self._goto_task = asyncio.create_task(self._goto_connect())
                else:
                    saved = wp.get_password(ssid)
                    if saved:
                        WiFiConnectingScreen.target   = ssid
                        WiFiConnectingScreen.authmode = authmode
                        WiFiConnectingScreen.password = saved
                        WiFiConnectingScreen.return_screen = self._exit_target
                        self._goto_task = asyncio.create_task(self._goto_connect())
                    else:
                        WiFiPasswordScreen.target   = ssid
                        WiFiPasswordScreen.authmode = authmode
                        WiFiPasswordScreen.return_screen = self._exit_target
                        WiFiPasswordScreen.back_screen = self
                        self._goto_task = asyncio.create_task(self._goto_password())
            except Exception as e:
                error("on_select:", e)

        self.lb = Listbox(self.wri, LB_Y + 5, LB_X, elements=self.els,
                          dlines=LB_DLINES, width=LB_WIDTH,
                          bdcolor=LB_BORDER_COLOR, callback=on_select)

        def _on_close(*_a, **_k):
            if self._leaving:
                return
            self._leaving = True
            if self.scan_task:
                try:
                    self.scan_task.cancel()
                except Exception:
                    pass
                self.scan_task = None
            if self._goto_task and not self._goto_task.done():
                try:
                    self._goto_task.cancel()
                except Exception:
                    pass
                self._goto_task = None
            asyncio.create_task(self._do_close())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X, text='X',
                         callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass

        ssd.fill(0)
        try:
            self.title_lbl.show()
            self.status_lbl.value('Scan 0')
        except Exception:
            pass
        redraw_status_bar()
        place_close_btn(self.cb)

        self._leaving   = False
        self.scan_count = 0
        self.networks   = []
        self._exit_target = (self.parent if self.parent is not None
                             else WiFiScannerScreen.return_screen)
        WiFiScannerScreen.return_screen = None
        self.els.clear()
        self.els.append(' ')
        try:
            self.lb.update()
        except Exception:
            pass

        if self.scan_task is not None:
            try:
                self.scan_task.cancel()
            except Exception:
                pass
            self.scan_task = None
        if self._goto_task is not None:
            if not self._goto_task.done():
                try:
                    self._goto_task.cancel()
                except Exception:
                    pass
            self._goto_task = None

        self.scan_task = asyncio.create_task(self._scan_delayed())

    def on_hide(self):
        self._leaving = True
        t = self.scan_task
        self.scan_task = None
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        g = self._goto_task
        self._goto_task = None
        if g and not g.done():
            try:
                g.cancel()
            except Exception:
                pass
        gc.collect()

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        tgt = self._exit_target if self._exit_target is not None else self.parent
        self._exit_target = None
        WiFiScannerScreen.return_screen = None
        _exit_to(tgt)

    async def _goto_connect(self):
        await wait_release_all()
        await asyncio.sleep_ms(120)
        Screen.change(WiFiConnectingScreen)

    async def _goto_password(self):
        await wait_release_all()
        await asyncio.sleep_ms(120)
        Screen.change(WiFiPasswordScreen)

    async def _scan_delayed(self):
        global _aborting_task
        try:
            if _aborting_task is not None:
                t = _aborting_task
                _aborting_task = None
                try:
                    await asyncio.wait_for(t, timeout=2.5)
                except Exception:
                    pass
                await asyncio.sleep_ms(800)

            await asyncio.sleep_ms(400)
            if self._leaving:
                return
            await self._scan()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error("scan_delayed:", type(e).__name__, e)

    async def _scan(self):
        while not self._leaving:
            self.scan_count += 1
            self._set_status('Scan {}'.format(self.scan_count))
            try:
                nets = self._do_scan()
            except Exception as e:
                error("scan:", type(e).__name__, e)
                nets = []
            if self._leaving:
                return
            self.networks = nets[:WIFI_MAX_NETWORKS]
            self._refresh()
            ticks = WIFI_SCAN_INTERVAL_MS // 100
            for _ in range(ticks):
                if self._leaving:
                    return
                await asyncio.sleep_ms(100)

    def _do_scan(self):
        global _wlan_reset_needed
        wlan = network.WLAN(network.STA_IF)
        try:
            connected = wlan.isconnected()
        except Exception:
            connected = False

        if connected:
            _wlan_reset_needed = False
        else:
            need = _wlan_reset_needed
            _wlan_reset_needed = False
            if not need:
                try:
                    if wlan.status() not in (0, 5):
                        need = True
                except Exception:
                    pass
            if need:
                try:
                    wlan.active(False)
                    time.sleep_ms(300)
                except Exception:
                    pass
            try:
                wlan.active(True)
            except Exception:
                pass
            time.sleep_ms(50)

        raw = wlan.scan()
        out, seen = [], set()
        for item in raw:
            try:
                ssid, bssid, channel, rssi, authmode, hidden = item
            except Exception:
                continue
            if isinstance(ssid, bytes):
                try:
                    ssid = ssid.decode('utf-8')
                except Exception:
                    continue
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            out.append((ssid, rssi, authmode))
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    def _set_status(self, text):
        try:
            self.status_lbl.value(text)
        except Exception:
            pass

    def _refresh(self):
        try:
            self.els.clear()
            inner  = LB_WIDTH - 4
            # Ширины колонок RSSI и типа защиты — фиксированные пиксели
            # (раньше это были константы из apps/system/wifi/config.py)
            rssi_n = 32
            sec_w  = 24
            saved_w = (self.wri.stringlen(WIFI_SAVED_MARKER) + 4
                       if WIFI_SAVED_MARKER else 0)
            rssi_w  = rssi_n + self.wri.stringlen('dB')
            fixed   = (self.wri.stringlen(' ') + sec_w +
                       self.wri.stringlen(' ') + saved_w +
                       self.wri.stringlen(' '))
            ssid_w = inner - rssi_w - fixed
            if ssid_w < 30:
                ssid_w = 30

            for ssid, rssi, authmode in self.networks:
                try:
                    has_pwd = wp.get_password(ssid) is not None
                except Exception:
                    has_pwd = False
                s = ssid
                while s and self.wri.stringlen(s) > ssid_w:
                    s = s[:-1]
                ssid_pad = pad_right(self.wri, s, ssid_w)
                sec_pad  = pad_right(self.wri, _auth_label(authmode), sec_w)
                marker   = WIFI_SAVED_MARKER if has_pwd else ''
                saved_pad = (pad_left_num(self.wri, marker, saved_w)
                             if saved_w > 0 else '')
                rssi_cell = pad_left_num(self.wri, str(rssi), rssi_n) + 'dB'
                self.els.append(
                    ssid_pad + ' ' + sec_pad + ' ' +
                    saved_pad + ' ' + rssi_cell)

            if not self.els:
                self.els.append(' ')
            self.lb.update()
        except Exception as e:
            error("refresh:", type(e).__name__, e)


class WiFiPasswordScreen(Screen):
    target   = None
    authmode = 0
    return_screen = None
    back_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        if self.target is None:
            Label(self.wri, PW_Y_TITLE, CS_MARGIN, 'No target')
            self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X, text='X',
                             width=CLOSE_BTN_W, height=CLOSE_BTN_H)
            place_close_btn(self.cb)
            self.kb = None
            return

        Label(self.wri, PW_Y_TITLE, CS_MARGIN, 'Enter WiFi password')
        Label(self.wri, PW_Y_SSID,  CS_MARGIN, self._clip(self.target))

        self.pwd_lbl = Label(self.wri, PW_Y_INPUT, CS_MARGIN, TEXT_W)
        self.pwd_lbl.value('')
        self.hint_lbl = Label(self.wri, PW_Y_HINT, CS_MARGIN, TEXT_W)
        self.hint_lbl.value('')

        def kb_cb(action, text):
            if action == 'CHANGED':
                try:
                    self.pwd_lbl.value(text)
                    self.hint_lbl.value('')
                except Exception:
                    pass
            elif action == 'OK':
                self._on_ok(text)
            elif action == 'CANCEL':
                self._on_cancel()
            elif action == 'SAVED':
                self._on_saved()

        self.cb = None
        self.kb = Keyboard(self.wri, PW_KB_Y, KB_X,
                           cell_w=KB_CELL_W, cell_h=KB_CELL_H,
                           callback=kb_cb)
        self.kb.cursor_r = ROW_SAVED
        self.kb.cursor_c = 0
        self.kb.enter()

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        if self.kb is None:
            return
        self.kb.text = ''
        self.kb.shift = False
        self.kb.cursor_r = ROW_SAVED
        self.kb.cursor_c = 0
        try:
            self.pwd_lbl.value('')
            self.hint_lbl.value('')
        except Exception:
            pass
        self.kb.show()
        self.kb.enter()

    def on_hide(self):
        if self.kb is not None:
            try:
                self.kb.stop_poll()
            except Exception:
                pass
        try:
            super().on_hide()
        except Exception:
            pass

    def _clip(self, text):
        s = text or ''
        while s and self.wri.stringlen(s) > TEXT_W:
            s = s[:-1]
        return s

    def _on_ok(self, text):
        text = text or ''
        if not text:
            try:
                self.hint_lbl.value('Password is empty')
            except Exception:
                pass
            return
        if self.authmode != 0 and len(text) < 8:
            try:
                self.hint_lbl.value('Min 8 characters')
            except Exception:
                pass
            return
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        WiFiConnectingScreen.target   = self.target
        WiFiConnectingScreen.authmode = self.authmode
        WiFiConnectingScreen.password = text
        WiFiConnectingScreen.return_screen = WiFiPasswordScreen.return_screen
        asyncio.create_task(self._goto())

    def _on_cancel(self):
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        asyncio.create_task(self._goto_back())

    def _on_saved(self):
        pwd = wp.get_password(self.target)
        if pwd:
            self.kb.text = pwd
            try:
                self.pwd_lbl.value(pwd)
                self.hint_lbl.value('')
            except Exception:
                pass
            try:
                self.kb.show()
            except Exception:
                pass
        else:
            try:
                self.hint_lbl.value('No saved password')
            except Exception:
                pass

    async def _goto(self):
        await wait_release_all()
        await asyncio.sleep_ms(120)
        Screen.change(WiFiConnectingScreen)

    async def _goto_back(self):
        await wait_release_all()
        await asyncio.sleep_ms(120)
        tgt = WiFiPasswordScreen.back_screen if WiFiPasswordScreen.back_screen is not None else self.parent
        WiFiPasswordScreen.back_screen = None
        _exit_to(tgt)


class WiFiConnectingScreen(Screen):
    target   = None
    authmode = 0
    password = None
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        self.wri        = make_writer()
        self.status_lbl = None
        self.task       = None
        self.retry_btn  = None
        self.pwd_btn    = None
        self._alive     = True
        self._completed = False
        self._last_ssid = None
        self._exit_target = None

        if self.target is None:
            Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'No target')

            def _noop(*_a, **_k):
                pass
            Button(self.wri, 0, 0, text=' ', callback=_noop,
                   width=1, height=1)
            return

        Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'Connecting to')
        Label(self.wri, CS_Y_NAME,   CS_MARGIN, self._clip(self.target))

        self.status_lbl = Label(self.wri, CS_Y_STATUS, CS_MARGIN, TEXT_W)
        self.status_lbl.value('Wait...')

        def _noop(*_a, **_k):
            pass

        _by  = ssd.height - 30
        _bh  = 22
        _gap = 6
        _bw  = (SCREEN_W - 2 * CS_MARGIN - _gap) // 2
        _x1  = CS_MARGIN
        _x2  = CS_MARGIN + _bw + _gap

        self.pwd_btn   = Button(self.wri, _by, _x1, text=' ',
                                callback=_noop, width=_bw, height=_bh)
        self.retry_btn = Button(self.wri, _by, _x2, text=' ',
                                callback=_noop, width=_bw, height=_bh)
        try:
            ssd.fill_rect(0, _by - 2, SCREEN_W, _bh + 4, BG_COLOR)
        except Exception:
            pass
        try:
            self.pwd_btn.enter()
        except Exception:
            pass

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        if self.target is None:
            return

        same       = (self.target == self._last_ssid)
        task_alive = (self.task is not None and not self.task.done())
        if same and self._completed and not task_alive:
            try:
                w = network.WLAN(network.STA_IF)
                if w.isconnected() and wifi_state.ssid == self.target:
                    self._status('IP: {}'.format(wifi_state.ip))
                    return
            except Exception:
                pass

        ssd.fill(0)
        try:
            Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'Connecting to')
            Label(self.wri, CS_Y_NAME,   CS_MARGIN, self._clip(self.target))
            self.status_lbl.value('Wait...')
        except Exception as e:
            error("CS redraw:", e)

        try:
            self.pwd_btn.text   = ' '
            self.retry_btn.text = ' '
        except Exception:
            pass

        try:
            _by = ssd.height - 30
            _bh = 22
            ssd.fill_rect(0, _by - 2, SCREEN_W, _bh + 4, BG_COLOR)
        except Exception:
            pass

        redraw_status_bar()

        self._last_ssid = self.target
        self._completed = False
        self._alive     = True
        self._exit_target = (WiFiConnectingScreen.return_screen
                             if WiFiConnectingScreen.return_screen is not None
                             else self.parent)
        WiFiConnectingScreen.return_screen = None

        if self.task and not self.task.done():
            try:
                self.task.cancel()
            except Exception:
                pass
        try:
            self.pwd_btn.enter()
        except Exception:
            pass
        self.task = asyncio.create_task(self._connect())

    def _clip(self, text):
        s = text or ''
        while s and self.wri.stringlen(s) > TEXT_W:
            s = s[:-1]
        return s

    def _status(self, text):
        if not self._alive:
            return
        try:
            if self.status_lbl:
                self.status_lbl.value(text)
        except Exception:
            pass

    def on_hide(self):
        global _aborting_task, _wlan_reset_needed
        self._alive = False
        t = self.task
        self.task = None
        if t and not t.done():
            _aborting_task = t
            try:
                t.cancel()
            except Exception:
                pass
            _wlan_reset_needed = True
        if not self._completed:
            wifi_state.clear()

    async def _connect(self):
        global _wlan_reset_needed, _aborting_task
        ssid     = self.target
        authmode = self.authmode
        try:
            if _aborting_task is not None:
                t = _aborting_task
                _aborting_task = None
                try:
                    await asyncio.wait_for(t, timeout=2.5)
                except Exception:
                    pass
                await asyncio.sleep_ms(800)

            if not self._alive:
                return

            wlan = network.WLAN(network.STA_IF)
            need_reset = _wlan_reset_needed
            _wlan_reset_needed = False
            if need_reset:
                self._status('Reset radio...')
                try:
                    wlan.active(False)
                    await asyncio.sleep_ms(300)
                except Exception:
                    pass
            try:
                if not wlan.active():
                    wlan.active(True)
                    await asyncio.sleep_ms(100)
            except Exception:
                try:
                    wlan.active(True)
                except Exception:
                    pass

            if not self._alive:
                return

            try:
                if wlan.status() == 1:
                    try:
                        wlan.disconnect()
                    except Exception:
                        pass
                    for _ in range(30):
                        await asyncio.sleep_ms(100)
                        if wlan.status() == 0:
                            break
            except Exception:
                pass

            if not self._alive:
                return

            if authmode == 0:
                password = ''
            else:
                password = self.password or wp.get_password(ssid)
                if not password:
                    _wlan_reset_needed = True
                    self._show_error(ssid, 'No password. Enter password.')
                    return

            self._status('Init WLAN...')

            if wlan.isconnected() and wifi_state.ssid == ssid:
                ip = wlan.ifconfig()[0]
                wifi_state.wlan, wifi_state.ssid = wlan, ssid
                wifi_state.password, wifi_state.ip = password, ip
                wifi_state.connected = True
                self._completed = True
                conn_state.wifi_connected = True
                power.remember_wifi(ssid, password)
                self._status('IP: {}'.format(ip))
                asyncio.create_task(time_sync.sync_ntp_once())
                asyncio.create_task(self._goto_menu())
                return

            if wlan.isconnected():
                try:
                    wlan.disconnect()
                except Exception:
                    pass
                await asyncio.sleep_ms(400)

            if not self._alive:
                return

            self._status('Connecting...')
            try:
                wlan.connect(ssid, password)
            except Exception as e:
                _wlan_reset_needed = True
                self._show_error(ssid, 'connect(): {}'.format(e))
                return

            elapsed = 0
            while elapsed < WIFI_CONNECT_TIMEOUT_MS:
                if wlan.isconnected():
                    break
                await asyncio.sleep_ms(500)
                elapsed += 500

            if wlan.isconnected():
                ip = wlan.ifconfig()[0]
                wifi_state.wlan, wifi_state.ssid = wlan, ssid
                wifi_state.password, wifi_state.ip = password, ip
                wifi_state.connected = True
                conn_state.wifi_connected = True
                self._completed = True
                power.remember_wifi(ssid, password)
                self._status('IP: {}'.format(ip))
                if authmode != 0 and password:
                    wp.save_password(ssid, password)
                info("WiFi OK: {} IP={}".format(ssid, ip))
                asyncio.create_task(time_sync.sync_ntp_once())
                asyncio.create_task(self._goto_menu())
                return
            else:
                try:
                    status = wlan.status()
                except Exception:
                    status = '?'
                _wlan_reset_needed = True
                self._show_error(ssid, 'Status={}'.format(status))
        except asyncio.CancelledError:
            try:
                network.WLAN(network.STA_IF).disconnect()
            except Exception:
                pass
            _wlan_reset_needed = True
            raise
        except Exception as e:
            error("WiFi connect:", type(e).__name__, e)
            _wlan_reset_needed = True
            if self._alive:
                self._show_error(ssid, str(e) or type(e).__name__)

    def _show_error(self, ssid, reason):
        if not self._alive:
            return

        ssd.fill(0)
        Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'Unable to connect')
        Label(self.wri, CS_Y_NAME,   CS_MARGIN, self._clip(ssid))
        Label(self.wri, CS_Y_STATUS, CS_MARGIN, 'Reason:')

        top       = CS_Y_STATUS + LINE_H
        max_lines = max(1, (ssd.height - top - 90) // LINE_H)
        lines     = self._wrap(reason, max_lines)
        for j, line in enumerate(lines):
            Label(self.wri, top + j * LINE_H, CS_MARGIN, line)

        def _retry(*_a, **_k):
            asyncio.create_task(self._do_retry())
        def _enter_pwd(*_a, **_k):
            asyncio.create_task(self._do_enter_pwd())

        try:
            self.pwd_btn.text     = 'Enter password'
            self.pwd_btn.callback = _enter_pwd
            self.pwd_btn.show()
        except Exception as e:
            error("pwd_btn:", e)

        try:
            self.retry_btn.text     = 'Scan again'
            self.retry_btn.callback = _retry
            self.retry_btn.show()
        except Exception as e:
            error("retry_btn:", e)

        redraw_status_bar()
        asyncio.create_task(delayed_focus(self.pwd_btn))

    async def _goto_menu(self):
        await wait_release_all()
        await asyncio.sleep_ms(SUCCESS_MENU_DELAY_MS)
        tgt = self._exit_target if self._exit_target is not None else self.parent
        self._exit_target = None
        WiFiConnectingScreen.return_screen = None
        _exit_to(tgt)

    async def _do_retry(self):
        try:
            w = network.WLAN(network.STA_IF)
            if w.isconnected():
                w.disconnect()
        except Exception:
            pass
        wifi_state.clear()
        # "Scan again" всегда возвращает в сканер. Экран подключения мог быть
        # открыт через экран пароля: тогда self.parent — пароль, а не список
        # сетей, и раньше обе кнопки вели в ввод пароля. Поднимаемся по цепочке
        # родителей до живого экземпляра сканера и прыгаем к нему (Screen.BACK),
        # чтобы не плодить копии в стеке.
        tgt = self.parent
        while tgt is not None and not isinstance(tgt, WiFiScannerScreen):
            tgt = getattr(tgt, 'parent', None)
        await wait_release_all()
        await asyncio.sleep_ms(200)
        _exit_to(tgt)

    async def _do_enter_pwd(self):
        WiFiPasswordScreen.target   = self.target
        WiFiPasswordScreen.authmode = self.authmode
        WiFiPasswordScreen.return_screen = self._exit_target
        WiFiPasswordScreen.back_screen = self.parent
        await wait_release_all()
        await asyncio.sleep_ms(150)
        Screen.change(WiFiPasswordScreen)

    def _wrap(self, text, max_lines):
        lines = []
        while text and len(lines) < max_lines:
            n = len(text)
            while n > 0 and self.wri.stringlen(text[:n]) > TEXT_W:
                n -= 1
            if n == 0:
                n = 1
            if n >= len(text):
                lines.append(text)
                break
            chunk = text[:n]
            cut = max(chunk.rfind(' '), chunk.rfind(','), chunk.rfind(':'))
            if cut >= n // 2:
                lines.append(text[:cut + 1].rstrip())
                text = text[cut + 1:].lstrip()
            else:
                lines.append(chunk)
                text = text[n:].lstrip()
        return lines or ['']


def get_wifi_state():         return wifi_state
def is_connected():           return wifi_state.connected
def get_ip():                 return wifi_state.ip
def get_saved_password(ssid): return wp.get_password(ssid)


def disconnect():
    if wifi_state.wlan:
        try:
            wifi_state.wlan.disconnect()
        except Exception:
            pass
    wifi_state.clear()


AppScreen = WiFiScannerScreen