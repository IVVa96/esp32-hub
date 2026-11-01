# ======================================================================
# ble/config.py — настройки BLE-сканера
# ======================================================================
from config import _sx


BLE_SCAN_MS          = 4000
BLE_SCAN_PAUSE_MS    = 500
BLE_CONNECT_TIMEOUT  = 8000
BLE_MAX_DEVICES      = 20
BLE_RADIO_SETTLE_MS  = 400

BLE_NAME_W     = _sx(55)
BLE_ADDR_W     = _sx(100)
BLE_RSSI_NUM_W = _sx(38)