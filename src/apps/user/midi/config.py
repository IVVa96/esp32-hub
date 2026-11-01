# ======================================================================
# midi_utils/config.py — настройки MIDI-контроллера
# ======================================================================
from config import _sx, _sy, SCREEN_H
from gui.core.colors import RED, YELLOW, CYAN, MAGENTA, BLUE


# ---- Канал и CC по умолчанию ----
MIDI_DEFAULT_CHANNEL = 1
MIDI_CC_GROUP_COLORS = (RED, YELLOW, CYAN, MAGENTA, BLUE)


# ---- Кодировщики (encoder) ----
MIDI_ENCODER_INC = 1
MIDI_ENCODER_DEC = 127


# ---- Частота опроса ADC (потенциометры) ----
MIDI_POLL_MS = 20


# ---- Доступные пины ----
# Исключены: дисплей (3, 9, 10, 11, 12, 13, 14, 46) и кнопки (15, 16, 17, 7, 18).
# ADC1 (безопасно с WiFi): GPIO 1-10.
MIDI_AVAILABLE_PINS = [1, 2, 4, 5, 6, 8, 9, 21, 38, 39, 40, 41, 42, 45, 47, 48]
MIDI_ADC_PINS       = {1, 2, 4, 5, 6, 8, 9}


# ---- Пресеты ----
MIDI_PRESETS_DIR    = 'apps/user/midi/utils/midi_saves'
MIDI_DEFAULT_PRESET = 'default'


# ---- Список пинов ----
MIDI_LB_DLINES      = 5     # видимых строк в списке
MIDI_LB_DLINES_REF  = 11    # эталон для сдвига списка вниз
MIDI_LB_EXTRA       = _sy(8)  # дополнительный отступ под subtitle


# ---- Панель редактирования (под списком) ----
PANEL_TOP_GAP      = _sy(16)

PANEL_TYPE_X       = _sx(2)
PANEL_TYPE_LBL_OFF = _sy(14)
PANEL_TYPE_W       = _sx(95)

PANEL_CC_X         = _sx(105)
PANEL_CC_OFF       = _sy(14)
PANEL_CC_W         = _sx(36)

PANEL_CH_X         = PANEL_TYPE_X
PANEL_CH_LBL_Y     = _sy(40)
PANEL_CH_LB_Y      = _sy(52)
PANEL_CH_W         = _sx(50)


# ---- Кнопки Load / Save / Save as ----
PRESET_BTN_W   = _sx(74)
PRESET_BTN_H   = _sy(22)
PRESET_BTN_GAP = _sx(4)
PRESET_BTN_Y = SCREEN_H - _sy(28)   # от нижнего края


# ---- Экран Save As / Rename (позиции клавиатуры) ----
PW_Y_TITLE = _sy(22)
PW_Y_LABEL = _sy(40)
PW_Y_INPUT = _sy(55)
PW_Y_HINT  = _sy(75)
PW_KB_Y    = _sy(95)