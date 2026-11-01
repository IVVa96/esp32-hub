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


TYPES = ('—', 'Btn/Sw', 'Virt_sw', 'Pot', 'Encoder')
ACTIVE_TYPES = ('Btn/Sw', 'Virt_sw', 'Pot', 'Encoder')

_MAX_NAME = 24


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
    if not MidiScreen._presets_loaded:
        MidiScreen._load_from_temp_or_preset()
        MidiScreen._presets_loaded = True


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
            MidiScreen._current_preset or MIDI_DEFAULT_PRESET)
    except Exception:
        pass


# ---- state -----------------------------------------------------------
def state():
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
            pair = int(pair)
        except Exception:
            return {'ok': False, 'error': 'encoder needs a second pin'}
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
    _ensure_loaded()
    if name == MIDI_DEFAULT_PRESET:
        MidiScreen._apply_preset(None)
        MidiScreen._current_preset = name
        MidiScreen._dirty = False
        _save_temp()
        MidiScreen._rebuild_all(_host)
        return state()
    pins = midi_save.load(name)
    if pins is None:
        return {'ok': False, 'error': 'preset not found'}
    MidiScreen._apply_preset(pins)
    MidiScreen._current_preset = name
    MidiScreen._dirty = False
    _save_temp()
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
    if not midi_save.save(name, MidiScreen._cfg):
        return {'ok': False, 'error': 'save failed'}
    MidiScreen._current_preset = name
    MidiScreen._dirty = False
    _save_temp()
    return state()


def delete(name):
    _ensure_loaded()
    if not name or name == MIDI_DEFAULT_PRESET:
        return {'ok': False, 'error': 'reserved preset'}
    if not midi_save.delete(name):
        return {'ok': False, 'error': 'delete failed'}
    if MidiScreen._current_preset == name:
        MidiScreen._current_preset = MIDI_DEFAULT_PRESET
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
