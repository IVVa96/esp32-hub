# ======================================================================
# status_bar.py — верхняя статус-полоса: время, RSSI WiFi, RSSI BLE
# ======================================================================
import asyncio
import time
import network

from gui.core.ugui import ssd
from config import (
    STATUS_BAR_ENABLED, STATUS_BAR_H,
    STATUS_BAR_BG, STATUS_BAR_CLOCK_COLOR, STATUS_BAR_SEP,
    STATUS_BAR_WIFI_NO_CONN_COLOR, STATUS_BAR_BLE_NO_CONN_COLOR,
    STATUS_BAR_RIGHT_MARGIN, STATUS_BAR_WIFI_RSSI_MS,
    SB_CLOCK_X, SB_CLOCK_Y, SB_ITEMS_GAP,
)
import core.time_sync as time_sync
from core.connection_state import conn_state


_running     = False
_task        = None
_wifi_timer  = 0
_last_render = None


def _get_hm():
    return time_sync.now_hm()


def _ble_display():
    if not conn_state.ble_connected:
        return "B-oo dB", STATUS_BAR_BLE_NO_CONN_COLOR
    rssi = conn_state.ble_rssi
    if rssi is not None:
        return "B{}dB".format(rssi), STATUS_BAR_BLE_NO_CONN_COLOR
    return "B-- dB", STATUS_BAR_BLE_NO_CONN_COLOR


def _wifi_display():
    if not conn_state.wifi_connected or conn_state.wifi_rssi is None:
        return "W-oo dB", STATUS_BAR_WIFI_NO_CONN_COLOR
    return "W{}dB".format(conn_state.wifi_rssi), STATUS_BAR_WIFI_NO_CONN_COLOR


def _update_wifi_cache():
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            r = wlan.status('rssi')
            conn_state.wifi_rssi = r if isinstance(r, int) else None
            conn_state.wifi_connected = True
        else:
            conn_state.clear_wifi()
    except Exception:
        conn_state.clear_wifi()


def redraw(force=False):
    if not STATUS_BAR_ENABLED:
        return

    global _last_render

    hh, mm = _get_hm()
    clock = "{:02d}:{:02d}".format(hh, mm)
    wifi_txt, wifi_color = _wifi_display()
    ble_txt, ble_color   = _ble_display()

    key = (clock, wifi_txt, ble_txt)
    if not force and key == _last_render:
        return
    _last_render = key

    try:
        ssd.fill_rect(0, 0, ssd.width, STATUS_BAR_H, STATUS_BAR_BG)
        ssd.hline(0, STATUS_BAR_H, ssd.width, STATUS_BAR_SEP)
    except Exception:
        pass

    try:
        ssd.text(clock, SB_CLOCK_X, SB_CLOCK_Y, STATUS_BAR_CLOCK_COLOR)
    except Exception:
        pass

    wifi_len = len(wifi_txt) * 8
    wifi_x   = ssd.width - wifi_len - STATUS_BAR_RIGHT_MARGIN
    try:
        ssd.text(wifi_txt, wifi_x, SB_CLOCK_Y, wifi_color)
    except Exception:
        pass

    ble_len = len(ble_txt) * 8
    ble_x   = wifi_x - ble_len - SB_ITEMS_GAP
    try:
        ssd.text(ble_txt, ble_x, SB_CLOCK_Y, ble_color)
    except Exception:
        pass


async def _loop():
    global _wifi_timer
    while _running:
        try:
            _wifi_timer -= 1000
            if _wifi_timer <= 0:
                _wifi_timer = STATUS_BAR_WIFI_RSSI_MS
                _update_wifi_cache()
            redraw(False)
        except Exception:
            pass
        await asyncio.sleep_ms(1000)


def attach():
    global _running, _task, _wifi_timer
    if not STATUS_BAR_ENABLED or _running:
        return
    _running = True
    _update_wifi_cache()
    _wifi_timer = STATUS_BAR_WIFI_RSSI_MS
    redraw(True)
    _task = asyncio.create_task(_loop())


def stop():
    global _running, _task
    _running = False
    if _task is not None:
        try:
            _task.cancel()
        except Exception:
            pass
        _task = None