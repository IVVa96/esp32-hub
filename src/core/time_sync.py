# ======================================================================
# time_sync.py — NTP-синхронизация, единый источник времени
# ======================================================================
import asyncio
import time
import ntptime
import network

from config import TZ_OFFSET_HOURS, NTP_HOST
from core.logger import info, error


_synced_once = False


def _tz_offset_sec():
    return int(TZ_OFFSET_HOURS * 3600)


async def sync_ntp_once():
    global _synced_once

    try:
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return False
    except Exception:
        return False

    ntptime.host = NTP_HOST

    try:
        ntptime.settime()
    except Exception as e:
        error("NTP sync:", type(e).__name__, e)
        return False

    utc = time.time()
    local = utc + _tz_offset_sec()
    try:
        import machine
        tm = time.gmtime(local)
        machine.RTC().datetime(
            (tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0)
        )
    except Exception as e:
        error("RTC set:", type(e).__name__, e)

    _synced_once = True
    info("NTP OK, local:", time.localtime())
    return True


async def sync_ntp_retry(tries=3, delay_ms=1500):
    """Несколько попыток синхронизации: сеть может подняться не сразу."""
    for i in range(max(1, tries)):
        if await sync_ntp_once():
            return True
        if i + 1 < tries:
            await asyncio.sleep_ms(delay_ms)
    return False


def is_synced():
    return _synced_once


def localtime():
    """Единый источник времени для всего проекта.
    До NTP RTC = uptime (эпоха 2000-01-01). После NTP = локальное
    время (UTC + TZ). Статус-бар и часы читают эту функцию."""
    return time.localtime()


def now_hm():
    t = localtime()
    return t[3], t[4]