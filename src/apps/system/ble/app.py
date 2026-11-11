# ======================================================================
# app.py — BLE-сканер: ESP32-S3 как централь
# ======================================================================
NAME = 'ble'
# AppScreen = ScannerScreen

import hardware_setup
import asyncio
import gc
import lib.aioble as aioble
from gui.core.ugui import ssd, Screen
from gui.widgets import Label, Listbox, Button
from gui.core.colors import *

from config import (
    TITLE_Y, TITLE_X, STATUS_LBL_GAP,
    LB_Y, LB_X, LB_WIDTH, LB_DLINES, LB_BORDER_COLOR,
    CS_Y_HEADER, CS_Y_NAME, CS_Y_ADDR, CS_Y_STATUS, CS_MARGIN,
    LINE_H, TEXT_W,
    BG_COLOR,
    CLOSE_BTN_X, CLOSE_BTN_Y, CLOSE_BTN_W, CLOSE_BTN_H,
)
from apps.system.ble.config import (
    BLE_SCAN_MS, BLE_SCAN_PAUSE_MS, BLE_CONNECT_TIMEOUT,
    BLE_MAX_DEVICES, BLE_RADIO_SETTLE_MS,
)
from core.ui import (
    make_writer, place_close_btn, wait_release_all, delayed_focus,
    redraw_status_bar, pad_right, pad_left_num, return_to,
)
from apps.system.ble.utils.classify import classify_device
from core.connection_state import conn_state
from core.logger import info, verbose, error


TITLE_TEXT     = 'BLE SCAN'
_aborting_task = None


class BLEState:
    def __init__(self):
        self.connection  = None
        self.device      = None
        self.addr        = None
        self.name        = None
        self.services    = ()
        self.tags        = ()
        self.device_type = 'UNKNOWN'
        self.last_rssi   = None

    def clear(self):
        self.connection  = None
        self.device      = None
        self.addr        = None
        self.name        = None
        self.services    = ()
        self.tags        = ()
        self.device_type = 'UNKNOWN'
        self.last_rssi   = None
        conn_state.clear_ble()


ble_state = BLEState()


class ScannerScreen(Screen):
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        self.scan_count  = 0
        self.devices     = []
        self.addrs       = set()
        self.els         = [' ']
        self._leaving    = False
        self.scan_task   = None
        self._old_task   = None
        self._close_task = None

        self.wri = make_writer()

        self.title_lbl = Label(self.wri, TITLE_Y, TITLE_X, TITLE_TEXT)
        title_w = self.wri.stringlen(TITLE_TEXT)
        lbl_x   = TITLE_X + title_w + STATUS_LBL_GAP
        lbl_w   = ssd.width - lbl_x - 40
        if lbl_w < 20:
            lbl_w = 20
        self.scan_lbl = Label(self.wri, TITLE_Y, lbl_x, lbl_w, justify=1)
        self.scan_lbl.value('Scan 0')

        def on_select(*args):
            try:
                if self._leaving:
                    return
                idx = args[0].value()
                if idx < 0 or idx >= len(self.devices):
                    return
                addr, name, rssi, dev = self.devices[idx]
                verbose("BLE selected:", addr, name)
                ConnectingScreen.target = (addr, name, rssi, dev)
                self._leaving = True
                self._old_task = self.scan_task
                self.scan_task = None
                if self._old_task:
                    try:
                        self._old_task.cancel()
                    except Exception:
                        pass
                asyncio.create_task(self._goto())
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
            self._close_task = asyncio.create_task(self._do_close())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X, text='X',
                         callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass

        self._leaving   = False
        self.scan_count = 0
        self.devices    = []
        self.addrs      = set()
        self.els.clear()
        self.els.append(' ')

        ssd.fill(0)
        try:
            self.title_lbl.show()
            self.scan_lbl.value('Scan 0')
        except Exception:
            pass
        try:
            self.lb.update()
        except Exception:
            pass
        redraw_status_bar()
        place_close_btn(self.cb)

        if self.scan_task is not None:
            try:
                self.scan_task.cancel()
            except Exception:
                pass
            self.scan_task = None

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
        ct = self._close_task
        self._close_task = None
        if ct and not ct.done():
            try:
                ct.cancel()
            except Exception:
                pass
        gc.collect()

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        tgt = ScannerScreen.return_screen
        ScannerScreen.return_screen = None
        return_to(self, tgt)

    async def _goto(self):
        t = self._old_task
        self._old_task = None
        if t:
            try:
                await asyncio.wait_for(t, timeout=2.0)
            except Exception:
                pass
        await asyncio.sleep_ms(400)
        Screen.change(ConnectingScreen)

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

            await asyncio.sleep_ms(BLE_RADIO_SETTLE_MS)
            if self._leaving:
                return
            await self._scan()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error("scan_delayed:", type(e).__name__, e)

    async def _scan(self):
        try:
            while not self._leaving:
                self.scan_count += 1
                self._set_status('Scan {}'.format(self.scan_count))
                try:
                    async with aioble.scan(
                            duration_ms=BLE_SCAN_MS,
                            interval_us=30000,
                            window_us=30000,
                            active=True) as scanner:
                        async for result in scanner:
                            if self._leaving:
                                break
                            addr = result.device.addr_hex()
                            if addr in self.addrs:
                                continue
                            name = result.name() or "N/A"
                            self.addrs.add(addr)
                            self.devices.append(
                                (addr, name, result.rssi, result.device))
                            if len(self.devices) > BLE_MAX_DEVICES:
                                old = self.devices.pop(0)
                                self.addrs.discard(old[0])
                            if not self._leaving:
                                self._refresh()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    error("scan cycle:", type(e).__name__, e)
                gc.collect()
                if not self._leaving:
                    await asyncio.sleep_ms(BLE_SCAN_PAUSE_MS)
        except asyncio.CancelledError:
            pass

    def _set_status(self, text):
        try:
            self.scan_lbl.value(text)
        except Exception:
            pass

    def _refresh(self):
        try:
            self.els.clear()
            inner  = LB_WIDTH - 4
            # Ширины колонок списка устройств — фиксированные пиксели
            # (раньше это были константы из apps/system/ble/config.py)
            name_w = 100
            addr_w = 120
            rssi_n = 38
            name_w = min(name_w, inner - addr_w - rssi_n - 4)
            if name_w < 20:
                name_w = 20

            for addr, name, rssi, _ in self.devices:
                nm = name[:12]
                while nm and self.wri.stringlen(nm) > name_w:
                    nm = nm[:-1]
                nm_pad    = pad_right(self.wri, nm, name_w)
                addr_pad  = pad_right(self.wri, addr, addr_w)
                rssi_cell = pad_left_num(self.wri, str(rssi), rssi_n) + 'dB'
                self.els.append(nm_pad + ' ' + addr_pad + rssi_cell)

            if not self.els:
                self.els.append(' ')
            self.lb.update()
        except Exception as e:
            error("refresh:", type(e).__name__, e)


class ConnectingScreen(Screen):
    target = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        self.wri        = make_writer()
        self.status_lbl = None
        self.retry_btn  = None
        self.task       = None
        self.connection = None
        self._alive     = True
        self._completed = False
        self._last_addr = None
        self._retry_btn_show = None

        if self.target is None:
            Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'No target')

            def _noop(*_a, **_k):
                pass
            self.retry_btn = Button(
                self.wri, ssd.height - 30, CS_MARGIN,
                text=' ', callback=_noop,
                width=80, height=20)
            self._retry_btn_show = self.retry_btn.show
            try:
                self.retry_btn.show = lambda *_a, **_k: None
            except Exception:
                pass
            try:
                ssd.fill_rect(CS_MARGIN - 1, ssd.height - 32,
                              84, 24, BG_COLOR)
            except Exception:
                pass
            self._add_close_btn()
            return

        addr, name, rssi, dev = self.target

        Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'Connecting to')
        Label(self.wri, CS_Y_NAME,   CS_MARGIN, self._clip(name))
        Label(self.wri, CS_Y_ADDR,   CS_MARGIN, addr)

        self.status_lbl = Label(self.wri, CS_Y_STATUS, CS_MARGIN, TEXT_W)
        self.status_lbl.value('Wait...')

        def _noop(*_a, **_k):
            pass

        self.retry_btn = Button(
            self.wri, ssd.height - 30, CS_MARGIN,
            text=' Scan again ', callback=_noop,
            width=self.wri.stringlen(' Scan again '), height=20)
        self._retry_btn_show = self.retry_btn.show
        try:
            self.retry_btn.show = lambda *_a, **_k: None
        except Exception:
            pass
        try:
            ssd.fill_rect(CS_MARGIN - 1, ssd.height - 32,
                          self.wri.stringlen(' Scan again ') + 4,
                          24, BG_COLOR)
        except Exception:
            pass

        self._add_close_btn()

    def _add_close_btn(self):
        # Кнопка выхода: экран подключения без неё — тупик. Раньше при
        # любом исходе (ошибка, UNKNOWN, успешное подключение) выйдти
        # было нельзя, экран выглядел «зависшим».
        def _on_close(*_a, **_k):
            asyncio.create_task(self._do_back())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X, text='X',
                         callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        if self.target is None:
            return

        cur_addr   = self.target[0]
        same       = (cur_addr == self._last_addr)
        task_alive = (self.task is not None and not self.task.done())
        if same and self._completed and not task_alive:
            try:
                conn = ble_state.connection
                if (conn is not None and conn.is_connected()
                        and ble_state.addr == cur_addr):
                    self._status(ble_state.device_type or 'Connected')
                    return
            except Exception:
                pass

        self._last_addr = cur_addr
        self._completed = False
        self.connection = None
        self._alive     = True

        redraw_status_bar()

        if self.task and not self.task.done():
            try:
                self.task.cancel()
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
        global _aborting_task
        self._alive = False
        t = self.task
        self.task = None
        if t and not t.done():
            _aborting_task = t
            try:
                t.cancel()
            except Exception:
                pass
        if not self._completed:
            ble_state.clear()

    async def _connect(self):
        addr, name, rssi, device = self.target
        try:
            if ble_state.connection is not None:
                try:
                    await ble_state.connection.disconnect()
                except Exception:
                    pass
                ble_state.clear()

            self._status('Wait radio...')
            await asyncio.sleep_ms(1500)

            self._status('Connecting...')
            # После неуспешной/прерванной попытки aioble оставляет в
            # device._connection «полусоединение» (_conn_handle=None).
            # Следующий connect() сразу вернул бы этот мёртвый объект
            # и всё дальнейшее зависло бы. Чистим перед новой попыткой.
            stale = getattr(device, '_connection', None)
            if stale is not None and not stale.is_connected():
                device._connection = None
            self.connection = await device.connect(timeout_ms=BLE_CONNECT_TIMEOUT)

            self._status('Discovering...')
            services = []
            try:
                # В vendored aioble services() возвращает async-итератор
                # (ClientDiscover), у него нет __await__. Прежний
                # `await ...services()` кидал TypeError, он молча
                # ловился, сервисы терялись и любое устройство
                # классифицировалось как 'UNKNOWN'.
                disc = self.connection.services()
            except Exception as e:
                error("services():", type(e).__name__, e)
                disc = None

            if disc is not None:
                try:
                    if hasattr(disc, 'services'):
                        s = disc.services
                        s = s() if callable(s) else s
                        if s:
                            services = list(s)
                except Exception:
                    pass
                if not services:
                    try:
                        # Сбор сервисов под жёстким таймаутом: внутри
                        # ClientDiscover таймаут не реализован (TODO в
                        # aioble), подвисший discovery держал бы экран
                        # на 'Discovering...' навсегда.
                        async def _collect():
                            async for s in disc:
                                services.append(s)
                        await asyncio.wait_for(_collect(), 3.0)
                    except Exception as e:
                        verbose("collect services:", type(e).__name__, e)
                if not services:
                    try:
                        services = list(disc)
                    except Exception:
                        pass

            info("CS: discovered {} services".format(len(services)))

            self._status('Classifying...')
            try:
                tags, dtype = await classify_device(services)
            except Exception:
                tags, dtype = (), 'UNKNOWN'

            ble_state.connection  = self.connection
            ble_state.device      = device
            ble_state.addr        = addr
            ble_state.name        = name
            ble_state.services    = tuple(services)
            ble_state.tags        = tags
            ble_state.device_type = dtype
            ble_state.last_rssi   = rssi
            self._completed = True

            conn_state.ble_connected = True
            conn_state.ble_rssi      = rssi

            # 'UNKNOWN' на экране выглядит как ошибка подключения:
            # если устройство не распознано, показываем просто 'Connected'.
            self._status(dtype if dtype != 'UNKNOWN' else 'Connected')
            redraw_status_bar()

        except asyncio.CancelledError:
            if self.connection is not None:
                try:
                    await self.connection.disconnect()
                except Exception:
                    pass
                self.connection = None
            raise
        except Exception as e:
            error("CS connect:", type(e).__name__, e)
            self.connection = None
            if self._alive:
                self._show_error(name, addr, str(e) or type(e).__name__)

    def _show_error(self, name, addr, reason):
        if not self._alive:
            return

        ssd.fill(0)
        Label(self.wri, CS_Y_HEADER, CS_MARGIN, 'Unable to connect')
        Label(self.wri, CS_Y_NAME,   CS_MARGIN, self._clip(name))
        Label(self.wri, CS_Y_ADDR,   CS_MARGIN, addr)
        Label(self.wri, CS_Y_STATUS, CS_MARGIN, 'Reason:')

        top       = CS_Y_STATUS + LINE_H
        max_lines = max(1, (ssd.height - top - 40) // LINE_H)
        lines     = self._wrap(reason, max_lines)
        for j, line in enumerate(lines):
            Label(self.wri, top + j * LINE_H, CS_MARGIN, line)

        redraw_status_bar()

        def _retry(*_a, **_k):
            asyncio.create_task(self._do_retry())

        try:
            self.retry_btn.text     = ' Scan again '
            self.retry_btn.callback = _retry
            self.retry_btn.show     = self._retry_btn_show
            self.retry_btn.show()
        except Exception as e:
            error("retry_btn show:", e)

        # ssd.fill(0) выше стёр и кнопку X — перерисовываем
        try:
            self.cb.show()
        except Exception:
            pass

        asyncio.create_task(delayed_focus(self.retry_btn))

    async def _do_retry(self):
        if ble_state.connection is not None:
            try:
                await ble_state.connection.disconnect()
            except Exception:
                pass
            ble_state.clear()
        await wait_release_all()
        await asyncio.sleep_ms(400)
        Screen.change(ScannerScreen)

    async def _do_back(self):
        # Выход по кнопке X: возвращаемся в сканер (REPLACE, как и
        # 'Scan again'). Если подключение ещё устанавливается, задачу
        # погасит on_hide() (через _aborting_task).
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(ScannerScreen)

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


def connect_device():
    Screen.change(ScannerScreen)
    return ble_state


def get_connection():  return ble_state.connection
def get_services():    return ble_state.services
def get_device_type(): return ble_state.device_type
def get_tags():        return ble_state.tags
def is_connected():    return ble_state.connection is not None


async def disconnect():
    if ble_state.connection:
        try:
            await ble_state.connection.disconnect()
        except Exception:
            pass
        ble_state.clear()


AppScreen = ScannerScreen