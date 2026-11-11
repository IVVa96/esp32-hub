# ======================================================================
# app.py — Radio Scanner: 2.4GHz spectrum analyzer (Wi-Fi/BLE hardware)
#
# Показывает не список сетей, а "спектр" 2400–2484 МГц: для каждого
# Wi-Fi канала 1..13 рисуется столбик уровня сигнала (max RSSI среди
# найденных точек доступа) + маркер пика с плавным спадом, как в
# сканере NRF24 на прошивке Bruce / Flipper Zero.
# ======================================================================
NAME = 'radio_scanner'

import hardware_setup
import asyncio
import gc
import network

from gui.core.ugui import ssd, Screen
from gui.widgets import Button
from gui.core.colors import AMBER, DIM, GREEN, RED, WHITE, BLACK, PANEL

from config import (
    TITLE_Y, TITLE_X, STATUS_BAR_H,
    CLOSE_BTN_X, CLOSE_BTN_Y, CLOSE_BTN_W, CLOSE_BTN_H,
    SCREEN_W, SCREEN_H,
)
from core.ui import (
    make_writer, place_close_btn, wait_release_all, redraw_status_bar,
)
from core.logger import info, error

TITLE_TEXT  = '2.4G SPECTRUM'
SUB_TEXT    = '2412 - 2472 MHz'

CH_FIRST    = 1
CH_LAST     = 13
CH_COUNT    = CH_LAST - CH_FIRST + 1

RSSI_MIN    = -95.0          # низ графика
RSSI_MAX    = -35.0          # верх графика

SCAN_GAP_MS = 20             # пауза между проходами (максимальная скорость)
PEAK_DECAY  = 2.0            # спад пика, % за обновление
UPDATE_EVERY = 5             # обновлять график каждые N сканов (для скорости)

# ---- Геометрия графика ----
GX   = 8
GW   = SCREEN_W - 2 * GX
GY   = TITLE_Y + 24
GH   = 120
GBASE = GY + GH
BAR_W = max(4, (GW - 2) // CH_COUNT - 3)
STEP  = (GW - 2) // CH_COUNT


def _ch_mhz(ch):
    """Центральная частота Wi-Fi канала, МГц."""
    return 2407 + 5 * ch


def _level(rssi):
    """RSSI дБм -> 0..100 % высоты."""
    v = (rssi - RSSI_MIN) * 100.0 / (RSSI_MAX - RSSI_MIN)
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


class RadioScannerScreen(Screen):
    def __init__(self):
        super().__init__()

        self.wri     = make_writer()
        self.wri_dim = make_writer(DIM)

        self.scanning   = True
        self.levels     = [0.0] * CH_COUNT    # текущий уровень, %
        self.peaks      = [0.0] * CH_COUNT    # пик с удержанием, %
        self.best_rssi  = [-100.0] * CH_COUNT
        self.ap_count   = 0
        self.err        = None
        self._task      = None
        self._leaving   = False
        self.scan_count = 0                    # счётчик сканов для оптимизации отрисовки

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X, text='X',
                          callback=self._on_close,
                          width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

        self.btn = Button(self.wri, SCREEN_H - 26, (SCREEN_W - 96) // 2,
                          text='STOP', callback=self._on_toggle,
                          width=96, height=22)
        # Первой кнопке даём фокус энкодера.
        try:
            self.selected_obj = len(self.lstactive) - 1
        except Exception:
            pass

    # ---------------- lifecycle ----------------
    def after_open(self):
        ssd.fill(0)
        self._draw_static()
        redraw_status_bar()
        place_close_btn(self.cb)
        self.btn.show()
        self._task = asyncio.create_task(self._scan_loop())

    def on_hide(self):
        self._leaving = True
        self._stop_task()
        gc.collect()

    def _stop_task(self):
        t = self._task
        self._task = None
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass

    # ---------------- buttons ----------------
    def _on_toggle(self, btn=None):
        self.scanning = not self.scanning
        self.btn.text = 'STOP' if self.scanning else 'SCAN'
        self.btn.draw = True
        info('radio_scanner:', 'scan', self.scanning)

    def _on_close(self, btn=None):
        if self._leaving:
            return
        self._leaving = True
        self.scanning = False
        self._stop_task()
        self._close_task = asyncio.create_task(self._do_close())

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(60)
        try:
            Screen.back()
        except Exception as e:
            error('radio_scanner close:', e)

    # ---------------- scanning ----------------
    async def _scan_loop(self):
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
        except Exception as e:
            self.err = str(e)[:26]
            error('radio_scanner wlan:', e)
            self._redraw_data()
            return

        while not self._leaving:
            if self.scanning:
                try:
                    nets = wlan.scan()
                    self.err = None
                    self._apply(nets)
                except Exception as e:
                    self.err = str(e)[:26]
                    error('radio_scanner scan:', e)
                # Обновляем график только раз в UPDATE_EVERY сканов
                self.scan_count += 1
                if self.scan_count >= UPDATE_EVERY:
                    self.scan_count = 0
                    self._redraw_data()
            await asyncio.sleep_ms(SCAN_GAP_MS)

    def _apply(self, nets):
        best = [-100.0] * CH_COUNT
        ap   = 0
        for rec in nets:
            try:
                ch   = rec[2]
                rssi = rec[3]
            except (IndexError, TypeError):
                continue
            if ch < CH_FIRST or ch > CH_LAST:
                continue
            ap += 1
            i = ch - CH_FIRST
            if rssi > best[i]:
                best[i] = rssi
        self.ap_count = ap

        for i in range(CH_COUNT):
            lv = _level(best[i])
            self.levels[i] = lv
            self.best_rssi[i] = best[i]
            p = self.peaks[i] - PEAK_DECAY
            self.peaks[i] = lv if lv > p else (0.0 if p < 0 else p)

    # ---------------- drawing ----------------
    def _draw_static(self):
        self.wri.set_textpos(ssd, TITLE_Y, TITLE_X)
        self.wri.printstring(TITLE_TEXT)
        self.wri_dim.set_textpos(ssd, TITLE_Y + 12, TITLE_X)
        self.wri_dim.printstring(SUB_TEXT)

        # рамка графика
        ssd.rect(GX, GY, GW, GH, DIM)

        # горизонтальная сетка
        for k in (1, 2, 3):
            y = GY + GH * k // 4
            ssd.hline(GX + 1, y, GW - 2, PANEL)

        # подписи каналов 1,3,5,7,9,11,13
        for ch in range(1, 14, 2):
            i = ch - CH_FIRST
            self.wri_dim.set_textpos(ssd, GBASE + 4,
                                     GX + 2 + i * STEP)
            self.wri_dim.printstring(str(ch))

        # нижние подписи диапазона
        self.wri_dim.set_textpos(ssd, GBASE + 16, GX + 2)
        self.wri_dim.printstring('2412 MHz')
        self.wri_dim.set_textpos(ssd, GBASE + 16, GX + GW - 56)
        self.wri_dim.printstring('2472 MHz')

    def _redraw_data(self):
        # очищаем внутреннюю область графика
        ssd.fill_rect(GX + 1, GY + 1, GW - 2, GH - 2, BLACK)

        for i in range(CH_COUNT):
            lv = self.levels[i]
            bx = GX + 2 + i * STEP
            bar_h = int(lv * (GH - 3) / 100.0)
            if bar_h > 0:
                col = GREEN if lv < 55 else (AMBER if lv < 80 else RED)
                ssd.fill_rect(bx, GBASE - 1 - bar_h, BAR_W, bar_h, col)

            # маркер удержания пика
            pk = self.peaks[i]
            if pk > 1:
                py = GBASE - 1 - int(pk * (GH - 3) / 100.0)
                if py < GY + 1:
                    py = GY + 1
                ssd.hline(bx, py, BAR_W, WHITE)

        # строка состояния под графиком
        self.wri.set_textpos(ssd, GBASE + 26, GX + 2)
        self.wri.printstring(' ' * 24)          # стираем старую строку
        self.wri.set_textpos(ssd, GBASE + 26, GX + 2)
        if self.err:
            self.wri.printstring('ERR ' + self.err)
        else:
            # самый загруженный канал
            bi = 0
            for i in range(1, CH_COUNT):
                if self.levels[i] > self.levels[bi]:
                    bi = i
            if self.levels[bi] > 0:
                self.wri.printstring('PK ch{} {}dBm'.format(
                    bi + CH_FIRST, int(self.best_rssi[bi])))
            else:
                self.wri.printstring('PK --')

        # вторая строка: количество AP
        self.wri_dim.set_textpos(ssd, GBASE + 36, GX + 2)
        self.wri_dim.printstring('APs {}  sweep {}ms'.format(
            self.ap_count, SCAN_GAP_MS))


AppScreen = RadioScannerScreen
