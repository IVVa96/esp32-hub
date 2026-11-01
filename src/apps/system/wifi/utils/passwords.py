# ======================================================================
# passwords.py — JSON-хранилище WiFi-паролей
# ======================================================================
import json
import os
from apps.system.wifi.config import WIFI_PASSWORDS_FILE

_cache = None


def _ensure_dir():
    d = WIFI_PASSWORDS_FILE.rsplit('/', 1)[0] if '/' in WIFI_PASSWORDS_FILE else ''
    if not d:
        return True
    try:
        os.stat(d)
        return True
    except OSError:
        pass
    cur = ''
    for p in d.split('/'):
        if not p:
            continue
        cur = p if not cur else cur + '/' + p
        try:
            os.mkdir(cur)
        except OSError:
            pass
    try:
        os.stat(d)
        return True
    except OSError:
        return False


def load_passwords():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(WIFI_PASSWORDS_FILE, 'r') as f:
            data = json.load(f)
        _cache = data if isinstance(data, dict) else {}
    except Exception:
        _cache = {}
    return _cache


def get_password(ssid):
    return load_passwords().get(ssid)


def save_password(ssid, password):
    global _cache
    if not _ensure_dir():
        return False
    pwds = dict(load_passwords())
    pwds[ssid] = password
    try:
        with open(WIFI_PASSWORDS_FILE, 'w') as f:
            json.dump(pwds, f)
        _cache = pwds
        return True
    except Exception as e:
        print("save_password EXC:", e)
        return False


def delete_password(ssid):
    global _cache
    pwds = dict(load_passwords())
    if ssid not in pwds:
        return False
    del pwds[ssid]
    try:
        with open(WIFI_PASSWORDS_FILE, 'w') as f:
            json.dump(pwds, f)
        _cache = pwds
        return True
    except Exception:
        return False