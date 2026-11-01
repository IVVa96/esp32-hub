# ======================================================================
# config.py — системные настройки (общие для всех приложений)
# ======================================================================
import gui.fonts.arial10 as arial10
from gui.core.colors import *


# ---- Геометрия экрана ----
SCREEN_W = 240
SCREEN_H = 320
_REF_W   = 240
_REF_H   = 320


def _sx(v):
    return max(1, v * SCREEN_W // _REF_W)


def _sy(v):
    return max(1, v * SCREEN_H // _REF_H)


def _sm(v):
    return min(_sx(v), _sy(v))


def _dlines(px_h, entry_px=13):
    return max(3, px_h // entry_px)


# ---- Отладка ----
DEBUG_LEVEL = 3
LOG_NONE     = 0
LOG_ERROR    = 1
LOG_WARN     = 2
LOG_INFO     = 3
LOG_VERBOSE  = 4


# ---- Шрифт и цвета ----
FONT         = arial10
TEXT_COLOR   = AMBER
BG_COLOR     = BLACK
ACCENT_COLOR = AMBER
LINE_COLOR   = DIM
PANEL_COLOR  = PANEL


# ---- Клавиатура ----
KEY_BG       = BLACK
KEY_FG       = AMBER
KEY_BORDER   = DIM
HIGHLIGHT_BG = AMBER
HIGHLIGHT_FG = BLACK


# ---- Status bar ----
STATUS_BAR_ENABLED            = True
STATUS_BAR_H                  = _sy(14)
STATUS_BAR_BG                 = BLACK
STATUS_BAR_FG                 = AMBER
STATUS_BAR_CLOCK_COLOR        = AMBER
STATUS_BAR_SEP                = DIM
STATUS_BAR_WIFI_NO_CONN_COLOR = DIM
STATUS_BAR_BLE_NO_CONN_COLOR  = DIM
STATUS_BAR_RIGHT_MARGIN       = _sx(2)
STATUS_BAR_WIFI_RSSI_MS       = 10000

SB_CLOCK_X   = _sx(2)
SB_CLOCK_Y   = _sy(3)
SB_ITEMS_GAP = _sx(6)

_TOP = STATUS_BAR_H if STATUS_BAR_ENABLED else 0


# ---- Стиль экранов ----
TITLE_Y        = _sy(8) + _TOP
TITLE_X        = _sx(2)
STATUS_LBL_GAP = _sx(8)

LB_Y            = _sy(28) + _TOP
LB_X            = _sx(10)
LB_WIDTH        = SCREEN_W - 2 * LB_X
LB_DLINES       = _dlines(_sy(298))
LB_BORDER_COLOR = DIM

CS_Y_HEADER     = _sy(2)  + _TOP
CS_Y_NAME       = _sy(14) + _TOP
CS_Y_ADDR       = _sy(26) + _TOP
CS_Y_STATUS     = _sy(50) + _TOP
CS_MARGIN       = _sx(4)
LINE_H          = _sy(12)
TEXT_W          = SCREEN_W - 2 * CS_MARGIN


# ---- Кнопка закрытия ----
CLOSE_BTN_W     = _sm(20)
CLOSE_BTN_H     = _sm(18)
CLOSE_BTN_RIGHT = _sx(4)
CLOSE_BTN_X     = SCREEN_W - CLOSE_BTN_RIGHT - CLOSE_BTN_W
CLOSE_BTN_Y     = _TOP + _sy(4)


# ---- Клавиатура ----
KB_CELL_W = _sx(22)
KB_CELL_H = _sy(32)
KB_COLS   = 10
KB_WIDTH  = KB_COLS * KB_CELL_W
KB_X      = (SCREEN_W - KB_WIDTH) // 2


# ---- NTP / время ----
TZ_MODE         = 'manual'
TZ_NAME         = 'Europe/Moscow'
TZ_OFFSET_HOURS = 3
NTP_HOST        = 'pool.ntp.org'


# ---- Fullscreen ----
FULLSCREEN = True


# ---- Shutdown ----
POWER_STATE_FILE   = 'core/power_state.json'
POWER_WAKE_PIN     = 0
SHUTDOWN_TEXT      = 'GOODBYE MY FRIEND'
SHUTDOWN_TEXT_MS   = 2000