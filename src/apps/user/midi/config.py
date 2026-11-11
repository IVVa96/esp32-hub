# ======================================================================
# midi_utils/config.py — настройки MIDI-контроллера
# ======================================================================
from gui.core.colors import RED, YELLOW, CYAN, MAGENTA, BLUE


# ---- Канал и CC по умолчанию ----
MIDI_DEFAULT_CHANNEL = 1
MIDI_CC_GROUP_COLORS = (RED, YELLOW, CYAN, MAGENTA, BLUE)


# ---- Кодировщики (encoder) ----
MIDI_ENCODER_INC = 1
MIDI_ENCODER_DEC = 127


# ---- Частота опроса ADC (потенциометры) ----
# Опрос общий на все ручки (см. hw._pot_loop), поэтому 10 мс на цикл
# дешевле, чем раньше 20 мс на каждую из семи отдельных задач.
MIDI_POLL_MS = 10


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


# ---- Экран Save As / Rename (позиции клавиатуры) ----
PW_Y_TITLE = 16
PW_Y_LABEL = 30
PW_Y_INPUT = 44
PW_Y_HINT  = 56
PW_KB_Y    = 66
