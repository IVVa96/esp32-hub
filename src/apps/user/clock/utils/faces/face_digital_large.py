from apps.user.clock.utils import draw
from gui.core.colors import *

NAME = 'Digital Large'
HAS_SECONDS = False

def draw_face_v(ssd, t, top):
    y, mo, d, hh, mm, ss, wd, yd = t
    ssd.fill_rect(0, top, 240, 320 - top, BLACK)
    w = 220
    h = 80
    x = (240 - w) // 2
    y_pos = top + (320 - top - h) // 2
    draw.time_hm(ssd, hh, mm, x, y_pos, w, h, GREEN)

def draw_face_h(ssd, t, top):
    y, mo, d, hh, mm, ss, wd, yd = t
    ssd.fill_rect(0, top, 320, 240 - top, BLACK)
    w = 300
    h = 70
    x = (320 - w) // 2
    y_pos = top + (240 - top - h) // 2
    draw.time_hm(ssd, hh, mm, x, y_pos, w, h, GREEN)