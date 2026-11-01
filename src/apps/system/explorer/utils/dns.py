# ======================================================================
# dns.py — мини-DNS и mDNS: espui.esp / espui.local -> IP платы
# ======================================================================
# В режиме AP DHCP ESP32 выдаёт себя как DNS-сервер, поэтому мини-DNS на
# порту 53 отвечает на любой A-запрос адресом платы: http://espui.esp/
# В режиме STA этот же сервер работает как обычный DNS, если прописать
# IP платы в DNS роутера. Дополнительно слушаем mDNS (порт 5353), чтобы
# espui.local находился в сетях с поддержкой mDNS.
#
# asyncio в MicroPython не умеет UDP-эндпоинты, поэтому используем
# неблокирующий сокет и периодический sleep.
import asyncio
import socket
import struct

_TTL = 60
_MCAST = '224.0.0.251'
_IP_ADD_MEMBERSHIP = 35  # lwIP значение для IP_ADD_MEMBERSHIP

_running = False
_task = None
_ip = ''


# ----------------------------------------------------------------------
# Разбор и сборка DNS-пакетов
# ----------------------------------------------------------------------
def _ip_bytes(ip):
    # MicroPython socket не всегда имеет inet_aton
    try:
        a, b, c, d = ip.split('.')
        return bytes((int(a) & 0xFF, int(b) & 0xFF,
                      int(c) & 0xFF, int(d) & 0xFF))
    except Exception:
        return b'\x00\x00\x00\x00'


def _skip_name(data, i):
    n = len(data)
    while i < n:
        ln = data[i]
        if ln == 0:
            return i + 1
        if ln & 0xC0:
            return i + 2
        i += 1 + ln
        if i > n:
            return -1
    return -1


def _question_end(data):
    if len(data) < 12:
        return None
    qd = (data[4] << 8) | data[5]
    if qd < 1:
        return None
    i = _skip_name(data, 12)
    if i < 0 or i + 4 > len(data):
        return None
    qtype = (data[i] << 8) | data[i + 1]
    return i + 4, qtype


def _answer(data, ip):
    q = _question_end(data)
    if q is None:
        return None
    qend, qtype = q
    # 1 = A, 255 = ANY. На AAAA (28) отвечаем пустым ответом.
    an = 1 if qtype in (1, 255) else 0
    out = bytearray()
    out += data[0:2]                  # ID запроса
    out += b'\x81\x80'                # QR=1, RD=1, RA=1
    out += b'\x00\x01'                # QDCOUNT
    out += struct.pack('>H', an)      # ANCOUNT
    out += b'\x00\x00\x00\x00'        # NSCOUNT, ARCOUNT
    out += data[12:qend]              # вопрос как есть
    if an:
        out += b'\xc0\x0c'            # ссылка на имя вопроса
        out += b'\x00\x01'            # TYPE A
        out += b'\x00\x01'            # CLASS IN
        out += struct.pack('>I', _TTL)
        out += b'\x00\x04'
        out += _ip_bytes(ip)
    return bytes(out)


# ----------------------------------------------------------------------
# Сокеты
# ----------------------------------------------------------------------
def _bind(port, multicast, ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    s.bind(('0.0.0.0', port))
    s.setblocking(False)
    if multicast:
        try:
            mreq = _ip_bytes(_MCAST) + _ip_bytes(ip)
            s.setsockopt(socket.IPPROTO_IP, _IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            pass
    return s


async def _listen(sock, ip):
    while _running:
        try:
            data, addr = sock.recvfrom(512)
        except OSError:
            await asyncio.sleep_ms(20)
            continue
        except Exception:
            return
        try:
            # Отвечаем только на запросы (QR=0)
            if data and len(data) >= 12 and (data[2] & 0x80) == 0:
                resp = _answer(data, ip)
                if resp:
                    sock.sendto(resp, addr)
        except Exception:
            pass
        await asyncio.sleep_ms(2)


async def _serve(ip):
    socks = []
    tasks = []
    for port, multicast in ((53, False), (5353, True)):
        try:
            socks.append(_bind(port, multicast, ip))
        except Exception:
            pass
    if not socks:
        return
    try:
        for s in socks:
            tasks.append(asyncio.create_task(_listen(s, ip)))
        while _running:
            await asyncio.sleep_ms(300)
    finally:
        for t in tasks:
            try:
                t.cancel()
            except Exception:
                pass
        for s in socks:
            try:
                s.close()
            except Exception:
                pass


def start(ip):
    global _running, _task, _ip
    if not ip:
        return False
    if _running and _ip == ip and _task is not None:
        return True
    stop()
    _ip = ip
    _running = True
    try:
        _task = asyncio.create_task(_serve(ip))
    except Exception:
        _running = False
        _task = None
        return False
    return True


def stop():
    global _running, _task, _ip
    _running = False
    t = _task
    _task = None
    _ip = ''
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def running():
    return _running
