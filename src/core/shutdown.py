# ======================================================================
# shutdown.py — экран выключения: GOODBYE MY FRIEND по центру
# ======================================================================
import asyncio
import gc
import time

from gui.core.ugui import ssd
from gui.core.colors import WHITE
from config import SHUTDOWN_TEXT, SHUTDOWN_TEXT_MS
from core.logger import info, error
from core import power


def _center_text(text, y, color, gap=1):
    """Вывести текст по центру с небольшим межбуквенным интервалом."""
    try:
        width = len(text) * 8 + max(0, len(text) - 1) * gap
        x = max(0, (ssd.width - width) // 2)
        for ch in text:
            ssd.text(ch, x, y, color)
            x += 8 + gap
    except Exception as e:
        error("center_text:", e)


async def _phase_goodbye():
    info("shutdown: goodbye")
    try:
        ssd.fill(0)
    except Exception:
        pass

    # Маскот над надписью: крупный серый паук с оранжевым крестом.
    try:
        from core import mascot
        mascot.draw_goodbye((ssd.width - mascot.GOODBYE_SIZE) // 2, 94)
    except Exception as e:
        error("mascot:", e)

    _center_text(SHUTDOWN_TEXT, 218, WHITE, 1)
    await asyncio.sleep_ms(SHUTDOWN_TEXT_MS)


def _disable_wifi():
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            wlan.disconnect()
        wlan.active(False)
    except Exception:
        pass
    try:
        import network
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
    except Exception:
        pass


def _disable_backlight():
    try:
        import hardware_setup
        hardware_setup.pled.value(0)
    except Exception:
        pass


async def run():
    info("shutdown: START")
    gc.collect()

    try:
        import core.status_bar as status_bar
        status_bar.stop()
    except Exception as e:
        error("status_bar stop:", e)

    try:
        await asyncio.sleep_ms(100)
    except Exception:
        pass

    try:
        await _phase_goodbye()
    except Exception as e:
        error("animation:", type(e).__name__, e)

    # Сохраняем последнюю сеть и разрешаем пробуждение кнопкой BOOT.
    try:
        power.capture_current()
    except Exception as e:
        error("power capture:", e)
    # Отложенная запись временного пресета MIDI: перед deep sleep сбрасываем.
    try:
        from apps.user.midi.utils import save as midi_save
        midi_save.flush_temp()
    except Exception:
        pass
    _disable_wifi()
    _disable_backlight()
    power.configure_wake()
    info("shutdown: backlight off, entering deepsleep")

    try:
        import machine
        machine.deepsleep()
    except Exception as e:
        error("deepsleep:", e)

    while True:
        try:
            time.sleep_ms(1000)
        except Exception:
            pass
