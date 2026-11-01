# ======================================================================
# engine.py — web control layer for the MIDI app
# ======================================================================
# Reuses MidiScreen class state (pins/presets/transport) so the browser
# and the on-device screen always edit the same configuration.
# ======================================================================
from apps.user.midi.app import MidiScreen
from apps.user.midi.config import (
    MIDI_AVAILABLE_PINS, MIDI_ADC_PINS, MIDI_DEFAULT_CHANNEL,
    MIDI_DEFAULT_PRESET,
)
from apps.user.midi.utils import hw, ble_midi
from apps.user.midi.utils import save as midi_save


TYPES = ('—', 'Btn/Sw', 'Toggle Btn', 'Pot', 'Encoder')
ACTIVE_TYPES = ('Btn/Sw', 'Toggle Btn', 'Pot', 'Encoder')

# Web control surface: faders, buttons, switches, knobs -> CC messages.
KINDS = ('fader', 'button', 'switch')
MAX_CONTROLS = 16
COLS = 8          # Surface grid columns (shared with the web page).


def set_cols(n):
    """Grid column count used for layout; the page reports its own width."""
    global COLS
    try:
        n = int(n)
    except Exception:
        return
    if n < 2:
        n = 2
    elif n > 12:
        n = 12
    COLS = n


_MAX_NAME = 24
_MAX_LABEL = 16

_controls = None


class _Host:
    """Minimal stand-in for MidiScreen: methods only need _cfg."""
    _cfg = MidiScreen._cfg

    def _queue_refresh(self, pin):
        pass

    def _rebuild(self, pin):
        MidiScreen._rebuild(self, pin)

    def _rebuild_all(self):
        MidiScreen._rebuild_all(self)

    def _stop_all(self):
        MidiScreen._stop_all(self)


_host = _Host()
_started = False


# ---- lifecycle -------------------------------------------------------
def _ensure_loaded():
    global _controls
    if not MidiScreen._presets_loaded:
        MidiScreen._load_from_temp_or_preset()
        MidiScreen._presets_loaded = True
    if _controls is None:
        _controls = midi_save.load_controls(
            MidiScreen._current_preset or MIDI_DEFAULT_PRESET)
        _renumber()
        _layout()


def start():
    """Start transports and GPIO inputs if the web page opened first."""
    global _started
    _ensure_loaded()
    _host._cfg = MidiScreen._cfg
    if _started:
        # Classic-экран мог остановить входы при переходе в web-режим.
        if not MidiScreen._components and _has_active_pins():
            MidiScreen._rebuild_all(_host)
        return
    _started = True
    try:
        hw.start(MidiScreen.mode)
    except Exception:
        pass
    if MidiScreen.mode == 'ble':
        try:
            ble_midi.start()
        except Exception:
            pass
    MidiScreen._rebuild_all(_host)


def _has_active_pins():
    for p in MIDI_AVAILABLE_PINS:
        if MidiScreen._cfg[p]['type'] in ACTIVE_TYPES:
            return True
    return False


def stop():
    global _started
    _started = False
    try:
        MidiScreen._stop_all(_host)
    except Exception:
        pass
    # Дописать отложенный _temp: выход из веб-режима не должен терять
    # последние изменения пресета.
    try:
        midi_save.flush_temp()
    except Exception:
        pass


def _refresh_dirty():
    name = MidiScreen._current_preset or MIDI_DEFAULT_PRESET
    if name == MIDI_DEFAULT_PRESET:
        MidiScreen._dirty = not MidiScreen._pins_equal(
            MidiScreen._cfg, MidiScreen._default_pins())
        return
    pins = midi_save.load(name)
    if pins is None:
        MidiScreen._dirty = True
    else:
        MidiScreen._dirty = not MidiScreen._pins_equal(
            MidiScreen._cfg, pins)


def _save_temp():
    try:
        midi_save.save_temp(
            MidiScreen._cfg,
            MidiScreen._current_preset or MIDI_DEFAULT_PRESET,
            _controls or [])
    except Exception:
        pass


# ---- control surface -------------------------------------------------
def _renumber():
    """id — сквозной (для API), num — номер внутри своего типа."""
    counters = {}
    for i, c in enumerate(_controls):
        c['id'] = i + 1
        k = c['kind']
        n = counters.get(k, 0) + 1
        counters[k] = n
        c['num'] = n
    _layout()


def _label_for(c):
    return '{} {}'.format(c['kind'].upper(), c.get('num', c['id']))


def _control(cid):
    try:
        cid = int(cid)
    except Exception:
        return None
    for c in _controls:
        if c['id'] == cid:
            return c
    return None


def _controls_state():
    return [{'id': c['id'], 'num': c.get('num', c['id']),
             'kind': c['kind'], 'label': c['label'],
             'cc': c['cc'], 'ch': c['ch'], 'value': c['value'],
             'slot': c.get('slot', 0)}
            for c in (_controls or [])]


# ---- surface layout --------------------------------------------------
def _span(kind):
    """Fader takes two grid rows, buttons and switches take one."""
    return 2 if kind == 'fader' else 1


def _cells(slot, kind):
    out = [slot]
    if _span(kind) == 2:
        out.append(slot + COLS)
    return out


def _fits(slot, kind, used):
    if slot < 0:
        return False
    for s in _cells(slot, kind):
        if s in used:
            return False
    return True


def _find_slot(start, kind, used):
    slot = start if start > 0 else 0
    while not _fits(slot, kind, used):
        slot += 1
        if slot > 1024:
            break
    return slot


def _place(order):
    used = set()
    for c in order:
        slot = _find_slot(c.get('slot', -1), c['kind'], used)
        c['slot'] = slot
        for s in _cells(slot, c['kind']):
            used.add(s)
    return used


def _layout():
    """Keep stored slots when free, otherwise pack into the first gap."""
    order = sorted(_controls or [], key=lambda c: (c.get('slot', -1), c['id']))
    return _place(order)


def move_control(cid, slot):
    _ensure_loaded()
    c = _control(cid)
    if c is None:
        return {'ok': False, 'error': 'no such control'}
    try:
        slot = int(slot)
    except Exception:
        return {'ok': False, 'error': 'bad slot'}
    if slot < 0:
        return {'ok': False, 'error': 'bad slot'}
    # Place the dragged control first, then let the rest shift right/down
    # into the nearest free cell, so it always gets exactly the drop slot.
    c['slot'] = slot
    rest = [o for o in _controls if o is not c]
    rest.sort(key=lambda o: (o.get('slot', -1), o['id']))
    _place([c] + rest)
    _save_temp()
    return state()


def swap_control(cid, slot):
    """Drop onto an occupied cell: exchange positions with its owner."""
    _ensure_loaded()
    c = _control(cid)
    if c is None:
        return {'ok': False, 'error': 'no such control'}
    try:
        slot = int(slot)
    except Exception:
        return {'ok': False, 'error': 'bad slot'}
    if slot < 0:
        return {'ok': False, 'error': 'bad slot'}
    other = None
    for o in _controls:
        if o is c:
            continue
        if slot in _cells(o.get('slot', 0), o['kind']):
            other = o
            break
    if other is None:
        return move_control(cid, slot)
    mine = c['slot']
    c['slot'] = other['slot']
    other['slot'] = mine
    rest = [o for o in _controls if o is not c and o is not other]
    rest.sort(key=lambda o: (o.get('slot', -1), o['id']))
    _place([c, other] + rest)
    _save_temp()
    return state()


def add_control(kind='fader'):
    _ensure_loaded()
    if kind not in KINDS:
        return {'ok': False, 'error': 'bad kind'}
    if len(_controls) >= MAX_CONTROLS:
        return {'ok': False, 'error': 'control limit reached'}
    used = set(c['cc'] for c in _controls)
    cc = 0
    while cc < 128 and cc in used:
        cc += 1
    _controls.append({
        'id': len(_controls) + 1,
        'kind': kind,
        'label': '',
        'cc': cc if cc < 128 else 0,
        'ch': 1,
        'value': 0,
        'slot': -1,
    })
    _renumber()
    _layout()
    _controls[-1]['label'] = _label_for(_controls[-1])
    _save_temp()
    return state()


def remove_control(cid):
    _ensure_loaded()
    c = _control(cid)
    if c is None:
        return {'ok': False, 'error': 'no such control'}
    _controls.remove(c)
    _renumber()
    _save_temp()
    return state()


def set_control(cid, cc=None, ch=None, label=None):
    _ensure_loaded()
    c = _control(cid)
    if c is None:
        return {'ok': False, 'error': 'no such control'}
    if cc is not None and cc != '':
        try:
            cc = int(cc)
        except Exception:
            return {'ok': False, 'error': 'bad CC'}
        if cc < 0 or cc > 127:
            return {'ok': False, 'error': 'CC must be 0..127'}
        c['cc'] = cc
    if ch is not None and ch != '':
        try:
            ch = int(ch)
        except Exception:
            return {'ok': False, 'error': 'bad channel'}
        if ch < 1 or ch > 16:
            return {'ok': False, 'error': 'Channel must be 1..16'}
        c['ch'] = ch
    if label is not None:
        label = (label or '').strip()
        if not label:
            label = _label_for(c)
        c['label'] = label[:_MAX_LABEL]
    _save_temp()
    return state()


def send_control(cid, value=None, persist=True, lite=False):
    _ensure_loaded()
    c = _control(cid)
    if c is None:
        return {'ok': False, 'error': 'no such control'}
    if value not in (None, ''):
        try:
            value = int(value)
        except Exception:
            return {'ok': False, 'error': 'bad value'}
        if value < 0 or value > 127:
            return {'ok': False, 'error': 'value must be 0..127'}
        c['value'] = value
    elif c['kind'] == 'switch':
        c['value'] = 0 if c['value'] else 127
    elif c['kind'] == 'button':
        # Momentary press: send on, then off straight away.
        try:
            ch = (c['ch'] - 1) & 0x0F
            hw.send_cc(ch, c['cc'], 127)
            hw.send_cc(ch, c['cc'], 0)
        except Exception:
            return {'ok': False, 'error': 'send failed'}
        c['value'] = 0
        if persist:
            _save_temp()
        if lite:
            return {'ok': True}
        return state()
    try:
        hw.send_cc((c['ch'] - 1) & 0x0F, c['cc'], c['value'])
    except Exception:
        return {'ok': False, 'error': 'send failed'}
    if persist:
        _save_temp()
    if lite:
        return {'ok': True}
    return state()


# ---- state -----------------------------------------------------------
def state(cols=None):
    if cols not in (None, ''):
        set_cols(cols)
    _ensure_loaded()
    pins = []
    for p in MIDI_AVAILABLE_PINS:
        c = MidiScreen._cfg[p]
        pins.append({
            'pin': p,
            'type': c['type'],
            'cc': c['cc'],
            'ch': c.get('channel', MIDI_DEFAULT_CHANNEL),
            'pair': c.get('pair'),
            'adc': p in MIDI_ADC_PINS,
        })
    presets = [MIDI_DEFAULT_PRESET]
    try:
        for n in midi_save.list_saves():
            if n != MIDI_DEFAULT_PRESET:
                presets.append(n)
    except Exception:
        pass
    return {
        'ok': True,
        'mode': MidiScreen.mode,
        'preset': MidiScreen._current_preset or MIDI_DEFAULT_PRESET,
        'dirty': bool(MidiScreen._dirty),
        'pins': pins,
        'presets': presets,
        'types': list(TYPES),
        'channels': list(range(1, 17)),
        'controls': _controls_state(),
        'kinds': list(KINDS),
        'ble_available': ble_midi.available(),
        'ble_connected': ble_midi.is_connected(),
    }


# ---- editing ---------------------------------------------------------
def _free_peer(pin):
    """Release the partner pin if `pin` was part of an encoder pair.

    Returns the released GPIO number or None.
    """
    c = MidiScreen._cfg.get(pin)
    if not c:
        return None
    peer = c.get('pair')
    if peer is None:
        return None
    pc = MidiScreen._cfg.get(peer)
    if pc is not None and pc.get('type') == 'encB' and pc.get('pair') == pin:
        pc['type'] = '—'
        pc['pair'] = None
    c['pair'] = None
    return peer


def _valid_name(name):
    name = (name or '').strip()
    if not name or len(name) > _MAX_NAME:
        return None
    if '/' in name or '\\' in name or name.startswith('_'):
        return None
    if name == MIDI_DEFAULT_PRESET:
        return None
    return name


def set_pin(pin, type_, cc, ch, pair=None):
    _ensure_loaded()
    try:
        pin = int(pin)
        cc = int(cc)
        ch = int(ch)
    except Exception:
        return {'ok': False, 'error': 'bad values'}
    if pin not in MidiScreen._cfg:
        return {'ok': False, 'error': 'bad pin'}
    if type_ not in TYPES:
        return {'ok': False, 'error': 'bad type'}
    if cc < 0 or cc > 127:
        return {'ok': False, 'error': 'CC must be 0..127'}
    if ch < 1 or ch > 16:
        return {'ok': False, 'error': 'Channel must be 1..16'}
    if type_ == 'Pot' and pin not in MIDI_ADC_PINS:
        return {'ok': False, 'error': 'GPIO{} is not ADC'.format(pin)}
    if MidiScreen._cfg[pin]['type'] == 'encB':
        return {'ok': False, 'error': 'pin is an encoder partner'}

    touched = [pin]
    peer = _free_peer(pin)
    if peer is not None:
        touched.append(peer)

    if type_ == 'Encoder':
        try:
            pair = int(pair) if pair not in (None, '', 'None') else None
        except Exception:
            pair = None
        if pair is not None:
            if pair == pin or pair not in MidiScreen._cfg:
                return {'ok': False, 'error': 'bad encoder pair'}
            pc = MidiScreen._cfg[pair]
            if pc['type'] not in ('—', 'encB'):
                return {'ok': False, 'error': 'GPIO{} is busy'.format(pair)}
            # Steal the pin from another encoder if it was its partner.
            if pc['type'] == 'encB' and pc.get('pair') not in (None, pin):
                other = pc['pair']
                freed = _free_peer(other)
                if freed is not None:
                    touched.append(freed)
            pc['type'] = 'encB'
            pc['pair'] = pin
            pc['cc'] = cc
            pc['channel'] = ch
        c = MidiScreen._cfg[pin]
        c['type'] = 'Encoder'
        c['cc'] = cc
        c['channel'] = ch
        c['pair'] = pair
        if pair is not None:
            touched.append(pair)
    else:
        c = MidiScreen._cfg[pin]
        c['type'] = type_
        c['cc'] = cc
        c['channel'] = ch
        c['pair'] = None

    for p in touched:
        try:
            MidiScreen._rebuild(_host, p)
        except Exception:
            pass

    _refresh_dirty()
    _save_temp()
    return state()


def set_mode(mode):
    _ensure_loaded()
    if mode not in ('wire', 'ble'):
        return {'ok': False, 'error': 'bad mode'}
    if mode == 'ble' and not ble_midi.available():
        return {'ok': False, 'error': 'BLE MIDI unavailable'}
    MidiScreen.mode = mode
    try:
        hw.start(mode)
    except Exception:
        pass
    try:
        if mode == 'ble':
            ble_midi.start()
        else:
            ble_midi.stop()
    except Exception:
        pass
    return state()


# ---- presets ---------------------------------------------------------
def load(name):
    global _controls
    _ensure_loaded()
    if name == MIDI_DEFAULT_PRESET:
        # "default" is the clean slate: no pins configured, no widgets.
        return reset()
    pins = midi_save.load(name)
    if pins is None:
        return {'ok': False, 'error': 'preset not found'}
    MidiScreen._apply_preset(pins)
    MidiScreen._current_preset = name
    MidiScreen._dirty = False
    _controls = midi_save.load_controls(name)
    _renumber()
    _save_temp()
    MidiScreen._rebuild_all(_host)
    return state()


def reset():
    """Drop every change and go back to the default preset."""
    global _controls
    _ensure_loaded()
    MidiScreen._apply_preset(None)
    MidiScreen._current_preset = MIDI_DEFAULT_PRESET
    MidiScreen._dirty = False
    _controls = []
    _renumber()
    midi_save.save_temp(MidiScreen._cfg, MIDI_DEFAULT_PRESET, [])
    MidiScreen._rebuild_all(_host)
    return state()


def save(name, overwrite=False):
    _ensure_loaded()
    name = _valid_name(name)
    if name is None:
        return {'ok': False, 'error': 'invalid name'}
    if not overwrite and midi_save.exists(name) and \
            name != MidiScreen._current_preset:
        return {'ok': False, 'error': 'preset exists'}
    if not midi_save.save(name, MidiScreen._cfg, _controls):
        return {'ok': False, 'error': 'save failed'}
    MidiScreen._current_preset = name
    MidiScreen._dirty = False
    _save_temp()
    return state()


def delete(name):
    global _controls
    _ensure_loaded()
    if not name or name == MIDI_DEFAULT_PRESET:
        return {'ok': False, 'error': 'reserved preset'}
    if not midi_save.delete(name):
        return {'ok': False, 'error': 'delete failed'}
    if MidiScreen._current_preset == name:
        MidiScreen._current_preset = MIDI_DEFAULT_PRESET
        _controls = midi_save.load_controls(MIDI_DEFAULT_PRESET)
        _renumber()
        _save_temp()
    return state()


def rename(old, new):
    _ensure_loaded()
    if not old or old == MIDI_DEFAULT_PRESET:
        return {'ok': False, 'error': 'reserved preset'}
    new = _valid_name(new)
    if new is None:
        return {'ok': False, 'error': 'invalid name'}
    if not midi_save.rename(old, new):
        return {'ok': False, 'error': 'rename failed'}
    if MidiScreen._current_preset == old:
        MidiScreen._current_preset = new
        _save_temp()
    return state()
