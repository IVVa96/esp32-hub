# ======================================================================
# app.py — USB-MIDI: пины, каналы, CC, пресеты
# ======================================================================
NAME = 'midi'
# AppScreen = MidiScreen

import hardware_setup
import asyncio
import gc
import time

from gui.core.ugui import ssd, Screen, display
from gui.widgets import Label, Listbox, Button
from gui.core.colors import *

from config import (
    TITLE_Y, TITLE_X, CS_MARGIN,
    LB_Y, LB_X, LB_WIDTH, LB_DLINES, LB_BORDER_COLOR,
    KB_CELL_W, KB_CELL_H, KB_X,
    CLOSE_BTN_X, CLOSE_BTN_Y, CLOSE_BTN_W, CLOSE_BTN_H,
    SCREEN_W, SCREEN_H, _sx, _sy,
)
from apps.user.midi.config import (
    MIDI_DEFAULT_CHANNEL, MIDI_CC_GROUP_COLORS,
    MIDI_AVAILABLE_PINS, MIDI_ADC_PINS,
    MIDI_DEFAULT_PRESET,
    MIDI_LB_DLINES, MIDI_LB_EXTRA,
    PANEL_TOP_GAP, PANEL_TYPE_X, PANEL_TYPE_LBL_OFF,
    PANEL_TYPE_W, PANEL_CC_X, PANEL_CC_OFF, PANEL_CC_W,
    PANEL_CH_X, PANEL_CH_LBL_Y, PANEL_CH_LB_Y, PANEL_CH_W,
    PRESET_BTN_W, PRESET_BTN_H, PRESET_BTN_GAP, PRESET_BTN_Y,
    PW_Y_TITLE, PW_Y_LABEL, PW_Y_INPUT, PW_Y_HINT, PW_KB_Y,
)
from apps.user.midi.utils import hw
from apps.user.midi.utils import ble_midi
from apps.user.midi.utils import save as midi_save
from core.ui import (
    make_writer, place_close_btn, wait_release_all, redraw_status_bar,
    pad_right, return_to,
)
from core.keyboard_widget import Keyboard
from core.logger import error


_LONG_MS      = 1200
_TICK_MS      = 100
_SYNC_TICKS   = 2
_TEMP_TICKS   = 15


def _elems_len(widget, default):
    for attr in ('elements', '_elements'):
        try:
            v = getattr(widget, attr, None)
            if v is not None:
                return len(v)
        except Exception:
            pass
    return default


# ======================================================================
# Listbox пинов
# ======================================================================
class _PinListbox(Listbox):
    def __init__(self, *args, on_edit=None, on_scroll=None, **kwargs):
        self._edit      = False
        self._on_edit   = on_edit
        self._on_scroll = on_scroll
        self._on_draw_markers = None
        self._row_spec = None
        self._marker_top = 0
        super().__init__(*args, **kwargs)

    def _sync_marker_top(self):
        try:
            n = _elems_len(self, len(MIDI_AVAILABLE_PINS))
            d = self.dlines
            v = self.value()
            t = getattr(self, '_top', None)
            if isinstance(t, int) and 0 <= t <= max(0, n - d) \
                    and t <= v < t + d:
                self._marker_top = t
                return
            mt = self._marker_top
            if n <= d:
                self._marker_top = 0
            elif v < mt:
                self._marker_top = v
            elif v >= mt + d:
                self._marker_top = v - d + 1
        except Exception as e:
            error("sync marker top:", e)

    def _redraw_markers(self):
        if self._on_draw_markers:
            try:
                self._on_draw_markers()
            except Exception as e:
                error("markers:", e)

    def show(self):
        # Своя отрисовка: колонки (пин / тип / CC / Ch) стоят на фиксированных
        # пиксельных позициях, поэтому пропорциональный шрифт не «съезжает».
        if not super(Listbox, self).show(False):
            return
        self.ntop = min(self.ntop, self._value)
        self.ntop = max(self.ntop, self._value - self.dlines + 1)
        ntop = self.ntop
        eh = self.entry_height
        nlines = min(self.dlines, len(self.els))
        wri = self.writer
        x_pin = self.col + 2
        x_type = x_pin + wri.stringlen('G00 ')
        x_cc = x_type + _sx(80)
        x_ch = x_cc + wri.stringlen('CC 127  ')
        x_end = self.col + self.width - 2
        fg = self.fontcolor if self.fontcolor is not None else self.fgcolor

        for i in range(nlines):
            idx = ntop + i
            y = self.row + 1 + i * eh
            bg = self.select_color if idx == self._value else self.bgcolor
            display.fill_rect(self.col, y, self.width, eh - 1, bg)
            pin_txt, type_txt, cc_txt, ch_txt, cc_color, ch_color = (
                '', '', '', '', None, None)
            if self._row_spec is not None:
                try:
                    pin_txt, type_txt, cc_txt, ch_txt, cc_color, ch_color = \
                        self._row_spec(idx, MIDI_AVAILABLE_PINS[idx])
                except Exception:
                    pass
            self._seg(x_pin, y, pin_txt, fg, bg, x_type)
            # Тип энкодера (encA 1 / encA 2) красим цветом группы, чтобы
            # обе ноги энкодера явно выделялись.
            type_fg = fg
            if cc_color is not None and type_txt[:3] == 'enc':
                type_fg = cc_color
            self._seg(x_type, y, type_txt, type_fg, bg, x_cc)
            self._seg(x_cc, y, cc_txt,
                      fg if cc_color is None else cc_color, bg, x_ch)
            self._seg(x_ch, y, ch_txt,
                      fg if ch_color is None else ch_color, bg, x_end)

        x = self.col + self.width - 2
        if ntop:
            display.vline(x, self.row, eh - 1, self.fgcolor)
        if ntop + self.dlines < len(self.els):
            y = self.row + (self.dlines - 1) * eh
            display.vline(x, y, eh - 1, self.fgcolor)

    def _seg(self, x, y, text, fg, bg, limit):
        """Нарисовать фрагмент строки, обрезав его по следующей колонке."""
        if not text:
            return
        avail = limit - x
        if avail <= 0:
            return
        wri = self.writer
        try:
            if wri.stringlen(text) > avail:
                pos = 0
                nch = 0
                font = wri.font
                for ch in text:
                    pos += font.get_ch(ch)[2]
                    if pos > avail:
                        break
                    nch += 1
                text = text[:nch]
        except Exception:
            pass
        if text:
            display.print_left(wri, x, y, text, fg, bg)

    def update(self, *args, **kwargs):
        try:
            super().update(*args, **kwargs)
        except Exception as e:
            error("lb update:", e)
        finally:
            self._sync_marker_top()
            self._redraw_markers()

    def do_adj(self, *args, **kwargs):
        if self._edit:
            return
        try:
            super().do_adj(*args, **kwargs)
        except Exception as e:
            error("super do_adj:", e)
            return
        self._sync_marker_top()
        self._redraw_markers()
        if self._on_scroll:
            try:
                self._on_scroll(self.value())
            except Exception as e:
                error("on_scroll:", e)

    def do_sel(self):
        if self._edit:
            self._edit = False
            return
        self._edit = True
        if self._on_edit:
            try:
                self._on_edit(self.value())
            except Exception as e:
                error("on_edit:", e)

    def leave_edit(self):
        self._edit = False


class _ValueListbox(Listbox):
    """Список одного значения (CC, Ch): применение сразу при изменении.

    Направление вращения инвертируется передачей -val в базовый do_adj:
    база уменьшает индекс при val > 0. Раньше это делалось «зеркалом» уже
    после изменения, из-за чего на краях (индекс 0 и последний) значение
    защёлкивалось и не менялось вообще.
    """

    def __init__(self, *args, on_change=None, **kwargs):
        self._on_change = on_change
        super().__init__(*args, **kwargs)

    def do_adj(self, button=None, val=0):
        old = self.value()
        try:
            super().do_adj(button, -val)
        except Exception as e:
            error("listbox do_adj:", e)
            return
        new = self.value()
        if new == old:
            return
        if self._on_change:
            try:
                self._on_change(new)
            except Exception as e:
                error("listbox change:", e)

    def do_sel(self):
        pass


class _CCListbox(_ValueListbox):
    pass


class _ChannelListbox(_ValueListbox):
    pass


# ======================================================================
# MidiScreen
# ======================================================================
class MidiScreen(Screen):
    return_screen = None
    mode = 'wire'          # 'wire' — USB, 'ble' — BLE-MIDI

    _cfg = {
        p: {'type': '—', 'cc': p, 'pair': None,
            'channel': MIDI_DEFAULT_CHANNEL}
        for p in MIDI_AVAILABLE_PINS
    }
    _dirty = False
    _presets_loaded = False
    _current_preset = None
    _components = {}
    _presets_confirm_delete = []

    _TYPE_LIST = ('—', 'Btn/Sw', 'Virt_sw', 'Pot', 'Encoder')
    _CHANNELS  = tuple(str(i) for i in range(1, 17))
    _CC_VALUES = tuple(str(i) for i in range(128))

    # Цвет, выданный значению (CC или каналу) один раз, больше не меняется,
    # пока значение остаётся тем же. Живёт на уровне класса, чтобы цвета
    # не пересчитывались при повторном открытии экрана.
    _cc_color_map = {}
    _ch_color_map = {}
    _cc_color_next = 0
    _ch_color_next = 0

    def __init__(self):
        super().__init__()
        ssd.fill(0)

        if not MidiScreen._presets_loaded:
            MidiScreen._load_from_temp_or_preset()
            MidiScreen._presets_loaded = True

        hw.start(MidiScreen.mode)

        self.wri      = make_writer()
        self._alive   = True
        self._sel_pin = MIDI_AVAILABLE_PINS[0]
        self._syncing = False
        self._last_type_idx = -1
        self._last_cc_val   = None
        self._last_ch_idx   = -1

        # Пин-энкодер, ожидающий выбора пары (или None)
        self._pending_pair_for = None

        self._pending_pins = set()
        self._pending_sync = False
        self._sync_ticks   = 0
        self._temp_ticks   = 0

        self._ch_focused  = False
        self._timer_task  = None
        self._poll_task   = None

        self._cc_groups_cache = None
        self._ch_groups_cache = None
        self._cc_stale = False
        # Индексы строк, которые сейчас покрашены цветом CC-группы
        self._painted_rows = set()

        self.title_lbl = Label(
            self.wri, TITLE_Y, TITLE_X, _sx(150))
        self.title_lbl.value('MIDI')

        self.preset_lbl = Label(
            self.wri, TITLE_Y + _sy(14), TITLE_X, _sx(150))
        self._update_title()

        # Индикатор режима работы справа в заголовке: USB / BLE wait / BLE ok
        self._mode_txt = None
        self.mode_lbl = Label(
            self.wri, TITLE_Y, _sx(150), _sx(64), justify=2)
        self._update_mode_label()

        self._elements = [self._row_text(p) for p in MIDI_AVAILABLE_PINS]

        lb_y_actual = LB_Y + MIDI_LB_EXTRA

        self.lb = _PinListbox(
            self.wri, lb_y_actual, LB_X,
            elements=self._elements,
            dlines=MIDI_LB_DLINES,
            width=LB_WIDTH,
            bdcolor=LB_BORDER_COLOR,
            callback=lambda *_: None,
            on_scroll=self._on_lb,
            on_edit=self._on_pick,
        )
        self.lb._row_spec = self._pin_row

        try:
            h4 = self.lb.height
        except AttributeError:
            h4 = MIDI_LB_DLINES * 13 + 2
        panel_h  = _sy(75)
        reserved = PRESET_BTN_H + _sy(16) + panel_h
        max_y    = SCREEN_H - reserved - h4

        if lb_y_actual > max_y:
            lb_y_actual = max(LB_Y, max_y)
            try:
                self.lb.row = lb_y_actual
                self.lb.show()
            except Exception as e:
                error("lb reposition:", e)

        panel_y = self.lb.row + self.lb.height + PANEL_TOP_GAP

        Label(self.wri, panel_y, PANEL_TYPE_X, 'Type:')
        self._type_elems = list(self._dd_elements_for(self._sel_pin))
        self.type_lb = Listbox(
            self.wri, panel_y + PANEL_TYPE_LBL_OFF, PANEL_TYPE_X,
            elements=self._type_elems,
            dlines=1,
            width=PANEL_TYPE_W,
            bdcolor=LB_BORDER_COLOR,
            callback=self._on_type_lb,
        )

        Label(self.wri, panel_y, PANEL_CC_X, 'CC:')
        self.cc_lb = _CCListbox(
            self.wri, panel_y + PANEL_CC_OFF, PANEL_CC_X,
            elements=list(self._CC_VALUES),
            dlines=1,
            width=PANEL_CC_W,
            bdcolor=LB_BORDER_COLOR,
            callback=lambda *_: None,
            on_change=self._on_cc,
        )

        Label(self.wri, panel_y + PANEL_CH_LBL_Y, PANEL_CH_X, 'Ch:')
        self._ch_elems = list(self._CHANNELS)
        self.ch_lb = _ChannelListbox(
            self.wri, panel_y + PANEL_CH_LB_Y, PANEL_CH_X,
            elements=self._ch_elems,
            dlines=1,
            width=PANEL_CH_W,
            bdcolor=LB_BORDER_COLOR,
            callback=lambda *_: None,
            on_change=self._on_channel_apply,
        )

        def _on_list(*_a, **_k):
            asyncio.create_task(self._do_list_presets())
        def _on_save(*_a, **_k):
            asyncio.create_task(self._do_save_now())
        def _on_save_as(*_a, **_k):
            asyncio.create_task(self._do_save_as())

        _x1 = CS_MARGIN
        _x2 = _x1 + PRESET_BTN_W + PRESET_BTN_GAP
        _x3 = _x2 + PRESET_BTN_W + PRESET_BTN_GAP
        self.list_btn = Button(
            self.wri, PRESET_BTN_Y, _x1,
            text='LIST', callback=_on_list,
            width=PRESET_BTN_W, height=PRESET_BTN_H,
        )
        self.save_btn = Button(
            self.wri, PRESET_BTN_Y, _x2,
            text='SAVE', callback=_on_save,
            width=PRESET_BTN_W, height=PRESET_BTN_H,
        )
        self.saveas_btn = Button(
            self.wri, PRESET_BTN_Y, _x3,
            text='SAVE AS', callback=_on_save_as,
            width=PRESET_BTN_W, height=PRESET_BTN_H,
        )

        def _on_close(*_a, **_k):
            asyncio.create_task(self._do_close())
        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X,
                         text='X', callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

        self._wrap_enter(self.lb,         is_ch=False)
        self._wrap_enter(self.type_lb,    is_ch=False)
        self._wrap_enter(self.cc_lb,      is_ch=False)
        self._wrap_enter(self.ch_lb,      is_ch=True)
        self._wrap_enter(self.list_btn,   is_ch=False)
        self._wrap_enter(self.save_btn,   is_ch=False)
        self._wrap_enter(self.saveas_btn, is_ch=False)
        self._wrap_enter(self.cb,         is_ch=False)

        self._sync_edit_panel()

    def _wrap_enter(self, widget, is_ch):
        orig = getattr(widget, 'enter', None)
        if orig is None:
            return
        def _new_enter():
            self._ch_focused = is_ch
            try:
                return orig()
            except Exception:
                pass
        try:
            widget.enter = _new_enter
        except Exception as e:
            error("wrap enter:", e)

    def _update_title(self):
        try:
            name = MidiScreen._current_preset or 'default'
            suffix = ' *' if MidiScreen._dirty else ''
            self.preset_lbl.value('{}{}'.format(name, suffix))
        except Exception as e:
            error("update_title:", e)

    def _update_mode_label(self):
        try:
            if MidiScreen.mode == 'ble':
                if not ble_midi.available():
                    txt = 'BLE n/a'
                elif ble_midi.is_connected():
                    txt = 'BLE ok'
                else:
                    txt = 'BLE wait'
            else:
                txt = 'USB'
            if txt == self._mode_txt:
                return
            self._mode_txt = txt
            self.mode_lbl.value(txt)
            self.mode_lbl.show()
        except Exception as e:
            error("mode label:", e)

    def _mark_dirty(self):
        if not MidiScreen._dirty:
            MidiScreen._dirty = True
            self._update_title()
        self._temp_ticks = 0

    async def _flash_title(self, text, duration_ms=1500):
        try:
            self.preset_lbl.value(text)
        except Exception:
            pass
        await asyncio.sleep_ms(duration_ms)
        if self._alive:
            self._update_title()

    @staticmethod
    def _pins_equal(a, b):
        """Сравнить два словаря пинов, игнорируя 'encB' (их нет в файлах)."""
        if a is None or b is None:
            return a is b

        def _clean(d):
            return {k: v for k, v in d.items() if v.get('type') != 'encB'}

        ca = _clean(a)
        cb = _clean(b)
        if set(ca.keys()) != set(cb.keys()):
            return False
        for k in ca:
            if ca[k].get('type')    != cb[k].get('type'):
                return False
            if ca[k].get('cc')      != cb[k].get('cc'):
                return False
            if ca[k].get('channel') != cb[k].get('channel'):
                return False
            if ca[k].get('pair')    != cb[k].get('pair'):
                return False
        return True

    @staticmethod
    def _default_pins():
        return {
            p: {'type': '—', 'cc': p, 'pair': None,
                'channel': MIDI_DEFAULT_CHANNEL}
            for p in MIDI_AVAILABLE_PINS
        }

    @classmethod
    def _apply_preset(cls, pins):
        # Загрузили другой пресет — значения изменились, цвета можно
        # назначать заново.
        MidiScreen._cc_color_map = {}
        MidiScreen._ch_color_map = {}
        MidiScreen._cc_color_next = 0
        MidiScreen._ch_color_next = 0
        for p in MIDI_AVAILABLE_PINS:
            cls._cfg[p]['type']    = '—'
            cls._cfg[p]['cc']      = p
            cls._cfg[p]['pair']    = None
            cls._cfg[p]['channel'] = MIDI_DEFAULT_CHANNEL
        if pins is None:
            return
        for pin, entry in pins.items():
            if pin not in MIDI_AVAILABLE_PINS:
                continue
            t = entry['type']
            if t == 'Button':
                t = 'Btn/Sw'
            elif t == 'Virt Sw':
                t = 'Virt_sw'
            if t == 'Pot' and pin not in MIDI_ADC_PINS:
                continue
            pair = entry.get('pair')
            if pair is not None and \
                    (pair == pin or pair not in MIDI_AVAILABLE_PINS):
                pair = None
            cls._cfg[pin]['type']    = t
            cls._cfg[pin]['cc']      = entry['cc']
            cls._cfg[pin]['pair']    = pair
            cls._cfg[pin]['channel'] = entry.get('channel',
                                                 MIDI_DEFAULT_CHANNEL)
        # Восстановить encB-маркеры для пар энкодеров
        used = set()
        for pin in MIDI_AVAILABLE_PINS:
            c = cls._cfg[pin]
            if c['type'] != 'Encoder':
                continue
            pair = c['pair']
            if pair is None or pair in used or \
                    cls._cfg[pair]['type'] not in ('—', 'encB'):
                c['type'] = '—'
                c['pair'] = None
                continue
            used.add(pair)
            cls._cfg[pair]['type']    = 'encB'
            cls._cfg[pair]['pair']    = pin
            cls._cfg[pair]['cc']      = c['cc']
            cls._cfg[pair]['channel'] = c['channel']

    @classmethod
    def _load_from_temp_or_preset(cls):
        base, pins = midi_save.load_temp()

        # Есть временное сохранение — применяем его, даже если base == 'default'.
        # Иначе пары энкодеров сбрасываются при каждом открытии экрана.
        if pins is not None:
            cls._current_preset = base or MIDI_DEFAULT_PRESET
            cls._apply_preset(pins)
            file_pins = midi_save.load(base) if base and base != MIDI_DEFAULT_PRESET else None
            if file_pins is not None:
                cls._dirty = not cls._pins_equal(pins, file_pins)
            else:
                cls._dirty = True
            return

        base = MIDI_DEFAULT_PRESET
        cls._current_preset = base
        cls._apply_preset(None)
        cls._dirty = False
        try:
            midi_save.save_temp(cls._cfg, base)
        except Exception as e:
            error("init temp:", e)

    def _next_preset_name(self):
        try:
            t = time.localtime()
            base = 'p_{:02d}{:02d}{:02d}_{:02d}{:02d}'.format(
                t[0] % 100, t[1], t[2], t[3], t[4])
        except Exception:
            base = 'preset'
        existing = set(midi_save.list_saves())
        name = base
        n = 2
        while name in existing:
            name = '{}_{}'.format(base, n)
            n += 1
        return name

    async def _do_list_presets(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetListScreen)

    async def _do_save_now(self):
        await wait_release_all()
        name = MidiScreen._current_preset or MIDI_DEFAULT_PRESET
        if name == MIDI_DEFAULT_PRESET:
            await self._do_save_as()
            return
        try:
            midi_save.save_temp(MidiScreen._cfg, name)
        except Exception:
            pass
        ok = midi_save.save(name, MidiScreen._cfg)
        if ok:
            MidiScreen._dirty = False
            asyncio.create_task(self._flash_title('Saved'))
        else:
            asyncio.create_task(self._flash_title('Save failed'))

    async def _do_save_as(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        PresetSaveScreen.initial_name = self._next_preset_name()
        Screen.change(PresetSaveScreen)

    def _pair_peers(self, pin):
        """Вернуть (мастер, slave) для пина-участника пары, иначе (None, None)."""
        cfg = self._cfg.get(pin)
        if cfg is None:
            return None, None
        pair = cfg.get('pair')
        if pair is None:
            return None, None
        t = cfg['type']
        if t == 'Encoder':
            return pin, pair
        if t == 'encB':
            return pair, pin
        return None, None

    def _pair_targets(self, pin):
        """Пины, на которые действует правка CC/Ch для данного пина."""
        master, slave = self._pair_peers(pin)
        if master is None:
            return [pin]
        return [master, slave]

    def _pair_letter_and_leg(self, pin):
        """Вернуть (буква_пары, нога) для пина энкодера, или (None, None).

        Буква — порядок пары (A=1-я пара, B=2-я, ...).
        Нога — 1 для мастера (Encoder), 2 для slave (encB).
        """
        master, slave = self._pair_peers(pin)
        if master is None:
            return None, None
        leg = 1 if pin == master else 2
        pairs = []
        for p in MIDI_AVAILABLE_PINS:
            c = self._cfg[p]
            if c['type'] == 'Encoder' and c['pair'] is not None:
                pairs.append((p, c['pair']))
        pairs.sort()
        for i, (m, s) in enumerate(pairs, 1):
            if (master, slave) == (m, s):
                letter = chr(ord('A') + i - 1)
                return letter, leg
        return None, None

    def _row_text(self, pin):
        cfg = self._cfg[pin]
        t = cfg['type']
        if t == 'Encoder':
            if cfg['pair'] is not None:
                letter, leg = self._pair_letter_and_leg(pin)
                t = 'enc{} {}'.format(letter, leg) if letter else 'enc? ?'
            elif self._pending_pair_for == pin:
                t = 'Enc…'
        elif t == 'encB':
            letter, leg = self._pair_letter_and_leg(pin)
            t = 'enc{} {}'.format(letter, leg) if letter else 'enc? ?'
        t_pad = pad_right(self.wri, t, _sx(80))
        return 'G{:02d} {} CC {}  Ch {}'.format(
            pin, t_pad, cfg['cc'], cfg['channel'])

    def _invalidate_cc_cache(self):
        self._cc_groups_cache = None
        self._ch_groups_cache = None
        # Группы могли измениться, а текст строк — нет: нужна полная перерисовка,
        # иначе цвет у пинов, которые не менялись, останется старым.
        self._cc_stale = True

    @classmethod
    def _group_colors(cls, values, mapping, counter_attr):
        """Выдать цвет каждому значению один раз и запомнить его.

        Значения, которым цвет уже выдан, не перекрашиваются при появлении
        новых групп. Новой группе достаётся первый свободный цвет палитры.
        """
        colors = MIDI_CC_GROUP_COLORS
        n = len(colors)
        # Зарезервированные цвета: даже если значение сейчас не в группе,
        # его цвет не отдаём другому значению — иначе при возврате
        # (например, 3 -> 4 -> снова 3) два разных значения совпадут.
        reserved = set(mapping.values())
        active = set()
        for v in values:
            idx = mapping.get(v)
            if idx is not None:
                active.add(idx)
        counter = getattr(cls, counter_attr, 0)
        present = set(values)
        # sorted() — чтобы порядок выдачи цветов не зависел от hash-порядка
        # словаря в MicroPython.
        for v in sorted(values):
            if v in mapping:
                continue
            idx = None
            for i in range(n):
                if i not in reserved:
                    idx = i
                    break
            if idx is None:                     # все цвета закреплены
                for i in range(n):
                    if i not in active:
                        idx = i
                        break
                if idx is not None:
                    # Цвет принадлежал значению, которого сейчас нет.
                    # Снимаем бронь, иначе при его возврате будет дубль.
                    for k in list(mapping.keys()):
                        if mapping[k] == idx and k not in present:
                            del mapping[k]
            if idx is None:                     # все цвета реально видны
                idx = counter % n
                counter += 1
            mapping[v] = idx
            reserved.add(idx)
            active.add(idx)
        setattr(cls, counter_attr, counter)
        return {v: mapping[v] for v in values}

    def _cc_groups(self):
        if self._cc_groups_cache is not None:
            return self._cc_groups_cache
        counts = {}
        for p in MIDI_AVAILABLE_PINS:
            cfg = self._cfg[p]
            cc = cfg['cc']
            counts[cc] = counts.get(cc, 0) + 1
        values = [cc for cc in counts if counts[cc] > 1]
        groups = MidiScreen._group_colors(
            values, MidiScreen._cc_color_map, '_cc_color_next')
        self._cc_groups_cache = groups
        return groups

    def _channel_groups(self):
        if getattr(self, '_ch_groups_cache', None) is not None:
            return self._ch_groups_cache
        counts = {}
        for p in MIDI_AVAILABLE_PINS:
            cfg = self._cfg[p]
            # Канал по умолчанию не участвует. «Нетронутость» пина здесь
            # не важна: если канал отличается от дефолтного, его задал
            # пользователь — даже у пина с type '—' и CC = номеру пина.
            ch = cfg['channel']
            if ch == MIDI_DEFAULT_CHANNEL:
                continue
            counts[ch] = counts.get(ch, 0) + 1
        groups = MidiScreen._group_colors(
            list(counts.keys()), MidiScreen._ch_color_map, '_ch_color_next')
        self._ch_groups_cache = groups
        return groups

    def _clip_text(self, lb, text, max_w):
        """Обрезать текст по ширине так же, как это делает Listbox.show()."""
        if not text or max_w <= 0:
            return ''
        try:
            if self.wri.stringlen(text) <= max_w:
                return text
            font = self.wri.font
            pos = 0
            nch = 0
            for ch in text:
                pos += font.get_ch(ch)[2]
                if pos > max_w:
                    break
                nch += 1
            return text[:nch]
        except Exception:
            return text

    def _redraw_row_standard(self, lb, row_idx, bgcolor=None, fgcolor=None):
        """Перерисовать строку стандартным цветом (чтобы стереть старый окрас enc).
        Если fgcolor задан — рисует текст этим цветом."""
        if bgcolor is None:
            bgcolor = lb.bgcolor
        if fgcolor is None:
            fgcolor = lb.fontcolor if lb.fontcolor is not None else lb.fgcolor
        try:
            ntop = getattr(lb, 'ntop', 0)
            actual_idx = ntop + row_idx
            if actual_idx >= len(lb.els):
                return
            text = lb.els[actual_idx] if lb.simple else lb.els[actual_idx][0]
            entry_h = getattr(lb, 'entry_height', 13)
            y = lb.row + 1 + row_idx * entry_h
            x = lb.col + 2
            ssd.fill_rect(lb.col, y, lb.width - 4, entry_h - 1, bgcolor)
            text = self._clip_text(lb, text, lb.width - 4)
            display.print_left(self.wri, x, y, text, fgcolor, bgcolor)
        except Exception:
            pass

    def _put_segment(self, lb, x, limit, y, text, fg, bgcolor):
        """Нарисовать сегмент текста, вернуть новую x."""
        avail = limit - x
        if avail <= 0 or not text:
            return x
        s = self._clip_text(lb, text, avail)
        if not s:
            return x
        display.print_left(self.wri, x, y, s, fg, bgcolor)
        return x + self.wri.stringlen(s)

    def _color_spans(self, lb, row_idx, text, spans, bgcolor=None):
        """Перерисовать строку: сегменты из spans — своими цветами, остальное — стандартными.

        spans — отсортированный список (start, end, fgcolor, bgcolor|None).
        Если у сегмента задан bgcolor, он рисуется цветной плашкой."""
        if bgcolor is None:
            bgcolor = lb.bgcolor
        try:
            ntop = getattr(lb, 'ntop', 0)
            actual_idx = ntop + row_idx
            if actual_idx >= len(lb.els):
                return
            entry_h = getattr(lb, 'entry_height', 13)
            y = lb.row + 1 + row_idx * entry_h
            # Полностью затираем строку фоном
            ssd.fill_rect(lb.col, y, lb.width - 4, entry_h - 1, bgcolor)
            fg = lb.fontcolor if lb.fontcolor is not None else lb.fgcolor
            x = lb.col + 2
            limit = x + lb.width - 4
            pos = 0
            for start, end, seg_fg, seg_bg in spans:
                if start > pos:
                    x = self._put_segment(
                        lb, x, limit, y, text[pos:start], fg, bgcolor)
                if seg_bg is None:
                    seg_bg = bgcolor
                x = self._put_segment(
                    lb, x, limit, y, text[start:end], seg_fg, seg_bg)
                pos = end
            if pos < len(text):
                self._put_segment(lb, x, limit, y, text[pos:], fg, bgcolor)
        except Exception:
            pass

    def _pin_cc_color(self, pin, groups):
        """Цвет группы для пина (или None, если пин не входит в группу)."""
        cfg = self._cfg[pin]
        colors = MIDI_CC_GROUP_COLORS
        cc = cfg['cc']
        if cc in groups:
            return colors[groups[cc] % len(colors)]
        return None

    def _pin_ch_color(self, pin):
        """Цвет группы каналов (None для канала по умолчанию и одиночек)."""
        ch = self._cfg[pin]['channel']
        if ch == MIDI_DEFAULT_CHANNEL:
            return None
        groups = self._channel_groups()
        if ch in groups:
            colors = MIDI_CC_GROUP_COLORS
            return colors[groups[ch] % len(colors)]
        return None

    def _pin_row(self, idx, pin):
        """(метка пина, тип, CC, Ch, цвет CC, цвет Ch) — для отрисовки строки."""
        cfg = self._cfg[pin]
        t = cfg['type']
        if t == 'Encoder':
            if cfg['pair'] is not None:
                letter, leg = self._pair_letter_and_leg(pin)
                t = 'enc{} {}'.format(letter, leg) if letter else 'enc? ?'
            elif self._pending_pair_for == pin:
                t = 'Enc…'
        elif t == 'encB':
            letter, leg = self._pair_letter_and_leg(pin)
            t = 'enc{} {}'.format(letter, leg) if letter else 'enc? ?'
        return (
            'G{:02d}'.format(pin),
            t,
            'CC {}'.format(cfg['cc']),
            'Ch {}'.format(cfg['channel']),
            self._pin_cc_color(pin, self._cc_groups()),
            self._pin_ch_color(pin),
        )

    def _draw_cc_markers(self):
        try:
            lb = getattr(self, 'lb', None)
            if lb is None:
                return
            painted = getattr(self, '_painted_rows', None)
            if painted is None:
                painted = self._painted_rows = set()
            groups = self._cc_groups()
            d = lb.dlines
            top = getattr(lb, 'ntop', 0)
            if not isinstance(top, int) or top < 0:
                top = 0
            n = len(MIDI_AVAILABLE_PINS)
            colors = MIDI_CC_GROUP_COLORS
            cur_idx = getattr(lb, '_value', -1)

            def _row_bg(idx):
                return lb.select_color if idx == cur_idx else lb.bgcolor

            if not groups:
                # Групп нет — убрать ранее нарисованный окрас
                for i in range(d):
                    idx = top + i
                    if idx >= n:
                        break
                    if idx in painted:
                        self._redraw_row_standard(lb, i, _row_bg(idx))
                        painted.discard(idx)
                return

            for i in range(d):
                idx = top + i
                if idx >= n:
                    break
                pin = MIDI_AVAILABLE_PINS[idx]
                cfg = self._cfg[pin]
                text = lb.els[idx] if lb.simple else lb.els[idx][0]

                color = self._pin_cc_color(pin, groups)

                spans = []
                if color is not None:
                    # CC красим у всех строк одинаково — это и есть метка группы
                    cc_txt = 'CC {}'.format(cfg['cc'])
                    cpos = text.find(' {}  Ch'.format(cc_txt))
                    if cpos >= 0:
                        cpos += 1
                        spans.append((cpos, cpos + len(cc_txt), color, None))
                    # У пар энкодера дополнительно красим метку encA 1 / encA 2
                    if cfg['type'] in ('Encoder', 'encB'):
                        letter, leg = self._pair_letter_and_leg(pin)
                        if letter:
                            lbl = 'enc{} {}'.format(letter, leg)
                            lpos = text.find(lbl)
                            if lpos >= 0:
                                spans.append((lpos, lpos + len(lbl), color, None))

                if spans:
                    spans.sort()
                    self._color_spans(lb, i, text, spans, _row_bg(idx))
                    painted.add(idx)
                elif idx in painted:
                    # Строка больше не в группе — вернуть стандартный вид
                    self._redraw_row_standard(lb, i, _row_bg(idx))
                    painted.discard(idx)
        except Exception as e:
            error("cc markers:", e)

    def _lb_update(self):
        try:
            # lb.update() -> show() -> _redraw_markers() сам перерисует окрас
            self.lb.update()
        except Exception as e:
            error("lb update:", e)

    def _queue_refresh(self, pin):
        self._pending_pins.add(pin)

    def _flush_pending(self):
        if not self._pending_pins:
            if getattr(self, '_cc_stale', False):
                self._cc_stale = False
                self._lb_update()
            return
        try:
            changed = False
            for pin in self._pending_pins:
                try:
                    idx = MIDI_AVAILABLE_PINS.index(pin)
                    new_text = self._row_text(pin)
                    if self._elements[idx] != new_text:
                        self._elements[idx] = new_text
                        changed = True
                except Exception:
                    pass
            self._pending_pins.clear()
            if changed or getattr(self, '_cc_stale', False):
                self._cc_stale = False
                self._lb_update()
        except Exception as e:
            error("flush pending:", e)

    async def _timer_loop(self):
        while self._alive:
            await asyncio.sleep_ms(_TICK_MS)
            if not self._alive:
                return
            if self._pending_sync:
                self._sync_ticks += 1
                if self._sync_ticks >= _SYNC_TICKS:
                    self._sync_ticks = 0
                    self._pending_sync = False
                    try:
                        self._sync_edit_panel()
                    except Exception as e:
                        error("sync:", e)
            else:
                self._sync_ticks = 0
            self._flush_pending()
            self._update_mode_label()
            if MidiScreen._dirty and self._pending_pair_for is None:
                self._temp_ticks += 1
                if self._temp_ticks >= _TEMP_TICKS:
                    self._temp_ticks = 0
                    try:
                        base = (MidiScreen._current_preset
                                or MIDI_DEFAULT_PRESET)
                        midi_save.save_temp(MidiScreen._cfg, base)
                    except Exception as e:
                        error("temp save:", e)
            else:
                self._temp_ticks = 0

    def _on_lb(self, idx):
        try:
            if idx < 0 or idx >= len(MIDI_AVAILABLE_PINS):
                return
            self._sel_pin = MIDI_AVAILABLE_PINS[idx]
            self._pending_sync = True
            self._sync_ticks = 0
        except Exception as e:
            error("on_lb:", e)

    def _on_pick(self, idx):
        """sel нажатие на строке списка пинов."""
        try:
            if idx < 0 or idx >= len(MIDI_AVAILABLE_PINS):
                return
            selected = MIDI_AVAILABLE_PINS[idx]

            # Активен режим выбора пары для энкодера
            if self._pending_pair_for is not None:
                self._handle_pair_selection(selected)
                return

            self._sel_pin = selected
            self._pending_sync = False
            self._sync_edit_panel()
            asyncio.create_task(self._focus_type())
        except Exception as e:
            error("on_pick:", e)

    def _handle_pair_selection(self, selected):
        """Пользователь выбрал второй пин для энкодера."""
        master = self._pending_pair_for

        # Отмена: sel на самом энкодере
        if selected == master:
            self._pending_pair_for = None
            cfg = self._cfg[master]
            if cfg['type'] == 'Encoder' and cfg['pair'] is None:
                cfg['type'] = '—'
            self._rebuild(master)
            self._queue_refresh(master)
            self._sync_edit_panel()
            self._update_title()
            return

        # Целевой пин должен быть свободен
        s_cfg = self._cfg[selected]
        if s_cfg['type'] != '—' or selected in MidiScreen._components:
            asyncio.create_task(
                self._flash_title('G{:02d} busy'.format(selected), 800))
            # Остаёмся в режиме выбора, фокус обратно на энкодер
            asyncio.create_task(self._focus_list_for_pair(master))
            return

        # Устанавливаем пару
        m_cfg = self._cfg[master]
        m_cfg['pair'] = selected
        s_cfg['type'] = 'encB'
        s_cfg['pair'] = master
        s_cfg['cc'] = m_cfg['cc']
        s_cfg['channel'] = m_cfg['channel']

        self._pending_pair_for = None
        self._invalidate_cc_cache()
        self._rebuild(master)
        self._queue_refresh(master)
        self._queue_refresh(selected)
        # Курсор в списке стоит на выбранной (второй) ноге — она и есть цель
        # для последующих правок типа/CC/Ch, а не мастер.
        self._sel_pin = selected
        self._sync_edit_panel()
        self._mark_dirty()
        # Сброс флага редактирования listbox, иначе следующий SEL
        # не вызовет _on_pick (в do_sel при _edit=True только сброс флага)
        try:
            self.lb._edit = False
        except Exception:
            pass
        asyncio.create_task(self._flash_title('Pair OK', 1000))

    async def _focus_type(self):
        await asyncio.sleep_ms(100)
        if not self._alive:
            return
        try:
            self.type_lb.enter()
        except Exception as e:
            error("focus type_lb:", e)

    async def _focus_list_for_pair(self, master):
        await asyncio.sleep_ms(100)
        if not self._alive:
            return
        try:
            idx = MIDI_AVAILABLE_PINS.index(master)
            self.lb.value(idx)
            self.lb.update()
        except Exception:
            pass
        try:
            self.lb._edit = False
        except Exception:
            pass
        # Переводим реальный фокус на список пинов, чтобы SEL/энкодер
        # дальше работали со списком (и можно было выбрать вторую ногу).
        try:
            cs = Screen.current_screen
            if cs is not None:
                cs.move_to(self.lb)
        except Exception as e:
            error("focus list:", e)
        try:
            self.preset_lbl.value(
                'Pair for G{:02d}: pick pin + sel'.format(master))
        except Exception:
            pass

    def _dd_elements_for(self, pin):
        if pin in MIDI_ADC_PINS:
            return list(self._TYPE_LIST)
        return [t for t in self._TYPE_LIST if t != 'Pot']

    def _sync_edit_panel(self):
        if self._sel_pin is None:
            return
        self._syncing = True
        try:
            pin = self._sel_pin
            cfg = self._cfg[pin]
            new_elems = self._dd_elements_for(pin)

            if list(self._type_elems) != new_elems:
                self._type_elems.clear()
                self._type_elems.extend(new_elems)
                try:
                    self.type_lb.update()
                except Exception as e:
                    error("type_lb.update:", e)
                self._last_type_idx = -1

            t = cfg['type']
            # encB — служебный тип второй ноги энкодера, не отображается в списке типов.
            # Не сбрасываем его, иначе пара энкодера «слетает» при пролистывании.
            if t not in new_elems and t != 'encB':
                t = '—'
                cfg['type'] = t
                self._rebuild(pin)
                self._queue_refresh(pin)

            # Вторая нога пары — это тоже режим Encoder, показываем его в панели
            shown_t = 'Encoder' if t == 'encB' else t
            try:
                idx = new_elems.index(shown_t)
            except ValueError:
                idx = 0
            if idx != self._last_type_idx:
                try:
                    self.type_lb.value(idx)
                except Exception as e:
                    error("type_lb.value:", e)
                self._last_type_idx = idx

            cc = cfg['cc']
            if cc != self._last_cc_val:
                try:
                    self.cc_lb.value(cc)
                except Exception as e:
                    error("cc_lb.value:", e)
                self._last_cc_val = cc

            ch_idx = cfg['channel'] - 1
            if ch_idx != self._last_ch_idx:
                try:
                    self.ch_lb.value(ch_idx)
                except Exception as e:
                    error("ch_lb.value:", e)
                self._last_ch_idx = ch_idx
        finally:
            self._syncing = False

    def _on_type_lb(self, lb, *_a):
        if self._syncing or self._sel_pin is None:
            return
        try:
            idx = lb.value()
        except Exception:
            return
        target = self._dd_elements_for(self._sel_pin)
        if idx < 0 or idx >= len(target):
            return
        t = target[idx]
        if t == 'Pot' and self._sel_pin not in MIDI_ADC_PINS:
            return
        cfg = self._cfg[self._sel_pin]
        # Вторая нога уже работает как энкодер: повторный выбор Encoder не должен
        # распускать пару (иначе SEL на encB ломает энкодер).
        if cfg['type'] == 'encB' and t == 'Encoder':
            return
        # Разрешаем повторный выбор Encoder, если пара ещё не выбрана
        if cfg['type'] == t and \
                not (t == 'Encoder' and cfg.get('pair') is None):
            return
        self._set_type(self._sel_pin, t)

    def _detach_pair(self, pin):
        """Распустить пару, в которой участвует pin.

        Оба пина (мастер и вторая нога) снова становятся свободными ('—').
        Возвращает список затронутых пинов.
        """
        master, slave = self._pair_peers(pin)
        if master is None:
            cfg = self._cfg[pin]
            if cfg['type'] == 'encB':
                # Осиротевшая вторая нога — просто освобождаем
                cfg['type'] = '—'
                cfg['pair'] = None
                self._queue_refresh(pin)
                return [pin]
            return []
        for p in (master, slave):
            c = self._cfg[p]
            c['type'] = '—'
            c['pair'] = None
        self._rebuild(master)
        self._rebuild(slave)
        for p in (master, slave):
            self._queue_refresh(p)
        self._invalidate_cc_cache()
        return [master, slave]

    def _set_type(self, pin, t):
        if t == 'Pot' and pin not in MIDI_ADC_PINS:
            return

        # Вторая нога пары уже в режиме энкодера — не распускать пару
        # Если пин — вторая нога энкодера (encB), и мы пытаемся назначить ему режим 'Encoder',
        # то ничего не делаем. Это предотвращает отмену пары, если её пин уже настроен как Encoder.
        # Сам режим Encoder для второй ноги должен устанавливаться только через мастер-ногу.
        if t == 'Encoder' and self._cfg[pin]['type'] == 'encB':
            return

        # Отменить/завершить незаконченный выбор пары
        pending = self._pending_pair_for
        if pending is not None and (pending != pin or t != 'Encoder'):
            if pending != pin:
                prev = self._cfg.get(pending)
                if prev and prev['type'] == 'Encoder' and \
                        prev['pair'] is None:
                    prev['type'] = '—'
                    self._rebuild(pending)
                    self._queue_refresh(pending)
            self._pending_pair_for = None
            self._update_title()

        cfg = self._cfg[pin]
        cur = cfg['type']

        # Распустить существующую пару (мастер или вторая нога)
        if cur == 'encB' or (cur == 'Encoder' and cfg['pair'] is not None):
            self._detach_pair(pin)

        if t == 'Encoder':
            # Не искать пару авто: установить 'Encoder' без пары,
            # перевести фокус на список пинов для выбора второго пина.
            cfg['type'] = 'Encoder'
            cfg['pair'] = None
            self._invalidate_cc_cache()
            self._rebuild(pin)             # ничего не создаст (pair=None)
            self._queue_refresh(pin)
            self._pending_pair_for = pin
            self._sel_pin = pin
            self._sync_edit_panel()
            asyncio.create_task(self._focus_list_for_pair(pin))
            return

        cfg['type'] = t
        self._invalidate_cc_cache()
        self._rebuild(pin)
        self._queue_refresh(pin)
        self._sync_edit_panel()
        self._mark_dirty()

    def _next_free_pin(self, exclude):
        """Оставлено для обратной совместимости (не используется в UI)."""
        for p in MIDI_AVAILABLE_PINS:
            if p == exclude:
                continue
            if self._cfg[p]['type'] == '—' and \
                    p not in MidiScreen._components:
                return p
        return None

    def _on_cc(self, idx):
        if self._syncing or self._sel_pin is None:
            return
        cc = max(0, min(127, idx))
        targets = self._pair_targets(self._sel_pin)
        changed = False
        for p in targets:
            c = self._cfg[p]
            if c['cc'] != cc:
                c['cc'] = cc
                changed = True
        if not changed:
            return
        # Компонент существует только у мастера пары (у encB его нет)
        comp = MidiScreen._components.get(targets[0])
        if comp is not None:
            try:
                comp.cc = cc
            except Exception:
                pass
        self._invalidate_cc_cache()
        self._last_cc_val = cc
        for p in targets:
            self._queue_refresh(p)
        self._mark_dirty()

    def _apply_channel_to_pin(self, pin, ch_user):
        targets = self._pair_targets(pin)
        changed = False
        for p in targets:
            c = self._cfg[p]
            if c['channel'] != ch_user:
                c['channel'] = ch_user
                changed = True
        if not changed:
            return False
        comp = MidiScreen._components.get(targets[0])
        if comp is not None:
            try:
                comp.channel = (ch_user - 1) & 0x0F
            except Exception:
                pass
        return True

    def _on_channel_apply(self, idx):
        if self._syncing or self._sel_pin is None:
            return
        pin = self._sel_pin
        ch_user = idx + 1
        if self._apply_channel_to_pin(pin, ch_user):
            self._invalidate_cc_cache()
            for p in self._pair_targets(pin):
                self._queue_refresh(p)
            self._sync_edit_panel()
            self._mark_dirty()

    def _on_channel_apply_all(self, idx):
        ch_user = idx + 1
        changed = False
        for p in MIDI_AVAILABLE_PINS:
            if self._apply_channel_to_pin(p, ch_user):
                changed = True
        if changed:
            self._invalidate_cc_cache()
            for p in MIDI_AVAILABLE_PINS:
                self._queue_refresh(p)
            self._sync_edit_panel()
            self._mark_dirty()

    async def _poll_sel(self):
        prev = 1
        press_time = 0
        press_on_ch = False
        triggered = False
        while self._alive:
            try:
                v = hardware_setup.sel.value()
            except Exception:
                v = 1

            if v == 0 and prev == 1:
                press_time = time.ticks_ms()
                press_on_ch = self._ch_focused
                triggered = False

            if v == 0 and press_on_ch and not triggered:
                try:
                    held = time.ticks_diff(time.ticks_ms(), press_time)
                    if held >= _LONG_MS:
                        triggered = True
                        idx = self.ch_lb.value()
                        self._on_channel_apply_all(idx)
                except Exception as e:
                    error("hold trigger:", e)

            if v == 1 and prev == 0:
                if press_on_ch and not triggered:
                    try:
                        idx = self.ch_lb.value()
                        self._on_channel_apply(idx)
                    except Exception as e:
                        error("sel apply:", e)
                press_on_ch = False
                triggered = False

            prev = v
            await asyncio.sleep_ms(30)

    def _rebuild(self, pin):
        old = MidiScreen._components.pop(pin, None)
        if old:
            try:
                old.stop()
            except Exception:
                pass
        cfg = self._cfg[pin]
        t = cfg['type']
        if t in ('—', 'encB'):
            return
        ch = (cfg.get('channel', MIDI_DEFAULT_CHANNEL) - 1) & 0x0F
        try:
            if t == 'Btn/Sw':
                MidiScreen._components[pin] = hw.ButtonInput(
                    pin, cfg['cc'], ch)
            elif t == 'Virt_sw':
                MidiScreen._components[pin] = hw.VirtSwInput(
                    pin, cfg['cc'], ch)
            elif t == 'Pot':
                if pin not in MIDI_ADC_PINS:
                    raise ValueError('not ADC')
                MidiScreen._components[pin] = hw.PotInput(
                    pin, cfg['cc'], ch)
            elif t == 'Encoder':
                b = cfg['pair']
                if b is None:
                    # Пары ещё нет — компонент не создаём (ждём выбора)
                    return
                MidiScreen._components[pin] = hw.EncoderInput(
                    pin, b, cfg['cc'], ch)
        except Exception as e:
            error('rebuild GPIO{}:'.format(pin), e)
            cfg['type'] = '—'
            pair = cfg['pair']
            cfg['pair'] = None
            # Не оставлять осиротевшую вторую ногу энкодера
            if pair is not None:
                p_cfg = self._cfg.get(pair)
                if p_cfg is not None and p_cfg['type'] == 'encB':
                    p_cfg['type'] = '—'
                    p_cfg['pair'] = None
                    self._queue_refresh(pair)
            self._queue_refresh(pin)

    def _stop_all(self):
        for p in list(MidiScreen._components):
            c = MidiScreen._components.pop(p, None)
            if c:
                try:
                    c.stop()
                except Exception:
                    pass

    def _rebuild_all(self):
        self._stop_all()
        for p in MIDI_AVAILABLE_PINS:
            if self._cfg[p]['type'] in ('Btn/Sw', 'Virt_sw', 'Pot', 'Encoder'):
                self._rebuild(p)

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        self._alive = True

        # Пересчёт звёздочки (с игнором encB внутри _pins_equal)
        name = MidiScreen._current_preset or MIDI_DEFAULT_PRESET
        if name == MIDI_DEFAULT_PRESET:
            MidiScreen._dirty = not MidiScreen._pins_equal(
                MidiScreen._cfg, MidiScreen._default_pins())
        elif midi_save.exists(name):
            file_pins = midi_save.load(name)
            if file_pins is not None:
                MidiScreen._dirty = not MidiScreen._pins_equal(
                    MidiScreen._cfg, file_pins)
            else:
                MidiScreen._dirty = True
        else:
            MidiScreen._dirty = True

        redraw_status_bar()
        place_close_btn(self.cb)
        self._rebuild_all()

        self._last_type_idx = -1
        self._last_cc_val   = None
        self._last_ch_idx   = -1
        self._cc_groups_cache = None
        self._sync_edit_panel()

        for i, pin in enumerate(MIDI_AVAILABLE_PINS):
            try:
                self._elements[i] = self._row_text(pin)
            except Exception:
                pass
        self._lb_update()

        self._update_title()

        try:
            self.lb._edit = False
            self.lb.enter()
        except Exception as e:
            error("after_open focus:", e)

        if self._timer_task is None or self._timer_task.done():
            self._timer_task = asyncio.create_task(self._timer_loop())
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_sel())

    def on_hide(self):
        # Сброс незавершённого выбора пары энкодера
        if self._pending_pair_for is not None:
            master = self._pending_pair_for
            self._pending_pair_for = None
            cfg = self._cfg.get(master)
            if cfg and cfg['type'] == 'Encoder' and cfg['pair'] is None:
                cfg['type'] = '—'
                try:
                    self._rebuild(master)
                except Exception:
                    pass

        if MidiScreen._dirty:
            try:
                base = MidiScreen._current_preset or MIDI_DEFAULT_PRESET
                midi_save.save_temp(MidiScreen._cfg, base)
            except Exception:
                pass
        self._alive = False
        for attr in ('_timer_task', '_poll_task'):
            t = getattr(self, attr, None)
            setattr(self, attr, None)
            if t and not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass
        try:
            self.lb.leave_edit()
        except Exception:
            pass
        self._stop_all()
        gc.collect()

    async def _do_close(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        tgt = MidiScreen.return_screen
        MidiScreen.return_screen = None
        return_to(self, tgt)


# ======================================================================
# Preset save
# ======================================================================
class PresetSaveScreen(Screen):
    return_screen = None
    initial_name = ''

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        Label(self.wri, PW_Y_TITLE, CS_MARGIN, 'SAVE PRESET')
        Label(self.wri, PW_Y_LABEL, CS_MARGIN, 'NAME:')

        init = PresetSaveScreen.initial_name or ''
        self.name_lbl = Label(self.wri, PW_Y_INPUT, CS_MARGIN,
                              ssd.width - 2 * CS_MARGIN)
        self.name_lbl.value(init)
        self.hint_lbl = Label(self.wri, PW_Y_HINT, CS_MARGIN,
                              ssd.width - 2 * CS_MARGIN)
        self.hint_lbl.value('OK to save' if init else 'Enter name, then OK')

        def kb_cb(action, text):
            if action == 'CHANGED':
                try:
                    self._show_name(text)
                except Exception:
                    pass
            elif action == 'OK':
                self._on_ok(text)
            elif action == 'CANCEL':
                self._on_cancel()

        self.kb = Keyboard(
            self.wri, PW_KB_Y, KB_X,
            cell_w=KB_CELL_W, cell_h=KB_CELL_H,
            callback=kb_cb, show_saved=False,
        )
        self.kb.cursor_r = 5
        self.kb.cursor_c = 0
        self.kb.enter()

    def _show_name(self, text):
        s = text or ''
        max_w = ssd.width - 2 * CS_MARGIN
        if self.wri.stringlen(s) > max_w:
            while s and self.wri.stringlen(s) > max_w:
                s = s[:-1]
            s = s + '…'
        self.name_lbl.value(s)
        self.hint_lbl.value('')

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        if self.kb is None:
            return
        init = PresetSaveScreen.initial_name or ''
        PresetSaveScreen.initial_name = ''
        self.kb.text = init
        self.kb.shift = False
        self.kb.cursor_r = 5
        self.kb.cursor_c = 0
        try:
            self.name_lbl.value(init)
            self.hint_lbl.value(
                'OK to save' if init else 'Enter name, then OK')
        except Exception:
            pass
        self.kb.show()
        self.kb.enter()

    def on_hide(self):
        if self.kb is not None:
            try:
                self.kb.stop_poll()
            except Exception:
                pass
        try:
            super().on_hide()
        except Exception:
            pass

    def _on_ok(self, text):
        name = (text or '').strip()
        if not name:
            try:
                self.hint_lbl.value('Name is empty')
            except Exception:
                pass
            return
        if '/' in name or '\\' in name or name.startswith('_'):
            try:
                self.hint_lbl.value('Invalid name')
            except Exception:
                pass
            return
        if name == MIDI_DEFAULT_PRESET:
            try:
                self.hint_lbl.value('Reserved name')
            except Exception:
                pass
            return
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        try:
            midi_save.save_temp(MidiScreen._cfg, name)
        except Exception:
            pass
        if midi_save.save(name, MidiScreen._cfg):
            MidiScreen._current_preset = name
            MidiScreen._dirty = False
            asyncio.create_task(self._goto_back())
        else:
            try:
                self.hint_lbl.value('Save failed')
            except Exception:
                pass

    def _on_cancel(self):
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        asyncio.create_task(self._goto_back())

    async def _goto_back(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(MidiScreen)


# ======================================================================
# Preset rename
# ======================================================================
class PresetRenameScreen(Screen):
    return_screen = None
    old_name = ''
    initial_name = ''

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        Label(self.wri, PW_Y_TITLE, CS_MARGIN, 'RENAME PRESET')
        Label(self.wri, PW_Y_LABEL, CS_MARGIN, 'NEW NAME:')

        init = PresetRenameScreen.initial_name or ''
        self.name_lbl = Label(self.wri, PW_Y_INPUT, CS_MARGIN,
                              ssd.width - 2 * CS_MARGIN)
        self.name_lbl.value(init)
        self.hint_lbl = Label(self.wri, PW_Y_HINT, CS_MARGIN,
                              ssd.width - 2 * CS_MARGIN)
        self.hint_lbl.value('OK to rename')

        def kb_cb(action, text):
            if action == 'CHANGED':
                try:
                    self._show_name(text)
                except Exception:
                    pass
            elif action == 'OK':
                self._on_ok(text)
            elif action == 'CANCEL':
                self._on_cancel()

        self.kb = Keyboard(
            self.wri, PW_KB_Y, KB_X,
            cell_w=KB_CELL_W, cell_h=KB_CELL_H,
            callback=kb_cb, show_saved=False,
        )
        self.kb.cursor_r = 5
        self.kb.cursor_c = 0
        self.kb.enter()

    def _show_name(self, text):
        s = text or ''
        max_w = ssd.width - 2 * CS_MARGIN
        if self.wri.stringlen(s) > max_w:
            while s and self.wri.stringlen(s) > max_w:
                s = s[:-1]
            s = s + '…'
        self.name_lbl.value(s)
        self.hint_lbl.value('')

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        if self.kb is None:
            return
        init = PresetRenameScreen.initial_name or ''
        PresetRenameScreen.initial_name = ''
        self.kb.text = init
        self.kb.shift = False
        self.kb.cursor_r = 5
        self.kb.cursor_c = 0
        try:
            self.name_lbl.value(init)
            self.hint_lbl.value('OK to rename')
        except Exception:
            pass
        self.kb.show()
        self.kb.enter()

    def on_hide(self):
        if self.kb is not None:
            try:
                self.kb.stop_poll()
            except Exception:
                pass
        try:
            super().on_hide()
        except Exception:
            pass

    def _on_ok(self, text):
        new_name = (text or '').strip()
        old_name = PresetRenameScreen.old_name or ''
        if not new_name:
            try:
                self.hint_lbl.value('Name is empty')
            except Exception:
                pass
            return
        if '/' in new_name or '\\' in new_name or new_name.startswith('_'):
            try:
                self.hint_lbl.value('Invalid name')
            except Exception:
                pass
            return
        if new_name == MIDI_DEFAULT_PRESET:
            try:
                self.hint_lbl.value('Reserved name')
            except Exception:
                pass
            return
        if new_name == old_name:
            asyncio.create_task(self._goto_back())
            return
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        ok = midi_save.rename(old_name, new_name)
        if ok:
            if MidiScreen._current_preset == old_name:
                MidiScreen._current_preset = new_name
            asyncio.create_task(self._goto_back())
        else:
            try:
                self.hint_lbl.value('Rename failed')
            except Exception:
                pass

    def _on_cancel(self):
        try:
            self.kb.stop_poll()
        except Exception:
            pass
        asyncio.create_task(self._goto_back())

    async def _goto_back(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetListScreen)


# ======================================================================
# Preset list
# ======================================================================
class PresetListScreen(Screen):
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        saves = midi_save.list_saves()
        if MIDI_DEFAULT_PRESET in saves:
            saves.remove(MIDI_DEFAULT_PRESET)
        self.names = [MIDI_DEFAULT_PRESET] + saves
        self.els = list(self.names)

        self.title_lbl = Label(
            self.wri, TITLE_Y, TITLE_X, _sx(150))
        self.title_lbl.value('PRESETS')

        self.lb = Listbox(
            self.wri, LB_Y + _sy(5), LB_X,
            elements=self.els,
            dlines=LB_DLINES - 3,
            width=LB_WIDTH,
            bdcolor=LB_BORDER_COLOR,
            callback=self._on_pick,
        )

        def _on_delete(*_a, **_k):
            asyncio.create_task(self._do_delete())
        def _on_rename(*_a, **_k):
            asyncio.create_task(self._do_rename())
        def _on_select(*_a, **_k):
            asyncio.create_task(self._do_select())

        _by = ssd.height - _sy(28)
        _bw = (LB_WIDTH - 2 * 4) // 3
        self.btn_delete = Button(
            self.wri, _by, LB_X,
            text='DELETE', callback=_on_delete,
            width=_bw, height=_sy(22),
        )
        self.btn_rename = Button(
            self.wri, _by, LB_X + _bw + 4,
            text='RENAME', callback=_on_rename,
            width=_bw, height=_sy(22),
        )
        self.btn_select = Button(
            self.wri, _by, LB_X + 2 * (_bw + 4),
            text='SELECT', callback=_on_select,
            width=_bw, height=_sy(22),
        )

        def _on_close(*_a, **_k):
            asyncio.create_task(self._do_back())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X,
                         text='X', callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def _selected_name(self):
        try:
            idx = self.lb.value()
        except Exception:
            return None
        if idx < 0 or idx >= len(self.names):
            return None
        return self.names[idx]

    async def _flash_status(self, text, duration_ms=1500):
        try:
            self.title_lbl.value(text)
        except Exception:
            pass
        await asyncio.sleep_ms(duration_ms)
        try:
            self.title_lbl.value('PRESETS')
        except Exception:
            pass

    def _on_pick(self, lb, *_a):
        name = self._selected_name()
        if name is None:
            return
        asyncio.create_task(self._do_load(name))

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        place_close_btn(self.cb)

        try:
            self.btn_delete.show()
            self.btn_rename.show()
            self.btn_select.show()
        except Exception:
            pass

        try:
            self.title_lbl.value('PRESETS')
            self.lb.value(0)
            self.lb.update()
        except Exception:
            pass
        try:
            self.lb.enter()
        except Exception as e:
            error("focus lb:", e)

    async def _do_load(self, name):
        if name == MIDI_DEFAULT_PRESET:
            MidiScreen._apply_preset(None)
            MidiScreen._current_preset = name
            MidiScreen._dirty = False
            try:
                midi_save.save_temp(MidiScreen._cfg, name)
            except Exception:
                pass
            await wait_release_all()
            await asyncio.sleep_ms(80)
            Screen.change(MidiScreen)
            return
        pins = midi_save.load(name)
        if pins is None:
            return
        MidiScreen._apply_preset(pins)
        MidiScreen._current_preset = name
        MidiScreen._dirty = False
        try:
            midi_save.save_temp(MidiScreen._cfg, name)
        except Exception:
            pass
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(MidiScreen)

    async def _do_delete(self):
        name = self._selected_name()
        if name is None:
            return
        if name == MIDI_DEFAULT_PRESET:
            await self._flash_status("You can't change default")
            return
        MidiScreen._presets_confirm_delete = [name]
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetConfirmDeleteScreen)

    async def _do_rename(self):
        name = self._selected_name()
        if name is None:
            return
        if name == MIDI_DEFAULT_PRESET:
            await self._flash_status("You can't change default")
            return
        PresetRenameScreen.old_name = name
        PresetRenameScreen.initial_name = name
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetRenameScreen)

    async def _do_select(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetSelectScreen)

    async def _do_back(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(MidiScreen)


# ======================================================================
# Preset select
# ======================================================================
class PresetSelectScreen(Screen):
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        saves = midi_save.list_saves()
        if MIDI_DEFAULT_PRESET in saves:
            saves.remove(MIDI_DEFAULT_PRESET)
        self.names = saves
        self.selected = set()

        self.els = self._build_els()

        Label(self.wri, TITLE_Y, TITLE_X, 'SELECT PRESETS')

        self.lb = Listbox(
            self.wri, LB_Y + _sy(5), LB_X,
            elements=self.els,
            dlines=LB_DLINES - 3,
            width=LB_WIDTH,
            bdcolor=LB_BORDER_COLOR,
            callback=self._on_toggle,
        )

        def _on_cancel(*_a, **_k):
            asyncio.create_task(self._do_back())
        def _on_delete(*_a, **_k):
            asyncio.create_task(self._do_delete())

        _by = ssd.height - _sy(28)
        _bw = (LB_WIDTH - _sx(6)) // 2
        self.btn_cancel = Button(
            self.wri, _by, LB_X,
            text='CANCEL', callback=_on_cancel,
            width=_bw, height=_sy(22),
        )
        self.btn_delete = Button(
            self.wri, _by, LB_X + _bw + _sx(6),
            text='DELETE', callback=_on_delete,
            width=_bw, height=_sy(22),
        )

        def _on_close(*_a, **_k):
            asyncio.create_task(self._do_back())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X,
                         text='X', callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def _build_els(self):
        els = []
        for i, n in enumerate(self.names):
            mark = '[x]' if i in self.selected else '[ ]'
            els.append('{} {}'.format(mark, n))
        if not els:
            els = ['(no presets)']
        return els

    def _on_toggle(self, lb, *_a):
        if not self.names:
            return
        try:
            idx = lb.value()
        except Exception:
            return
        if idx < 0 or idx >= len(self.names):
            return
        if idx in self.selected:
            self.selected.discard(idx)
        else:
            self.selected.add(idx)
        new_els = self._build_els()
        try:
            self.els.clear()
            self.els.extend(new_els)
        except Exception as e:
            error("toggle els:", e)
        try:
            lb.update()
        except Exception as e:
            error("toggle update:", e)

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        place_close_btn(self.cb)

        try:
            self.btn_cancel.show()
            self.btn_delete.show()
        except Exception:
            pass

        try:
            self.lb.value(0)
            self.lb.update()
        except Exception:
            pass

        try:
            self.lb.enter()
        except Exception as e:
            error("focus lb:", e)

    async def _do_delete(self):
        names = [self.names[i] for i in sorted(self.selected)
                 if 0 <= i < len(self.names)]
        if not names:
            return
        MidiScreen._presets_confirm_delete = names
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetConfirmDeleteScreen)

    async def _do_back(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetListScreen)


# ======================================================================
# Preset confirm delete
# ======================================================================
class PresetConfirmDeleteScreen(Screen):
    return_screen = None

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        names = getattr(MidiScreen, '_presets_confirm_delete', []) or []

        Label(self.wri, TITLE_Y, TITLE_X, 'DELETE')
        Label(self.wri, TITLE_Y + _sy(20), CS_MARGIN,
              'Delete {} preset(s)?'.format(len(names)))
        if names:
            preview = ', '.join(names[:3])
            if len(names) > 3:
                preview += '…'
            Label(self.wri, TITLE_Y + _sy(36), CS_MARGIN, preview)

        def _no(*_a, **_k):
            asyncio.create_task(self._do_back_no())
        def _yes(*_a, **_k):
            asyncio.create_task(self._do_yes())

        _by = ssd.height // 2
        _bw = (LB_WIDTH - _sx(6)) // 2
        self.btn_no = Button(
            self.wri, _by, LB_X,
            text='NO', callback=_no,
            width=_bw, height=_sy(28),
        )
        self.btn_yes = Button(
            self.wri, _by, LB_X + _bw + _sx(6),
            text='YES', callback=_yes,
            width=_bw, height=_sy(28),
        )

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        try:
            self.btn_no.enter()
        except Exception as e:
            error("focus no:", e)

    async def _do_back_no(self):
        await wait_release_all()
        await asyncio.sleep_ms(80)
        MidiScreen._presets_confirm_delete = []
        Screen.change(PresetListScreen)

    async def _do_yes(self):
        names = getattr(MidiScreen, '_presets_confirm_delete', []) or []
        for n in names:
            try:
                midi_save.delete(n)
            except Exception:
                pass
        MidiScreen._presets_confirm_delete = []
        await wait_release_all()
        await asyncio.sleep_ms(80)
        Screen.change(PresetListScreen)


# ======================================================================
# ModeSelectScreen — выбор режима работы MIDI (Wire / BLE)
# ======================================================================
class ModeSelectScreen(Screen):
    return_screen = None      # main.py подставит MenuScreen

    _ITEMS = ('Wire / USB', 'BLE / wireless')

    def __init__(self):
        super().__init__()
        ssd.fill(0)
        self.wri = make_writer()

        Label(self.wri, TITLE_Y, TITLE_X, 'MIDI MODE')
        Label(self.wri, TITLE_Y + _sy(14), TITLE_X,
              'Wire = cable, BLE = wireless')

        self.lb = Listbox(
            self.wri, LB_Y + MIDI_LB_EXTRA, LB_X,
            elements=list(self._ITEMS),
            dlines=LB_DLINES - 3,
            width=LB_WIDTH,
            bdcolor=LB_BORDER_COLOR,
            callback=self._on_pick,
        )

        def _on_close(*_a, **_k):
            asyncio.create_task(self._do_close())

        self.cb = Button(self.wri, CLOSE_BTN_Y, CLOSE_BTN_X,
                         text='X', callback=_on_close,
                         width=CLOSE_BTN_W, height=CLOSE_BTN_H)
        place_close_btn(self.cb)

    def _on_pick(self, lb, *_a):
        if getattr(self, '_busy', False):
            return
        try:
            idx = lb.value()
        except Exception:
            return
        self._busy = True
        asyncio.create_task(self._apply_mode(idx))

    async def _apply_mode(self, idx):
        await wait_release_all()
        await asyncio.sleep_ms(60)
        if idx == 1:
            MidiScreen.mode = 'ble'
            try:
                ble_midi.start()
            except Exception as e:
                error("ble start:", e)
        else:
            MidiScreen.mode = 'wire'
            try:
                ble_midi.stop()
            except Exception as e:
                error("ble stop:", e)
        Screen.change(MidiScreen)

    async def _do_close(self):
        try:
            ble_midi.stop()
        except Exception as e:
            error("ble stop:", e)
        await wait_release_all()
        await asyncio.sleep_ms(80)
        target = ModeSelectScreen.return_screen
        if target is not None and target is not ModeSelectScreen:
            ModeSelectScreen.return_screen = None
            return_to(self, target)
        else:
            Screen.back()

    def after_open(self):
        try:
            super().after_open()
        except Exception:
            pass
        redraw_status_bar()
        place_close_btn(self.cb)
        try:
            self.lb.value(0 if MidiScreen.mode == 'wire' else 1)
            self.lb.update()
            self.lb.enter()
        except Exception as e:
            error("mode focus:", e)


MidiScreen.return_screen = ModeSelectScreen
AppScreen = ModeSelectScreen