from apps.user.clock.utils import draw
from gui.core.colors import *

NAME = 'Digital + Date'
HAS_SECONDS = False

def draw_face_v(ssd, t, top):
    y, mo, d, hh, mm, ss, wd, yd = t
    ssd.fill_rect(0, top, 240, 320 - top, BLACK)
    w = 220
    h = 62
    x = (240 - w) // 2
    y_pos = top + 60
    draw.time_hm(ssd, hh, mm, x, y_pos, w, h, GREEN)
    date_str = '{} {} {}'.format(d, draw.MONTHS[mo - 1], y)
    tw = len(date_str) * 8
    ssd.text(date_str, (240 - tw) // 2, y_pos + h + 40, WHITE)
    wd_str = draw.WEEKDAYS[wd] if 0 <= wd < 7 else ''
    tw2 = len(wd_str) * 8
    ssd.text(wd_str, (240 - tw2) // 2, y_pos + h + 58, WHITE)

def draw_face_h(ssd, t, top):
    y, mo, d, hh, mm, ss, wd, yd = t
    ssd.fill_rect(0, top, 320, 240 - top, BLACK)
    w = 300
    h = 70
    x = (320 - w) // 2
    y_pos = top + 40
    draw.time_hm(ssd, hh, mm, x, y_pos, w, h, GREEN)
    date_str = '{} {} {}'.format(d, draw.MONTHS[mo - 1], y)
    wd_str = draw.WEEKDAYS[wd] if 0 <= wd < 7 else ''
    full = date_str + '  ' + wd_str
    tw = len(full) * 8
    ssd.text(full, (320 - tw) // 2, y_pos + h + 30, WHITE)