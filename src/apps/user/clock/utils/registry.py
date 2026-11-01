# ======================================================================
# registry.py — реестр циферблатов с ленивой загрузкой
# ======================================================================
import os
import sys

from core.logger import info, verbose, error


_DIR     = 'apps/user/clock/utils/faces'
_DIR_MOD = 'apps.user.clock.utils.faces'

_FACES  = None
_LOADED = {}


def _scan():
    global _FACES
    if _FACES is not None:
        return _FACES

    faces = []
    try:
        entries = os.listdir(_DIR)
        verbose("[CLOCK] scan:", _DIR, "->", len(entries), "entries")
    except Exception as e:
        error("[CLOCK] listdir fail:", e)
        entries = []

    for f in entries:
        if not (f.startswith('face_') and f.endswith('.py')):
            continue
        mod_name = f[:-3]
        stem = mod_name[5:].replace('_', ' ')
        disp = ' '.join(
            (w[:1].upper() + w[1:]) if w else ''
            for w in stem.split(' ')
        )
        faces.append((mod_name, disp))
        verbose("[CLOCK]   +", mod_name, "=", disp)

    faces.sort()
    info("[CLOCK] faces:", len(faces))
    _FACES = faces
    return faces


def count():
    return len(_scan())


def display_name(idx):
    f = _scan()
    if 0 <= idx < len(f):
        return f[idx][1]
    return '?'


def load(idx):
    faces = _scan()
    if idx < 0 or idx >= len(faces):
        return None
    mod_name = faces[idx][0]
    if mod_name in _LOADED:
        return _LOADED[mod_name]
    full = _DIR_MOD + '.' + mod_name
    try:
        __import__(full)
        mod = sys.modules[full]
        _LOADED[mod_name] = mod
        has_v = hasattr(mod, 'draw_face_v') or hasattr(mod, 'draw_face')
        has_h = hasattr(mod, 'draw_face_h')
        verbose("[CLOCK] loaded:", mod_name,
                "V=" + ("1" if has_v else "0"),
                "H=" + ("1" if has_h else "0"))
        return mod
    except Exception as e:
        error("[CLOCK] LOAD FAIL:", mod_name, type(e).__name__, e)
        return None


def invalidate():
    global _FACES
    _FACES = None


def debug_info():
    faces = _scan()
    parts = []
    for i, (mod, _disp) in enumerate(faces):
        tag = 'ok' if mod in _LOADED else 'lazy'
        parts.append('{}:{}:{}'.format(i, mod, tag))
    return '{} faces: {}'.format(len(faces), ', '.join(parts))