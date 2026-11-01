# ======================================================================
# mounts.py — монтирование SD-карты в /sd
# ======================================================================
import os
import machine

from apps.system.explorer.config import (
    SD_ENABLED, SD_SPI_PINS, SD_FREQ, SD_ROOT,
)

# Пины SDMMC slot 0 по умолчанию на ESP32-S3. Они конфликтуют с дисплеем
# и кнопками этой платы, поэтому SDMMC-режим не используется никогда:
# только SPI-модуль на явно заданных свободных пинах.
_SDMMC_CONFLICT = (14, 15, 2, 4, 12, 13)

_sd = None
_mounted = False
_last_error = None


def _ensure_dir():
    try:
        os.stat(SD_ROOT)
    except OSError:
        try:
            os.mkdir(SD_ROOT)
        except OSError:
            pass


def _cleanup_dir():
    """Убрать пустую /sd, если карта не смонтировалась (иначе она видна
    как обычная папка во внутренней ФС и в проводниках)."""
    try:
        os.rmdir(SD_ROOT)
    except Exception:
        pass


def mounted():
    if not _mounted:
        return False
    try:
        os.statvfs(SD_ROOT)
        return True
    except OSError:
        return False


def last_error():
    return _last_error


def mount_sd(force=False):
    """Смонтировать SD в /sd. Возвращает True при успехе.

    Без карты просто возвращает False — приложение продолжает работать
    только с внутренней файловой системой.
    """
    global _sd, _mounted, _last_error

    if not SD_ENABLED:
        _last_error = 'disabled'
        return False
    if not SD_SPI_PINS:
        _last_error = 'set SD_SPI_PINS'
        return False
    if mounted() and not force:
        return True
    if _sd is not None:
        return _mounted

    _ensure_dir()
    try:
        import vfs
        sck, mosi, miso, cs = SD_SPI_PINS
        # slot=2 — SPI-режим (slot 0/1 — SDMMC с занятыми пинами).
        _sd = machine.SDCard(
            slot=2,
            sck=machine.Pin(sck), mosi=machine.Pin(mosi),
            miso=machine.Pin(miso), cs=machine.Pin(cs),
            freq=SD_FREQ,
        )
    except Exception as e:
        _last_error = 'init: {}'.format(e)
        _sd = None
        _cleanup_dir()
        return False

    try:
        vfs.mount(_sd, SD_ROOT)
        _mounted = True
        _last_error = None
        return True
    except Exception as e:
        _last_error = 'mount: {}'.format(e)
        try:
            _sd = None
        except Exception:
            pass
        _mounted = False
        _cleanup_dir()
        return False


def umount_sd():
    global _sd, _mounted
    if _sd is None:
        return
    try:
        os.umount(SD_ROOT)
    except Exception:
        pass
    _sd = None
    _mounted = False
