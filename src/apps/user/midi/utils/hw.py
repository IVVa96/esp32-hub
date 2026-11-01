# ======================================================================
# hw.py — USB-MIDI и GPIO-компоненты
# ======================================================================
# Классы:
#   ButtonInput   — «Btn/Sw», моментальная кнопка (127 при нажатии, 0 при отпускании)
#   VirtSwInput   — «Virt_sw», тумблер: счётчик нажатий (counter = (counter+1) % 2)
#                   реализован через ОПРОС в фоновой задаче, а не через IRQ.
#   PotInput      — потенциометр (ADC 0..127, абсолютный)
#   EncoderInput  — квадратурный энкодер (относительный CC: 1 / 127)
#
# При создании Btn/Sw и Virt_sw отправляют исходное состояние в DAW,
# чтобы при смене типа не оставалось «зависшее» CC от предыдущего компонента.
# ======================================================================
import asyncio
import time
from machine import Pin, ADC

from apps.user.midi.config import (
    MIDI_ENCODER_INC, MIDI_ENCODER_DEC, MIDI_POLL_MS,
)
from apps.user.midi.utils import ble_midi
from core.logger import error


# ======================================================================
# USB-MIDI
# ======================================================================
_usb_midi    = None
_MIDI_OK     = False
_midi_inited = False


def init_usb_midi():
    global _usb_midi, _MIDI_OK, _midi_inited
    if _midi_inited:
        return
    _midi_inited = True
    try:
        import usb.device
        from usb.device.midi import MIDIInterface
        _usb_midi = MIDIInterface()
        usb.device.get().init(_usb_midi, builtin_driver=True)
        _MIDI_OK = True
        print("USB-MIDI initialized")
    except Exception as e:
        print("USB-MIDI init failed:", e)
        _usb_midi = None
        _MIDI_OK  = False


_midi_queue = []
_flush_task = None
_transport   = 'wire'   # 'wire' (USB-MIDI) или 'ble' (BLE-MIDI)


def send_cc(channel, control, value):
    """channel — 0..15 (MIDI-канал 1..16, 0-based).

    Всегда кладём в очередь: фактическую отправку делает flush-задача,
    поэтому BLE-notify не вызывается из ISR.
    """
    if len(_midi_queue) < 32:
        try:
            _midi_queue.append(
                (channel & 0x0F, control & 0x7F, value & 0x7F))
        except Exception:
            pass


async def _midi_flush_loop():
    while True:
        while _midi_queue:
            ch, cc, val = _midi_queue.pop(0)
            if _transport == 'ble':
                try:
                    ble_midi.send_cc(ch, cc, val)
                except Exception:
                    pass
            elif _MIDI_OK and _usb_midi is not None:
                try:
                    _usb_midi.control_change(ch, cc, val)
                except Exception:
                    pass
        await asyncio.sleep_ms(5)


def _ensure_flush():
    global _flush_task
    if _flush_task is None or _flush_task.done():
        try:
            _flush_task = asyncio.create_task(_midi_flush_loop())
        except Exception:
            pass


def start(mode='wire'):
    """mode='wire' — USB-MIDI, mode='ble' — BLE-MIDI."""
    global _transport
    _transport = 'ble' if mode == 'ble' else 'wire'
    if _transport == 'wire':
        init_usb_midi()
    _ensure_flush()


# ======================================================================
# Btn/Sw — моментальная кнопка
# Нажал: CC = 127, отпустил: CC = 0
# При создании сразу синхронизирует DAW с фактическим состоянием пина.
# ======================================================================
class ButtonInput:
    def __init__(self, pin_num, cc, channel=0):
        self.cc      = cc
        self.channel = channel
        self._pin    = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        try:
            self._last = self._pin.value()
        except Exception:
            self._last = 1
        # Синхронизация при старте: 0 если не нажата, 127 если нажата.
        send_cc(self.channel, self.cc, 0 if self._last else 127)
        self._pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                      handler=self._isr)

    def _isr(self, pin):
        v = pin.value()
        if v != self._last:
            self._last = v
            send_cc(self.channel, self.cc, 0 if v else 127)

    def stop(self):
        try:
            self._pin.irq(handler=None)
        except Exception:
            pass


# ======================================================================
# Virt_sw — виртуальный тумблер
# Счётчик нажатий:
#   counter = (counter + 1) % 2
#   counter = 0 → CC = 0   (выкл)
#   counter = 1 → CC = 127 (вкл)
#
# Реализация: фоновая задача опрашивает пин каждые POLL_MS.
# Нажатие детектируется по переходу 1 → 0.
# Дебаунс: нажатия ближе DEBOUNCE_MS игнорируются.
#
# При создании отправляет CC = 0 (counter изначально = 0),
# чтобы не унаследовать «зависшее» 127 от предыдущего компонента.
# ======================================================================
class VirtSwInput:
    _POLL_MS     = 10   # опрос пина, мс
    _DEBOUNCE_MS = 40   # минимальный интервал между нажатиями, мс

    def __init__(self, pin_num, cc, channel=0):
        self.cc      = cc
        self.channel = channel
        self._pin    = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self._last_v = 1
        self._last_press_t = 0
        self._counter = 0
        # Синхронизация при старте: тумблер начинает с выкл.
        send_cc(self.channel, self.cc, 0)
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            try:
                v = self._pin.value()
                # Фронт 1 → 0 = нажатие
                if v == 0 and self._last_v == 1:
                    now = time.ticks_ms()
                    if (self._last_press_t == 0) or \
                            (time.ticks_diff(now, self._last_press_t)
                             >= self._DEBOUNCE_MS):
                        self._last_press_t = now
                        self._counter = (self._counter + 1) % 2
                        send_cc(self.channel, self.cc,
                                127 if self._counter else 0)
                self._last_v = v
            except Exception as e:
                error("vsw loop:", e)
            await asyncio.sleep_ms(self._POLL_MS)

    def stop(self):
        t = self._task
        if t:
            try:
                t.cancel()
            except Exception:
                pass


# ======================================================================
# Pot — потенциометр (ADC 0..127, абсолютный)
# ======================================================================
class PotInput:
    def __init__(self, pin_num, cc, channel=0):
        self.cc      = cc
        self.channel = channel
        self._adc    = ADC(Pin(pin_num))
        try:
            self._adc.atten(ADC.ATTN_11DB)
        except Exception:
            pass
        self._last = -1
        self._buf  = []
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            try:
                raw = self._adc.read()
                self._buf.append(raw)
                if len(self._buf) > 4:
                    self._buf.pop(0)
                avg = sum(self._buf) // len(self._buf)
                val = (avg * 127) // 4095
                if val != self._last:
                    self._last = val
                    send_cc(self.channel, self.cc, val)
            except Exception:
                pass
            await asyncio.sleep_ms(MIDI_POLL_MS)

    def stop(self):
        t = self._task
        if t:
            try:
                t.cancel()
            except Exception:
                pass


# ======================================================================
# Encoder — квадратурный энкодер (относительный CC: 1 / 127)
# ======================================================================
class EncoderInput:
    _QUAD = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)

    def __init__(self, pin_a, pin_b, cc, channel=0):
        self.cc      = cc
        self.channel = channel
        self._pos    = 0
        self._a = Pin(pin_a, Pin.IN, Pin.PULL_UP)
        self._b = Pin(pin_b, Pin.IN, Pin.PULL_UP)
        self._prev_ab = self._read_ab()
        self._a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                    handler=self._isr)
        self._b.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                    handler=self._isr)

    def _read_ab(self):
        return (self._b.value() << 1) | self._a.value()

    def _isr(self, pin):
        now = self._read_ab()
        idx = ((self._prev_ab << 2) | now) & 0x0F
        step = self._QUAD[idx]
        self._prev_ab = now
        if step == 0:
            return
        self._pos += step
        if abs(self._pos) >= 4:
            if self._pos > 0:
                send_cc(self.channel, self.cc, MIDI_ENCODER_INC)
            else:
                send_cc(self.channel, self.cc, MIDI_ENCODER_DEC)
            self._pos = 0

    def stop(self):
        try:
            self._a.irq(handler=None)
            self._b.irq(handler=None)
        except Exception:
            pass