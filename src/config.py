# ======================================================================
# config.py — системные настройки (общие для всех приложений)
# ======================================================================
import gui.fonts.arial10 as arial10
from gui.core.colors import *


# ---- Геометрия экрана ----
# Все значения — фиксированные пиксели под панель ILI9341 320x240.
# Функции масштабирования (_sx/_sy/_sm) удалены: при масштабе 1:1 они
# лишь тратили время ESP32 на вызовы и деления. Если панель сменится,
# значения ниже правятся напрямую, без пересчёта.
SCREEN_W = 320
SCREEN_H = 240


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
STATUS_BAR_H                  = 14
STATUS_BAR_BG                 = BLACK
STATUS_BAR_FG                 = AMBER
STATUS_BAR_CLOCK_COLOR        = AMBER
STATUS_BAR_SEP                = DIM
STATUS_BAR_WIFI_NO_CONN_COLOR = DIM
STATUS_BAR_BLE_NO_CONN_COLOR  = DIM
STATUS_BAR_RIGHT_MARGIN       = 2
STATUS_BAR_WIFI_RSSI_MS       = 10000

SB_CLOCK_X   = 2
SB_CLOCK_Y   = 3
SB_ITEMS_GAP = 6

# Все экранные отступы ниже считаются от _TOP: если статус-бар выключен,
# контент сдвигается к верхнему краю, если включён — на его высоту.
_TOP = STATUS_BAR_H if STATUS_BAR_ENABLED else 0


# ---- Стиль экранов ----
TITLE_Y        = 8 + _TOP
TITLE_X        = 2
STATUS_LBL_GAP = 8

LB_Y            = 28 + _TOP
LB_X            = 10
LB_WIDTH        = SCREEN_W - 2 * LB_X
LB_DLINES       = (SCREEN_H - LB_Y - 24) // 13   # строк списка (при 240 -> 13)
LB_BORDER_COLOR = DIM

CS_Y_HEADER     = 2  + _TOP
CS_Y_NAME       = 14 + _TOP
CS_Y_ADDR       = 26 + _TOP
CS_Y_STATUS     = 50 + _TOP
CS_MARGIN       = 4
LINE_H          = 12
TEXT_W          = SCREEN_W - 2 * CS_MARGIN


# ---- Кнопка закрытия ----
CLOSE_BTN_W     = 20
CLOSE_BTN_H     = 18
CLOSE_BTN_RIGHT = 4
CLOSE_BTN_X     = SCREEN_W - CLOSE_BTN_RIGHT - CLOSE_BTN_W
CLOSE_BTN_Y     = _TOP + 4


# ---- Клавиатура ----
KB_CELL_W = 30
KB_CELL_H = 21
KB_COLS   = 10
KB_WIDTH  = KB_COLS * KB_CELL_W
KB_X      = (SCREEN_W - KB_WIDTH) // 2


# ---- Нижняя подсказка ----
FOOTER_Y = SCREEN_H - 34


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
