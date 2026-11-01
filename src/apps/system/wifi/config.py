# ======================================================================
# wifi/config.py — настройки WiFi-сканера
# ======================================================================
from config import _sx, _sy


WIFI_PASSWORDS_FILE = 'apps/system/wifi/utils/wifi_passwords.json'

WIFI_SCAN_INTERVAL_MS   = 8000
WIFI_CONNECT_TIMEOUT_MS = 15000
WIFI_MAX_NETWORKS       = 20
WIFI_SAVED_MARKER       = 'saved'

WIFI_RSSI_NUM_W = _sx(32)
WIFI_SEC_W      = _sx(24)

PW_Y_TITLE = _sy(2)
PW_Y_SSID  = _sy(16)
PW_Y_INPUT = _sy(32)
PW_Y_HINT  = _sy(50)
PW_KB_Y    = _sy(66)