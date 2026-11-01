# ======================================================================
# classify.py — классификация BLE-устройств по GATT-сервисам
# ======================================================================
from core.logger import verbose, info


SIG_NAMES = {
    0x1800: 'GAP',            0x1801: 'GATT',
    0x1802: 'IMM_ALERT',      0x1803: 'LINK_LOSS',
    0x1805: 'CURRENT_TIME',   0x1809: 'THERMO',
    0x180A: 'DEVICE_INFO',    0x180D: 'HEART_RATE',
    0x180F: 'BATTERY',        0x1811: 'ALERT_NOTIF',
    0x1812: 'HID',            0x1813: 'SCALE',
    0x1814: 'RUNNING_SPEED',  0x1816: 'FITNESS',
    0x1818: 'CYCLING_POWER',  0x181A: 'ENV_SENSING',
    0x181C: 'USER_DATA',      0x181D: 'WEIGHT_SCALE',
}


def uuid_to_int(u):
    try:
        s = str(u).lower()
    except Exception:
        return None
    if len(s) == 4:
        try:
            return int(s, 16)
        except Exception:
            return None
    if (len(s) >= 36
            and s[8:12] == '-0000' and s[12:16] == '-1000'
            and s[16:20] == '-8000' and s[20:24] == '-0080'
            and s[24:28] == '5f9b'):
        try:
            return int(s[4:8], 16)
        except Exception:
            return None
    return None


async def _read_hid_map(hid_svc):
    try:
        chars = await hid_svc.characteristics()
    except Exception:
        return None
    map_char = None
    for ch in chars:
        if uuid_to_int(ch.uuid) == 0x2A4B:
            map_char = ch
            break
    if map_char is None:
        return None
    try:
        data = await map_char.read()
    except Exception:
        return None
    if not data:
        return None
    b = bytes(data)
    has_kbd      = b'\x05\x01\x09\x06' in b
    has_mouse    = b'\x05\x01\x09\x02' in b
    has_consumer = b'\x05\x0c\x09\x01' in b
    if has_kbd and has_mouse:
        return 'HID_COMBO'
    if has_kbd:
        return 'HID_KEYBOARD'
    if has_mouse:
        return 'HID_MOUSE'
    if has_consumer:
        return 'HID_CONSUMER'
    return 'HID'


async def classify_device(services):
    tags = []
    for svc in services:
        v = uuid_to_int(getattr(svc, 'uuid', None))
        if v is not None and v in SIG_NAMES:
            nm = SIG_NAMES[v]
            if nm not in tags:
                tags.append(nm)
    tags_t = tuple(tags)

    dtype = 'UNKNOWN'
    if 'HID' in tags_t:
        for svc in services:
            if uuid_to_int(getattr(svc, 'uuid', None)) == 0x1812:
                dtype = (await _read_hid_map(svc)) or 'HID'
                break
    elif 'HEART_RATE' in tags_t:    dtype = 'HEART_RATE_MONITOR'
    elif 'ENV_SENSING' in tags_t:   dtype = 'ENV_SENSOR'
    elif 'THERMO' in tags_t:        dtype = 'THERMOMETER'
    elif 'WEIGHT_SCALE' in tags_t:  dtype = 'SCALE'
    elif 'CYCLING_POWER' in tags_t: dtype = 'CYCLING_POWER'
    elif 'FITNESS' in tags_t:       dtype = 'FITNESS_TRACKER'
    elif 'BATTERY' in tags_t:       dtype = 'BATTERY_DEVICE'
    elif tags_t:                    dtype = tags_t[0]

    verbose("classify:", tags_t, "->", dtype)
    return tags_t, dtype