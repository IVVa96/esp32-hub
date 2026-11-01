# ======================================================================
# app.py — заглушка приложения в Classic UI (3)
# ======================================================================
import hardware_setup

from gui.core.ugui import Screen
from gui.core.colors import WHITE, AMBER, DIM

from config import SCREEN_W
from core.ui import make_writer, redraw_status_bar
from core.pixel_ui import (
    header, footer, screen_bg, big_c, text_c, PixelClose,
)

TITLE = 'DEMO 3'
SUBTITLE = '// PLACEHOLDER'


class AppScreen(Screen):
    def __init__(self):
        Screen.__init__(self)
        self.wri = make_writer()
        screen_bg()
        header(TITLE, SUBTITLE)
        big_c('SOON', 118, 3, AMBER)
        text_c('THIS APP IS A STUB', 178, DIM)
        text_c('CLOSE TO GO BACK', 192, DIM)
        self.cb = PixelClose(self.wri, 20, SCREEN_W - 36, self._on_close)
        footer('CLOSE', 'BACK', 'SEL', 'OK')
        redraw_status_bar()

    def _on_close(self):
        Screen.back()
