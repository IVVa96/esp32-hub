# ======================================================================
# ble_midi.py — BLE-MIDI (периферия, aioble)
# ======================================================================
# ESP32 поднимает BLE-MIDI GATT-сервис и рекламируется как 'ESP32-MIDI'.
# Компьютер/телефон подключается к нему как central, после чего контроллер
# отправляет CC-сообщения BLE-нотификациями.
#
# Отправка идёт из фоновой задачи hw._midi_flush_loop(), поэтому notify()
# никогда не вызывается из ISR.
# ======================================================================
import asyncio
import time

from core.logger import error

try:
    import bluetooth
    import aioble

    BLE_MIDI_SERVICE_UUID = bluetooth.UUID(
        '03B80E5A-EDE8-4B33-A751-6CE34EC4C700')
    BLE_MIDI_CHAR_UUID = bluetooth.UUID(
        '7772E5DB-3868-11E2-A1A9-F2A9F7E5A9B7')
    _AVAILABLE = True
except Exception as _e:
    BLE_MIDI_SERVICE_UUID = None
    BLE_MIDI_CHAR_UUID = None
    _AVAILABLE = False
    error('ble_midi import:', _e)


BLE_NAME = 'ESP32-MIDI'
ADV_INTERVAL_US = 500_000

_connection = None
_char = None
_task = None
_started = False
_registered = False


def available():
    return _AVAILABLE


def is_connected():
    conn = _connection
    if conn is None:
        return False
    try:
        return conn.is_connected()
    except Exception:
        return False


def _packet(channel, control, value):
    """BLE-MIDI: заголовок (старшие 6 бит времени) + младшие 7 бит + CC."""
    ts = time.ticks_ms() & 0x1FFF
    hdr = 0x80 | ((ts >> 7) & 0x3F)
    return bytes((hdr, ts & 0x7F,
                  0xB0 | (channel & 0x0F),
                  control & 0x7F,
                  value & 0x7F))


def send_cc(channel, control, value):
    """Отправить CC через BLE. Безопасно вызывать без подключения."""
    conn = _connection
    char = _char
    if conn is None or char is None:
        return
    try:
        if not conn.is_connected():
            return
        char.notify(conn, _packet(channel, control, value))
    except Exception:
        # Обрыв связи: следующие пакеты просто не уйдут.
        pass


def _register():
    global _char, _registered
    if _registered:
        return True
    service = aioble.Service(BLE_MIDI_SERVICE_UUID)
    _char = aioble.Characteristic(
        service, BLE_MIDI_CHAR_UUID,
        read=True, write=True, write_no_response=True, notify=True,
    )
    aioble.register_services(service)
    _registered = True
    return True


def _enable_bonding():
    """Разрешить bonding: Windows/телефон сохраняют ключи, связь стабильнее."""
    try:
        aioble.config(bond=True)
    except Exception as e:
        error('ble bond cfg:', e)


async def _run():
    global _connection
    try:
        _enable_bonding()
        _register()
    except Exception as e:
        error('ble register:', e)
        return

    while _started:
        conn = None
        try:
            conn = await aioble.advertise(
                ADV_INTERVAL_US,
                name=BLE_NAME,
                services=[BLE_MIDI_SERVICE_UUID],
            )
        except asyncio.CancelledError:
            return
        except Exception as e:
            error('ble advertise:', e)
            await asyncio.sleep_ms(1000)
            continue

        _connection = conn
        try:
            await conn.disconnected()
        except asyncio.CancelledError:
            return
        except Exception:
            pass
        _connection = None
        await asyncio.sleep_ms(200)


def start():
    """Запустить рекламу и ожидание подключения. Возвращает True при успехе."""
    global _task, _started
    if not _AVAILABLE:
        return False
    if _started and _task is not None and not _task.done():
        return True
    _started = True
    try:
        _task = asyncio.create_task(_run())
    except Exception as e:
        error('ble start:', e)
        _started = False
        return False
    return True


def stop():
    """Прекратить рекламу и отключить central."""
    global _started, _task, _connection, _char, _registered
    _started = False
    conn = _connection
    _connection = None
    if conn is not None:
        try:
            asyncio.create_task(conn.disconnect())
        except Exception:
            pass
    t = _task
    _task = None
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass
    # aioble.stop() гасит BLE и обнуляет таблицу GATT: при следующем
    # запуске характеристику нужно зарегистрировать заново.
    _char = None
    _registered = False
