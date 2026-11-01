# ======================================================================
# power.py — глубокий сон, пробуждение кнопкой BOOT и восстановление Wi-Fi
#
# В deep sleep RTC-домен ESP32 остаётся запитанным, поэтому время
# продолжает идти. Wi-Fi выключается, а при пробуждении main.py
# поднимает последнюю сохранённую сеть.
# ======================================================================
import json

from config import POWER_STATE_FILE, POWER_WAKE_PIN
from core.logger import info, error


_cache = None


def _load():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(POWER_STATE_FILE, 'r') as f:
            data = json.load(f)
        _cache = data if isinstance(data, dict) else {}
    except Exception:
        _cache = {}
    return _cache


def _store(data):
    global _cache
    _cache = data
    try:
        with open(POWER_STATE_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        error('power save:', type(e).__name__, e)
        return False


# ----------------------------------------------------------------------
# Последняя сеть
# ----------------------------------------------------------------------
def remember_wifi(ssid, password=None):
    if not ssid:
        return False
    data = _load()
    old = data.get('wifi') or {}
    if not password and old.get('ssid') == ssid:
        password = old.get('password') or ''
    wifi = {'ssid': str(ssid), 'password': password or ''}
    if old == wifi:
        return True
    data = dict(data)
    data['wifi'] = wifi
    return _store(data)


def last_wifi():
    wifi = _load().get('wifi')
    if not isinstance(wifi, dict) or not wifi.get('ssid'):
        return None
    return {'ssid': wifi.get('ssid'), 'password': wifi.get('password') or ''}


def capture_current():
    """Запомнить сеть, к которой плата подключена прямо сейчас."""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return None
        try:
            ssid = wlan.config('essid') or ''
        except Exception:
            ssid = ''
        if isinstance(ssid, bytes):
            try:
                ssid = ssid.decode('utf-8')
            except Exception:
                ssid = ''
        if not ssid:
            return None
        password = ''
        try:
            from apps.system.wifi.utils import passwords as wp
            password = wp.get_password(ssid) or ''
        except Exception:
            pass
        if not password:
            try:
                from apps.system.wifi.app import wifi_state
                if wifi_state.ssid == ssid:
                    password = wifi_state.password or ''
            except Exception:
                pass
        remember_wifi(ssid, password)
        return ssid
    except Exception as e:
        error('power capture:', type(e).__name__, e)
        return None


# ----------------------------------------------------------------------
# Последний режим веб-сервера
# ----------------------------------------------------------------------
def remember_web(mode, ssid, ip, running):
    data = _load()
    web = {
        'mode': mode or '',
        'ssid': ssid or '',
        'ip': ip or '',
        'running': bool(running),
    }
    if data.get('web') == web:
        return True
    data = dict(data)
    data['web'] = web
    return _store(data)


def last_web():
    web = _load().get('web')
    if not isinstance(web, dict):
        return None
    return web


# ----------------------------------------------------------------------
# Сон / пробуждение
# ----------------------------------------------------------------------
def configure_wake():
    """Разбудить плату коротким нажатием BOOT (GPIO0, активный низкий)."""
    try:
        import esp32
        import machine
        pin = machine.Pin(POWER_WAKE_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        esp32.wake_on_ext0(pin, 0)
        info('power: wake on BOOT GPIO{}'.format(POWER_WAKE_PIN))
        return True
    except Exception as e:
        error('power wake:', type(e).__name__, e)
        return False


def woke_from_sleep():
    try:
        import machine
        return machine.reset_cause() == machine.DEEPSLEEP_RESET
    except Exception:
        return False


def sleep_now():
    configure_wake()
    try:
        import machine
        machine.deepsleep()
    except Exception as e:
        error('power deepsleep:', type(e).__name__, e)


async def shutdown():
    """Анимация выключения + глубокий сон; время сохраняется в RTC."""
    from core import shutdown as shutdown_anim
    await shutdown_anim.run()
