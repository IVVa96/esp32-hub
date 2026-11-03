TITLE = 'IMCD P2P'

import hardware_setup
from gui.core.ugui import Screen
from core.ui import make_writer, redraw_status_bar, return_to
from core.pixel_ui import header, footer, screen_bg, PixelClose, text, fill
from apps.user.imcd import config

class AppScreen(Screen):
    def __init__(self):
        Screen.__init__(self)
        self.wri = make_writer()
        screen_bg()
        header(TITLE, 'P2P Radio')
        footer('CLOSE', 'MODE', 'CHAT', 'SEND')
        self.cb = PixelClose(self.wri, 20, 320 - 36, self._on_close)
        
    def after_open(self):
        redraw_status_bar()
        text(self.wri, 20, 60, f"Mode: {config.DEFAULT_MODE.upper()}", 0xFFFF, 0x0000)
        text(self.wri, 20, 85, "Status: Initializing...", 0xFFFF, 0x0000)
        text(self.wri, 20, 110, "SPI3 & Radios: Pending Driver", 0xFFFF, 0x0000)

    def on_hide(self):
        pass

    def _on_close(self):
        Screen.back()
