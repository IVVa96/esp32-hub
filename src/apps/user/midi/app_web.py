# ======================================================================
# app_web.py — веб-версия MIDI: экран-подсказка на устройстве
#
# Браузерная часть живёт в utils/index.html и общается с платой через
# /api/midi (см. apps/user/midi/utils/engine.py).
# ======================================================================
import asyncio

from gui.core.ugui import Screen
from gui.core.colors import BLACK, WHITE, AMBER, DIM

from config import SCREEN_W
from core.ui import make_writer, redraw_status_bar, wait_release_all, return_to
from core.logger import error
from core.pixel_ui import PixelClose, header, footer, screen_bg, text, fill, frame, MARGIN


TITLE = 'MIDI'
PAGE = 'utils/index.html'
# Веб-версия вытесняет classic-интерфейс: экран гаснет, вывод прекращается.
# Двигатель MIDI при этом продолжает работать — его запускает engine.start().
DUAL_MODE = False


class WebScreen(Screen):
    return_screen = None

    def __init__(self):
        Screen.__init__(self)
        self.wri = make_writer()
        self._alive = True
        self._drawn = False
        self._timer = None
        self._key = None
        self._mode = '-'
        self._preset = '-'
        self._active = 0
        self._url = '-'
        self.cb = PixelClose(self.wri, 20, SCREEN_W - 36, self._on_close)

    # ------------------------------------------------------------------
    # Панель статуса
    # ------------------------------------------------------------------
    def _read_state(self):
        try:
            from apps.user.midi.app import MidiScreen
            mode = 'BLE' if MidiScreen.mode == 'ble' else 'USB'
            cfg = MidiScreen._cfg
            active = 0
            for pin, c in cfg.items():
                if c.get('type') in ('Btn/Sw', 'Virt_sw', 'Pot', 'Encoder'):
                    active += 1
            preset = MidiScreen._current_preset or 'default'
            dirty = '*' if MidiScreen._dirty else ''
            return mode, preset + dirty, active
        except Exception:
            return '-', '-', 0

    def _url_text(self):
        try:
            from apps.system.explorer.utils import server
            st = server.STATUS
            host = st.get('host') or st.get('ip') or ''
            if host:
                return 'http://{}/apps/midi/'.format(host)
        except Exception:
            pass
        return '-'

    def _update_status(self):
        if not self._drawn:
            return
        mode, preset, active = self._read_state()
        url = self._url_text()
        key = (mode, preset, active, url)
        if key == self._key:
            return
        self._key = key
        self._mode = mode
        self._preset = preset
        self._active = active
        self._url = url
        self._draw_panel()

    def _panel_line(self, y, label, value, color):
        text(label, 24, y, DIM)
        text(str(value)[:19], 64, y, color)

    def _draw_panel(self):
        x, y, w, h = MARGIN, 96, SCREEN_W - 2 * MARGIN, 110
        fill(x, y, w, h, BLACK)
        frame(x, y, w, h, DIM)
        text('STATUS', x + 8, y + 6, DIM)
        self._panel_line(y + 24, 'MODE', self._mode, AMBER)
        self._panel_line(y + 42, 'PRESET', self._preset, WHITE)
        self._panel_line(y + 60, 'ACTIVE', '{} PINS'.format(self._active), WHITE)
        self._panel_line(y + 78, 'URL', 'OPEN IN BROWSER', DIM)

    def _draw_all(self):
        screen_bg()
        header('MIDI WEB', '// EDIT IN BROWSER')
        footer('MIDI', 'LIVE', 'X', 'CLOSE')
        self._key = None
        self._update_status()
        self.cb.show()

    def after_open(self):
        self._alive = True
        self._drawn = True
        try:
            from apps.user.midi.utils import engine
            engine.start()
        except Exception as e:
            error('midi web start:', e)
        self._draw_all()
        redraw_status_bar()
        try:
            self._timer = asyncio.create_task(self._timer_loop())
        except Exception as e:
            error('midi web timer:', e)

    def on_hide(self):
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
        ret = WebScreen.return_screen
        WebScreen.return_screen = None
        if ret is None:
            ret = self.parent
        return_to(self, ret)
