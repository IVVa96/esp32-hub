# ======================================================================
# draw.py — общие примитивы для циферблатов
# ======================================================================
from gui.core.colors import *


SEG = {
    '0': 'abcdef', '1': 'bc',     '2': 'abdeg',  '3': 'abcdg',
    '4': 'bcfg',   '5': 'acdfg',  '6': 'acdefg', '7': 'abc',
    '8': 'abcdefg','9': 'abcdfg',
}

MONTHS   = ('Jan','Feb','Mar','Apr','May','Jun',
            'Jul','Aug','Sep','Oct','Nov','Dec')
WEEKDAYS = ('Mon','Tue','Wed','Thu','Fri','Sat','Sun')


def digit(ssd, ch, x, y, w, h, color):
    t = max(2, w // 6)
    segs = SEG.get(ch, '')
    x2 = x + w - 1
    y2 = y + h - 1
    ymid = y + h // 2
    half_ht = h // 2
    if 'a' in segs: ssd.fill_rect(x + t, y, w - 2*t, t, color)
    if 'b' in segs: ssd.fill_rect(x2 - t + 1, y + t, t, half_ht - t, color)
    if 'c' in segs: ssd.fill_rect(x2 - t + 1, ymid, t, half_ht - t + 1, color)
    if 'd' in segs: ssd.fill_rect(x + t, y2 - t + 1, w - 2*t, t, color)
    if 'e' in segs: ssd.fill_rect(x, ymid, t, half_ht - t + 1, color)
    if 'f' in segs: ssd.fill_rect(x, y + t, t, half_ht - t, color)
    if 'g' in segs: ssd.fill_rect(x + t, ymid, w - 2*t, t, color)


def colon(ssd, cx, y, h, color):
    t = max(3, h // 10)
    d1 = y + h // 3
    d2 = y + 2 * h // 3
    ssd.fill_rect(cx - t//2, d1 - t//2, t, t, color)
    ssd.fill_rect(cx - t//2, d2 - t//2, t, t, color)


def thick_line(ssd, x0, y0, x1, y1, thickness, color):
    dx = x1 - x0
    dy = y1 - y0
    L = (dx*dx + dy*dy) ** 0.5
    if L < 0.1:
        return
    px = -dy / L
    py = dx / L
    half = thickness // 2
    for i in range(-half, half + 1):
        ssd.line(x0 + int(px*i), y0 + int(py*i),
                 x1 + int(px*i), y1 + int(py*i), color)


def time_hm(ssd, hh, mm, x, y, w, h, color):
    gap = max(2, w // 36)
    cg  = max(3, w // 27)
    dg  = (w - 2*gap - cg) // 4
    x0 = x
    x1 = x0 + dg + gap
    c  = x1 + dg + cg // 2
    x2 = x1 + dg + cg
    x3 = x2 + dg + gap
    digit(ssd, str(hh // 10), x0, y, dg, h, color)
    digit(ssd, str(hh % 10), x1, y, dg, h, color)
    colon(ssd, c, y, h, color)
    digit(ssd, str(mm // 10), x2, y, dg, h, color)
    digit(ssd, str(mm % 10), x3, y, dg, h, color)


def time_hms(ssd, hh, mm, ss, x, y, w, h, color):
    gap = max(1, w // 55)
    cg  = max(2, w // 36)
    dg  = (w - 2*gap - 2*cg) // 6
    x0 = x
    x1 = x0 + dg + gap
    c1 = x1 + dg + cg // 2
    x2 = x1 + dg + cg
    x3 = x2 + dg + gap
    c2 = x3 + dg + cg // 2
    x4 = x3 + dg + cg
    x5 = x4 + dg + gap
    digit(ssd, str(hh // 10), x0, y, dg, h, color)
    digit(ssd, str(hh % 10), x1, y, dg, h, color)
    colon(ssd, c1, y, h, color)
    digit(ssd, str(mm // 10), x2, y, dg, h, color)
    digit(ssd, str(mm % 10), x3, y, dg, h, color)
    colon(ssd, c2, y, h, color)
    digit(ssd, str(ss // 10), x4, y, dg, h, color)
    digit(ssd, str(ss % 10), x5, y, dg, h, color)


def analog(ssd, cx, cy, r, hh, mm, ss, with_sec=True):
    import math
    try:
        ssd.ellipse(cx, cy, r, r, WHITE)
    except Exception:
        steps = 120
        for i in range(steps):
            a = i * 2 * math.pi / steps
            ssd.pixel(cx + int(r * math.cos(a)),
                      cy + int(r * math.sin(a)), WHITE)
    for i in range(12):
        a = (i * 30 - 90) * math.pi / 180
        mx = cx + int((r - 10) * math.cos(a))
        my = cy + int((r - 10) * math.sin(a))
        sz = 4 if i % 3 == 0 else 2
        ssd.fill_rect(mx - sz//2, my - sz//2, sz, sz, WHITE)

    ha = ((hh % 12) * 30 + mm * 0.5 - 90) * math.pi / 180
    thick_line(ssd, cx, cy,
               cx + int(r * 0.50 * math.cos(ha)),
               cy + int(r * 0.50 * math.sin(ha)), 5, WHITE)
    ma = (mm * 6 + ss * 0.1 - 90) * math.pi / 180
    thick_line(ssd, cx, cy,
               cx + int(r * 0.78 * math.cos(ma)),
               cy + int(r * 0.78 * math.sin(ma)), 3, WHITE)
    if with_sec:
        sa = (ss * 6 - 90) * math.pi / 180
        ssd.line(cx, cy,
                 cx + int(r * 0.88 * math.cos(sa)),
                 cy + int(r * 0.88 * math.sin(sa)), RED)
    ssd.fill_rect(cx - 2, cy - 2, 5, 5, WHITE)