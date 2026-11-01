# ======================================================================
# save.py — сохранение/загрузка пресетов MIDI (JSON)
# ======================================================================
# Допустимые типы: '—', 'Btn/Sw', 'Toggle Btn', 'Pot', 'Encoder'.
# Старые названия ('Button', 'Virt Sw', 'Virt_sw') конвертируются автоматически.
#
# 'encB' не пишется в файл — восстанавливается из 'pair' энкодера.
# 'Encoder' без пары записывается как '—' (защита от недоделанного
# выбора при выключении питания).
# ======================================================================
import os
import json

from apps.user.midi.config import (
    MIDI_PRESETS_DIR, MIDI_DEFAULT_PRESET, MIDI_DEFAULT_CHANNEL,
)
from core.logger import error


_TEMP_NAME = '_temp'
_temp_cache = None
_temp_base = None
_temp_controls = None

_VALID_TYPES = ('—', 'Btn/Sw', 'Toggle Btn', 'Pot', 'Encoder')

# Контролы веб-пульта: фейдер, кнопка, переключатель, ручка.
_VALID_KINDS = ('fader', 'button', 'switch')


def _normalize_type(t):
    if t == 'Button':
        return 'Btn/Sw'
    if t == 'Virt Sw' or t == 'Virt_sw':
        return 'Toggle Btn'
    return t


def _path(name):
    return '{}/{}.json'.format(MIDI_PRESETS_DIR, name)


def _ensure_dir():
    try:
        os.stat(MIDI_PRESETS_DIR)
        return True
    except OSError:
        pass
    parts = MIDI_PRESETS_DIR.split('/')
    cur = ''
    for p in parts:
        if not p:
            continue
        cur = p if not cur else cur + '/' + p
        try:
            os.mkdir(cur)
        except OSError:
            pass
        except Exception as e:
            error("save mkdir:", e)
            return False
    try:
        os.stat(MIDI_PRESETS_DIR)
        return True
    except OSError:
        return False


def exists(name):
    try:
        os.stat(_path(name))
        return True
    except OSError:
        return False


def list_saves():
    if not _ensure_dir():
        return []
    out = []
    try:
        for name in os.listdir(MIDI_PRESETS_DIR):
            if name.endswith('.json') and not name.startswith('_'):
                out.append(name[:-5])
    except Exception:
        pass
    return sorted(out)


def _build_pins(cfg):
    pins = {}
    for pin, c in cfg.items():
        t = _normalize_type(c.get('type', '—'))
        if t == 'encB':
            continue
        if t not in _VALID_TYPES:
            continue
        # Защита: Encoder без пары не сохраняем
        if t == 'Encoder' and c.get('pair') is None:
            t = '—'
        entry = {'type': t, 'cc': int(c.get('cc', 0))}
        ch = c.get('channel', MIDI_DEFAULT_CHANNEL)
        try:
            entry['channel'] = int(ch)
        except Exception:
            entry['channel'] = MIDI_DEFAULT_CHANNEL
        p = c.get('pair')
        if p is not None and t == 'Encoder':
            try:
                entry['pair'] = int(p)
            except Exception:
                pass
        pins[str(pin)] = entry
    return pins


def _parse_pins(data):
    if not isinstance(data, dict):
        return None
    pins = data.get('pins')
    if not isinstance(pins, dict):
        return None
    out = {}
    for k, v in pins.items():
        try:
            pin = int(k)
        except Exception:
            continue
        if not isinstance(v, dict):
            continue
        t = _normalize_type(v.get('type', '—'))
        if t not in _VALID_TYPES:
            continue
        try:
            cc = int(v.get('cc', 0))
        except Exception:
            continue
        if not (0 <= cc <= 127):
            continue
        pair = v.get('pair')
        if pair is not None:
            try:
                pair = int(pair)
            except Exception:
                pair = None
        ch = v.get('channel', MIDI_DEFAULT_CHANNEL)
        try:
            ch = int(ch)
        except Exception:
            ch = MIDI_DEFAULT_CHANNEL
        if not (1 <= ch <= 16):
            ch = MIDI_DEFAULT_CHANNEL
        out[pin] = {'type': t, 'cc': cc, 'pair': pair, 'channel': ch}
    return out


def load(name):
    if name == MIDI_DEFAULT_PRESET:
        return None
    if not _ensure_dir():
        return None
    try:
        with open(_path(name), 'r') as f:
            data = json.load(f)
    except Exception:
        return None
    return _parse_pins(data)


def _clean_controls(items):
    """Приводит список контролов к валидному виду (id = позиция + 1)."""
    out = []
    if not isinstance(items, (list, tuple)):
        return out
    for i, c in enumerate(items):
        if not isinstance(c, dict):
            continue
        kind = c.get('kind')
        if kind == 'knob':
            kind = 'fader'
        if kind not in _VALID_KINDS:
            continue
        try:
            cc = int(c.get('cc', 0))
        except Exception:
            cc = 0
        if cc < 0:
            cc = 0
        elif cc > 127:
            cc = 127
        try:
            ch = int(c.get('ch', MIDI_DEFAULT_CHANNEL))
        except Exception:
            ch = MIDI_DEFAULT_CHANNEL
        if not (1 <= ch <= 16):
            ch = MIDI_DEFAULT_CHANNEL
        try:
            val = int(c.get('value', 0))
        except Exception:
            val = 0
        if val < 0:
            val = 0
        elif val > 127:
            val = 127
        label = c.get('label')
        if not isinstance(label, str) or not label:
            label = 'CTRL {}'.format(i + 1)
        try:
            slot = int(c.get('slot', -1))
        except Exception:
            slot = -1
        if slot < 0:
            slot = -1
        out.append({'id': i + 1, 'kind': kind, 'label': label[:16],
                    'cc': cc, 'ch': ch, 'value': val, 'slot': slot})
    return out


def _read(name):
    if not _ensure_dir():
        return None
    try:
        with open(_path(name), 'r') as f:
            return json.load(f)
    except Exception:
        return None


def load_controls(name):
    if name == MIDI_DEFAULT_PRESET:
        data = _read(_TEMP_NAME)
        if not isinstance(data, dict):
            return []
        base = data.get('base', MIDI_DEFAULT_PRESET)
        if base != MIDI_DEFAULT_PRESET:
            return []
        return _clean_controls(data.get('controls'))
    data = _read(name)
    if not isinstance(data, dict):
        return []
    return _clean_controls(data.get('controls'))


def save(name, cfg, controls=None):
    if name == MIDI_DEFAULT_PRESET:
        return False
    if not _ensure_dir():
        return False
    pins = _build_pins(cfg)
    if controls is None:
        old = _read(name)
        controls = old.get('controls') if isinstance(old, dict) else None
    payload = {'name': name, 'pins': pins,
               'controls': _clean_controls(controls)}
    try:
        with open(_path(name), 'w') as f:
            json.dump(payload, f)
        return True
    except Exception as e:
        error("save.save:", e)
        return False


def delete(name):
    if name == MIDI_DEFAULT_PRESET:
        return False
    if not _ensure_dir():
        return False
    try:
        os.remove(_path(name))
        return True
    except Exception:
        return False


def rename(old_name, new_name):
    if old_name == MIDI_DEFAULT_PRESET:
        return False
    if new_name == MIDI_DEFAULT_PRESET:
        return False
    if old_name == new_name:
        return True
    if exists(new_name):
        return False
    pins = load(old_name)
    if pins is None:
        return False
    ctls = load_controls(old_name)
    if not save(new_name, pins, ctls):
        return False
    try:
        os.remove(_path(old_name))
    except Exception:
        pass
    base, tpins = load_temp()
    if base == old_name:
        try:
            save_temp(tpins or pins, new_name, ctls)
        except Exception:
            pass
    return True


def save_temp(cfg, base, controls=None):
    global _temp_cache, _temp_base, _temp_controls
    if not _ensure_dir():
        return False
    pins = _build_pins(cfg)
    base = base or MIDI_DEFAULT_PRESET
    if controls is None:
        if _temp_controls is not None and _temp_base == base:
            controls = _temp_controls
        else:
            controls = load_controls(base)
    controls = _clean_controls(controls)
    payload = {'base': base, 'pins': pins, 'controls': controls}
    _temp_base = base
    _temp_controls = controls
    try:
        new_json = json.dumps(payload)
    except Exception as e:
        error("save_temp dumps:", e)
        return False
    if _temp_cache == new_json:
        return True
    try:
        with open(_path(_TEMP_NAME), 'w') as f:
            f.write(new_json)
        _temp_cache = new_json
        return True
    except Exception as e:
        error("save_temp write:", e)
        return False


def load_temp():
    global _temp_cache, _temp_base, _temp_controls
    if not _ensure_dir():
        return None, None
    try:
        with open(_path(_TEMP_NAME), 'r') as f:
            raw = f.read()
    except Exception:
        return None, None
    _temp_cache = raw
    try:
        data = json.loads(raw)
    except Exception:
        return None, None
    base = data.get('base', MIDI_DEFAULT_PRESET)
    if not isinstance(base, str) or not base:
        base = MIDI_DEFAULT_PRESET
    _temp_base = base
    _temp_controls = _clean_controls(data.get('controls'))
    pins = _parse_pins(data)
    return base, pins


def temp_exists():
    try:
        os.stat(_path(_TEMP_NAME))
        return True
    except OSError:
        return False