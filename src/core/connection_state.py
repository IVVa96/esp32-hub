# ======================================================================
# connection_state.py — общее состояние WiFi/BLE для status_bar
# ======================================================================
class ConnectionState:
    def __init__(self):
        self.wifi_connected = False
        self.wifi_rssi      = None
        self.ble_connected  = False
        self.ble_rssi       = None

    def clear_wifi(self):
        self.wifi_connected = False
        self.wifi_rssi      = None

    def clear_ble(self):
        self.ble_connected  = False
        self.ble_rssi       = None

    def clear(self):
        self.clear_wifi()
        self.clear_ble()


conn_state = ConnectionState()