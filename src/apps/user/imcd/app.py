TITLE = 'IMCD P2P'

import hardware_setup
from gui.core.ugui import Screen
from config import SCREEN_W
from core.ui import make_writer, redraw_status_bar, return_to
from core.pixel_ui import header, footer, screen_bg, PixelClose, text
from apps.user.imcd import config

class AppScreen(Screen):
    def __init__(self):
        Screen.__init__(self)
        self.wri = make_writer()
        self.cb = PixelClose(self.wri, 20, SCREEN_W - 36, self._on_close)

    def after_open(self):
        # После открытия экран очищается, поэтому статику рисуем здесь.
        screen_bg()
        header(TITLE, 'P2P Radio')
        footer('CLOSE', 'MODE', 'CHAT', 'SEND')
        text(f"Mode: {config.DEFAULT_MODE.upper()}", 20, 60)
        text("Status: Initializing...", 20, 80)
        text("SPI3 & Radios: Pending Driver", 20, 100)
        redraw_status_bar()
        self.cb.show()

    def on_hide(self):
        pass

    def _on_close(self):
        Screen.back()
