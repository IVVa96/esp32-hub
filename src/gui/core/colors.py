# colors.py Micropython GUI library for TFT displays: colors and shapes

# Released under the MIT License (MIT). See LICENSE.
# Copyright (c) 2019-2023 Peter Hinch
from hardware_setup import SSD
from gui.core.writer import CWriter

# Code can be portable between 4-bit and other drivers by calling create_color
def create_color(idx, r, g, b):
    return CWriter.create_color(SSD, idx, r, g, b)

if hasattr(SSD, 'lut'):  # Colors defined by LUT
    BLACK = create_color(0, 0, 0, 0)
    GREEN = create_color(1, 0, 255, 0)
    RED = create_color(2, 255, 0, 0)
    LIGHTRED = create_color(3, 140, 0, 0)
    BLUE = create_color(4, 0, 0, 255)
    YELLOW = create_color(5, 255, 255, 0)
    GREY = create_color(6, 100, 100, 100)
    MAGENTA = create_color(7, 255, 0, 255)
    CYAN = create_color(8, 0, 255, 255)
    LIGHTGREEN = create_color(9, 0, 100, 0)
    DARKGREEN = create_color(10, 0, 80, 0)
    DARKBLUE = create_color(11, 0, 0, 90)
    # 12, 13, 14 free for user definition
    AMBER = create_color(12, 255, 140, 26)   # насыщенный оранжевый, как на сайте
    DIM = create_color(13, 142, 139, 139)    # серый сайта #8e8b8b, хорошо читается на чёрном
    PANEL = create_color(14, 10, 10, 11)     # панели/шапка #0a0a0b, почти чёрный
    WHITE = create_color(15, 255, 255, 255)
else:
    BLACK = SSD.rgb(0, 0, 0)
    GREEN = SSD.rgb(0, 255, 0)
    RED = SSD.rgb(255, 0, 0)
    LIGHTRED = SSD.rgb(140, 0, 0)
    BLUE = SSD.rgb(0, 0, 255)
    YELLOW = SSD.rgb(255, 255, 0)
    GREY = SSD.rgb(100, 100, 100)
    MAGENTA = SSD.rgb(255, 0, 255)
    CYAN = SSD.rgb(0, 255, 255)
    LIGHTGREEN = SSD.rgb(0, 100, 0)
    DARKGREEN = SSD.rgb(0, 80, 0)
    DARKBLUE = SSD.rgb(0, 0, 90)
    AMBER = SSD.rgb(255, 140, 26)
    DIM = SSD.rgb(142, 139, 139)
    PANEL = SSD.rgb(10, 10, 11)
    WHITE = SSD.rgb(255, 255, 255)

CIRCLE = 1
RECTANGLE = 2
CLIPPED_RECT = 3

FOCUS = 0
PRECISION = 1
FG = 2
BG = 3
GREY_OUT = 4
ADJUSTING = 5
# FOCUS and FG default to the amber accent so no widget falls back to white.
color_map = [AMBER, YELLOW, AMBER, BLACK, GREY, LIGHTGREEN]
