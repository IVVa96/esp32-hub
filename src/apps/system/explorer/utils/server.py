# ======================================================================
# server.py — HTTP-сервер проводника файлов
# ======================================================================
import asyncio
import os
import json
import time

from apps.system.explorer.utils import fsapi
from apps.system.explorer.utils import mounts
from apps.system.explorer.utils import dns
from apps.system.explorer.config import (
    FILES_HTTP_PORT, WEB_HOST, WEB_PASSWORD,
)
from core import power
from core import web_mode
from core import time_sync
from core import app_registry

_HTML = None
_HTML_PATH = 'apps/system/explorer/utils/index.html'
_PORTAL_PATH = 'web/portal.html'
_LOGIN_PATH = 'web/login.html'
_USB_HELP_PATH = 'apps/system/explorer/utils/usb.html'
_USB_TOOL_PATH = 'apps/system/explorer/utils/usb_tool.py'
_PAGES = {}
_server = None
_SESSIONS = set()
_COOKIE = 'esp_sid'

# Максимальный размер файла, который разрешено открывать/сохранять
# в веб-редакторе (1 МБ).
MAX_EDIT = 1024 * 1024

STATUS = {
    'running': False,
    'mode': None,        # 'sta' / 'ap' / 'usb'
    'ssid': '',
    'ip': '',
    'host': WEB_HOST,
    'port': FILES_HTTP_PORT,
    'error': '',
}


# ----------------------------------------------------------------------
# Утилиты
# ----------------------------------------------------------------------
def _unquote(s):
    if s is None:
        return ''
    if '%' not in s and '+' not in s:
        return s
    out = bytearray()
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '%' and i + 2 < n:
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except Exception:
                pass
        if c == '+':
            out.append(0x20)
        else:
            out.append(ord(c) & 0xFF)
        i += 1
    try:
        return out.decode('utf-8')
    except Exception:
        return s


def parse_query(qs):
    out = {}
    if not qs:
        return out
    for part in qs.split('&'):
        if not part:
            continue
        if '=' in part:
            k, v = part.split('=', 1)
        else:
            k, v = part, ''
        out[_unquote(k)] = _unquote(v)
    return out


def _read_page(path):
    """Прочитать и закешировать HTML-страницу."""
    page = _PAGES.get(path)
    if page is not None:
        return page
    with open(path, 'r') as f:
        page = f.read()
    _PAGES[path] = page
    return page


def _html():
    global _HTML
    if _HTML is None:
        try:
            _HTML = _read_page(_HTML_PATH)
        except Exception as e:
            _HTML = ('<!doctype html><meta charset="utf-8">'
                     '<h1>UI not found</h1><pre>{}</pre>'.format(e))
    return _HTML


def _portal():
    try:
        return _read_page(_PORTAL_PATH)
    except Exception as e:
        return ('<!doctype html><meta charset="utf-8">'
                '<h1>Portal not found</h1><pre>{}</pre>'.format(e))


def _login_page():
    try:
        return _read_page(_LOGIN_PATH)
    except Exception as e:
        return ('<!doctype html><meta charset="utf-8">'
                '<h1>Login page not found</h1><pre>{}</pre>'.format(e))


def _new_session():
    """Создать случайный идентификатор сессии для cookie."""
    try:
        raw = os.urandom(16)
        token = ''.join('{:02x}'.format(b) for b in raw)
    except Exception:
        token = '{:x}{:x}'.format(time.ticks_ms(), time.ticks_us())
    # Держим только последние сессии, чтобы не расти в памяти.
    _SESSIONS.add(token)
    if len(_SESSIONS) > 8:
        _SESSIONS.clear()
        _SESSIONS.add(token)
    return token


def _cookie(headers, name):
    raw = headers.get('cookie', '')
    for part in raw.split(';'):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        if key.strip() == name:
            return value.strip()
    return ''


def _authed(headers):
    return _cookie(headers, _COOKIE) in _SESSIONS


async def _read_body(reader, headers):
    try:
        length = int(headers.get('content-length', '0'))
    except Exception:
        length = 0
    if length <= 0:
        return b''
    if length > 512:
        length = 512
    chunks = []
    left = length
    while left > 0:
        chunk = await reader.read(left)
        if not chunk:
            break
        chunks.append(chunk)
        left -= len(chunk)
    return b''.join(chunks)


def _fmt_size(n):
    try:
        n = int(n)
    except Exception:
        return '?'
    if n < 1024:
        return '{} B'.format(n)
    if n < 1024 * 1024:
        return '{:.1f} KB'.format(n / 1024.0)
    return '{:.1f} MB'.format(n / (1024.0 * 1024.0))


def _json(obj):
    try:
        return json.dumps(obj)
    except Exception:
        return '{}'


def _roots():
    out = [{'id': '/', 'label': 'Internal'}]
    try:
        if mounts.mounted():
            out.append({'id': mounts.SD_ROOT, 'label': 'SD card'})
    except Exception:
        pass
    return out


def _screen_name():
    try:
        from gui.core.ugui import Screen
        cur = Screen.current_screen
        return type(cur).__name__ if cur is not None else ''
    except Exception:
        return ''


def _info():
    free, total = fsapi.free('/')
    hh, mm = time_sync.now_hm()
    data = {
        'ok': True,
        'title': 'ESP32 Files',
        'roots': _roots(),
        'free': free,
        'total': total,
        'mode': STATUS['mode'],
        'ssid': STATUS['ssid'],
        'ip': STATUS['ip'],
        'host': STATUS['host'],
        'dns': dns.running(),
        'usb': False,
        'sd': False,
        'screen': _screen_name(),
        'time': '{:02d}:{:02d}'.format(hh, mm),
        'synced': time_sync.is_synced(),
        'web_mode': web_mode.active(),
        'web_dual': web_mode.dual(),
        'size': _fmt_size(free),
        'error': STATUS['error'],
    }
    try:
        data['sd'] = mounts.mounted()
        if data['sd']:
            sf, st = fsapi.free(mounts.SD_ROOT)
            data['sd_free'] = sf
            data['sd_total'] = st
            data['sd_size'] = _fmt_size(sf)
    except Exception:
        pass
    return data


def _apps():
    return {'ok': True, 'apps': app_registry.scan()}


# ----------------------------------------------------------------------
# HTTP ответы
# ----------------------------------------------------------------------
async def _send(writer, code, body=b'', ctype='application/json; charset=utf-8',
                extra=None):
    if isinstance(body, str):
        body = body.encode()
    reasons = {
        200: 'OK', 201: 'Created', 204: 'No Content', 206: 'Partial Content',
        302: 'Found',
        400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
        404: 'Not Found',
        409: 'Conflict', 413: 'Payload Too Large',
        415: 'Unsupported Media Type', 500: 'Internal Server Error',
        507: 'Insufficient Storage',
    }
    head = 'HTTP/1.1 {} {}\r\n'.format(code, reasons.get(code, 'OK'))
    head += 'Content-Type: {}\r\n'.format(ctype)
    head += 'Content-Length: {}\r\n'.format(len(body))
    head += 'Connection: close\r\n'
    head += 'Cache-Control: no-store\r\n'
    if extra:
        for k, v in extra.items():
            head += '{}: {}\r\n'.format(k, v)
    head += '\r\n'
    writer.write(head.encode())
    if body:
        writer.write(body)
    try:
        await writer.drain()
    except Exception:
        pass


async def _json_reply(writer, code, obj):
    await _send(writer, code, _json(obj))


async def _err(writer, code, msg):
    await _json_reply(writer, code, {'ok': False, 'error': msg})


# ----------------------------------------------------------------------
# Маршруты
# ----------------------------------------------------------------------
async def _handle(reader, writer):
    try:
        if not STATUS.get('running'):
            # Сервер остановлен — вежливо закрываем
            await _send(writer, 503, '{"ok":false,"error":"stopped"}')
            return

        line = await reader.readline()
        if not line:
            return
        try:
            text = line.decode().strip()
        except Exception:
            text = str(line)
        parts = text.split()
        if len(parts) < 3:
            await _err(writer, 400, 'bad request')
            return
        method, target, _ver = parts[0], parts[1], parts[2]

        if '?' in target:
            path, qs = target.split('?', 1)
        else:
            path, qs = target, ''
        query = parse_query(qs)

        headers = {}
        while True:
            h = await reader.readline()
            if not h or h == b'\r\n' or h == b'\n':
                break
            try:
                hs = h.decode().strip()
            except Exception:
                continue
            if ':' in hs:
                k, v = hs.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        await _route(method, path, query, headers, reader, writer)
    except Exception as e:
        try:
            await _err(writer, 500, str(e))
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _route(method, path, query, headers, reader, writer):
    # --- вход в веб-интерфейс ---
    if path == '/login' or path == '/login/':
        if method == 'GET':
            if _authed(headers):
                await _send(writer, 302, b'', extra={'Location': '/'})
            else:
                await _send(writer, 200, _login_page(),
                           'text/html; charset=utf-8')
            return
        if method == 'POST':
            body = await _read_body(reader, headers)
            try:
                form = parse_query(body.decode())
            except Exception:
                form = {}
            if form.get('password', '') == WEB_PASSWORD:
                sid = _new_session()
                cookie = '{}={}; Path=/; HttpOnly; SameSite=Lax'.format(
                    _COOKIE, sid)
                await _send(writer, 302, b'', extra={
                    'Location': '/', 'Set-Cookie': cookie,
                })
            else:
                await asyncio.sleep_ms(400)
                await _send(writer, 302, b'', extra={
                    'Location': '/login?e=1',
                })
            return
        await _err(writer, 400, 'bad login request')
        return

    if path == '/logout' or path == '/logout/':
        sid = _cookie(headers, _COOKIE)
        if sid:
            _SESSIONS.discard(sid)
        await _send(writer, 302, b'', extra={'Location': '/login'})
        return

    if path == '/favicon.ico':
        await _send(writer, 204)
        return

    # Всё остальное — только после входа.
    if not _authed(headers):
        if path.startswith('/api/'):
            await _err(writer, 401, 'auth required')
        else:
            await _send(writer, 302, b'', extra={'Location': '/login'})
        return

    # --- главный портал ---
    if method == 'GET' and (path == '/' or path == '/index.html'
                            or path == '/apps' or path == '/apps/'):
        web_mode.exit()
        await _send(writer, 200, _portal(), 'text/html; charset=utf-8')
        return

    # --- веб-версии приложений: /apps/<name>/ ---
    if method == 'GET' and path.startswith('/apps/'):
        name = path[6:].strip('/')
        if name and '/' not in name:
            page_path = app_registry.web_page(name)
            if page_path:
                try:
                    web_mode.enter(dual=app_registry.web_dual(name))
                    page = _read_page(page_path)
                    await _send(writer, 200, page, 'text/html; charset=utf-8')
                except Exception as e:
                    await _send(writer, 500,
                                '<!doctype html><meta charset="utf-8">'
                                '<h1>Page not found</h1><pre>{}</pre>'.format(e),
                                'text/html; charset=utf-8')
                return
        await _err(writer, 404, 'app not found')
        return

    # --- быстрый переход к проводнику ---
    if method == 'GET' and (path == '/files' or path == '/files/'):
        web_mode.enter(False)
        await _send(writer, 200, _html(), 'text/html; charset=utf-8')
        return

    if method == 'GET' and (path == '/usb' or path == '/usb/'):
        try:
            with open(_USB_HELP_PATH, 'r') as f:
                page = f.read()
        except Exception as e:
            await _send(writer, 500,
                        '<!doctype html><meta charset="utf-8">'
                        '<h1>USB help not found</h1><pre>{}</pre>'.format(e),
                        'text/html; charset=utf-8')
            return
        await _send(writer, 200, page, 'text/html; charset=utf-8')
        return
    if path == '/api/ping':
        await _json_reply(writer, 200, {'ok': True})
        return
    if path == '/api/info':
        await _json_reply(writer, 200, _info())
        return
    if path == '/api/apps':
        await _json_reply(writer, 200, _apps())
        return

    # --- запуск классической версии приложения с платы ---
    if path == '/api/launch' and method == 'POST':
        name = query.get('app', '')
        if not name or app_registry.classic_module(name) is None:
            await _err(writer, 404, 'classic app not found')
            return
        await _json_reply(writer, 200, {'ok': True, 'launch': name})
        try:
            asyncio.create_task(_launch_async(name))
        except Exception:
            pass
        return

    # --- скачать автономный USB-инструмент ---
    if path == '/api/usb-tool':
        try:
            with open(_USB_TOOL_PATH, 'rb') as f:
                data = f.read()
        except Exception as e:
            await _err(writer, 404, 'usb tool: {}'.format(e))
            return
        await _send(writer, 200, data, 'text/x-python; charset=utf-8', {
            'Content-Disposition':
                'attachment; filename="file_explorer.py"',
        })
        return

    # --- список ---
    if path == '/api/list':
        p = fsapi.norm(query.get('path', '/'))
        try:
            entries = fsapi.listdir(p)
        except OSError as e:
            await _err(writer, 404, 'cannot list: {}'.format(e))
            return
        free, total = fsapi.free(p)
        await _json_reply(writer, 200, {
            'ok': True,
            'path': p,
            'parent': fsapi.parent(p),
            'entries': entries,
            'free': free,
            'total': total,
            'size': _fmt_size(free),
        })
        return

    # --- чтение текста для редактора ---
    if path == '/api/file':
        p = fsapi.norm(query.get('path', ''))
        if not fsapi.exists(p) or fsapi.is_dir(p):
            await _err(writer, 404, 'not found')
            return
        try:
            size = os.stat(p)[6]
        except OSError as e:
            await _err(writer, 404, 'not found: {}'.format(e))
            return
        if size > MAX_EDIT:
            await _err(writer, 413, 'too large: max {} bytes'.format(MAX_EDIT))
            return
        try:
            with open(p, 'rb') as f:
                first = f.read(min(4096, size))
                if b'\x00' in first:
                    await _err(writer, 415, 'binary file')
                    return
                writer.write(
                    ('HTTP/1.1 200 OK\r\n'
                     'Content-Type: text/plain; charset=utf-8\r\n'
                     'Content-Length: {}\r\n'
                     'Connection: close\r\n'
                     'Cache-Control: no-store\r\n\r\n'
                     ).format(size).encode())
                left = size
                if first:
                    writer.write(first)
                    left -= len(first)
                while left > 0:
                    chunk = f.read(min(4096, left))
                    if not chunk:
                        break
                    writer.write(chunk)
                    left -= len(chunk)
                    try:
                        await writer.drain()
                    except Exception:
                        pass
        except Exception as e:
            try:
                await _err(writer, 500, str(e))
            except Exception:
                pass
        return

    # --- сохранение текста из редактора ---
    if path == '/api/save' and method == 'POST':
        global _HTML
        p = fsapi.norm(query.get('path', ''))
        if not p or p == '/':
            await _err(writer, 400, 'bad path')
            return
        if fsapi.exists(p) and fsapi.is_dir(p):
            await _err(writer, 400, 'is a directory')
            return
        parent = fsapi.parent(p)
        if not parent or not fsapi.exists(parent) or not fsapi.is_dir(parent):
            await _err(writer, 400, 'bad directory')
            return
        try:
            length = int(headers.get('content-length', '0') or 0)
        except Exception:
            length = 0
        if length < 0 or length > MAX_EDIT:
            await _err(writer, 413, 'too large: max {} bytes'.format(MAX_EDIT))
            return
        try:
            free, _total = fsapi.free(parent)
            if free and length + 4096 > free:
                await _err(writer, 507, 'not enough space')
                return
        except Exception:
            pass
        tmp = p + '.part'
        try:
            left = length
            with open(tmp, 'wb') as f:
                while left > 0:
                    chunk = await reader.read(min(4096, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left > 0:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                await _err(writer, 400, 'incomplete save')
                return
            # Атомарная замена, если ФС это поддерживает.
            try:
                os.rename(tmp, p)
            except OSError:
                try:
                    os.remove(p)
                except Exception:
                    pass
                os.rename(tmp, p)
        except Exception as e:
            try:
                os.remove(tmp)
            except Exception:
                pass
            await _err(writer, 500, 'save: {}'.format(e))
            return
        if p == _HTML_PATH:
            _HTML = None
        _PAGES.pop(p, None)
        await _json_reply(writer, 200, {'ok': True, 'path': p, 'size': length})
        return

    # --- скачивание ---
    if path == '/api/download':
        p = fsapi.norm(query.get('path', ''))
        try:
            size = os.stat(p)[6]
        except OSError:
            await _err(writer, 404, 'not found')
            return
        if fsapi.is_dir(p):
            await _err(writer, 400, 'is a directory')
            return
        start, end = 0, size - 1
        code = 200
        rng = headers.get('range')
        if rng and rng.startswith('bytes='):
            try:
                spec = rng[6:].split(',')[0].strip()
                a, b = spec.split('-', 1)
                if a == '':
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    if b:
                        end = min(size - 1, int(b))
                if start > end or start >= size:
                    raise ValueError('bad range')
                code = 206
            except Exception:
                start, end, code = 0, size - 1, 200
        length = end - start + 1
        name = p.rsplit('/', 1)[-1]
        extra = {
            'Content-Disposition': 'attachment; filename="{}"'.format(
                name.replace('"', '_')),
            'Accept-Ranges': 'bytes',
        }
        if code == 206:
            extra['Content-Range'] = 'bytes {}-{}/{}'.format(start, end, size)
        try:
            with open(p, 'rb') as f:
                f.seek(start)
                left = length
                head = 'HTTP/1.1 {} {}\r\n'.format(
                    code, 'Partial Content' if code == 206 else 'OK')
                head += 'Content-Type: application/octet-stream\r\n'
                head += 'Content-Length: {}\r\n'.format(length)
                head += 'Connection: close\r\n'
                head += 'Cache-Control: no-store\r\n'
                for k, v in extra.items():
                    head += '{}: {}\r\n'.format(k, v)
                head += '\r\n'
                writer.write(head.encode())
                while left > 0:
                    chunk = f.read(min(4096, left))
                    if not chunk:
                        break
                    writer.write(chunk)
                    left -= len(chunk)
                    try:
                        await writer.drain()
                    except Exception:
                        pass
        except Exception as e:
            try:
                await _err(writer, 500, str(e))
            except Exception:
                pass
        return

    # --- загрузка ---
    if path == '/api/upload' and method in ('POST', 'PUT'):
        p = fsapi.norm(query.get('path', '/'))
        name = query.get('name', '').replace('/', '_').replace('\\', '_')
        if not name or name in ('.', '..'):
            await _err(writer, 400, 'bad name')
            return
        if not fsapi.exists(p) or not fsapi.is_dir(p):
            await _err(writer, 400, 'bad directory')
            return
        try:
            length = int(headers.get('content-length', '0'))
        except Exception:
            length = 0
        if length <= 0:
            await _err(writer, 400, 'empty body')
            return
        dst = p.rstrip('/') + '/' + name
        tmp = dst + '.part'
        try:
            left = length
            with open(tmp, 'wb') as f:
                while left > 0:
                    chunk = await reader.read(min(4096, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left > 0:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                await _err(writer, 400, 'incomplete upload')
                return
            fsapi.rename(tmp, dst)
        except Exception as e:
            try:
                os.remove(tmp)
            except Exception:
                pass
            await _err(writer, 500, 'upload: {}'.format(e))
            return
        await _json_reply(writer, 200, {'ok': True, 'path': dst,
                                        'size': length})
        return

    # --- удаление ---
    if path == '/api/delete' and method == 'POST':
        p = fsapi.norm(query.get('path', ''))
        recursive = query.get('recursive', '0') in ('1', 'true', 'yes')
        if p == '/':
            await _err(writer, 400, 'refuse to delete root')
            return
        try:
            fsapi.remove(p, recursive)
        except OSError as e:
            await _err(writer, 500, 'delete: {}'.format(e))
            return
        await _json_reply(writer, 200, {'ok': True})
        return

    # --- создание каталога ---
    if path == '/api/mkdir' and method == 'POST':
        p = fsapi.norm(query.get('path', ''))
        try:
            fsapi.mkdir(p)
        except OSError as e:
            await _err(writer, 409, 'mkdir: {}'.format(e))
            return
        await _json_reply(writer, 200, {'ok': True, 'path': p})
        return

    # --- переименование / перемещение ---
    if path == '/api/rename' and method == 'POST':
        src = fsapi.norm(query.get('path', ''))
        dst = fsapi.norm(query.get('to', ''))
        if not src or not dst:
            await _err(writer, 400, 'bad paths')
            return
        try:
            fsapi.rename(src, dst)
        except OSError as e:
            await _err(writer, 500, 'rename: {}'.format(e))
            return
        await _json_reply(writer, 200, {'ok': True, 'path': dst})
        return

    # --- глубокий сон (время остаётся в RTC, BOOT будит плату) ---
    if path == '/api/sleep' and method == 'POST':
        await _json_reply(writer, 200, {'ok': True, 'sleep': True})
        try:
            asyncio.create_task(_sleep_device())
        except Exception:
            pass
        return

    # --- перезагрузка платы ---
    if path == '/api/reset' and method == 'POST':
        # Сначала отдаём ответ, затем перезагружаемся, чтобы браузер
        # успел получить подтверждение.
        await _json_reply(writer, 200, {'ok': True, 'reset': True})
        try:
            asyncio.create_task(_reboot())
        except Exception:
            pass
        return

    # --- MIDI web app: /api/midi?action=... ---
    if path == '/api/midi':
        try:
            from apps.user.midi.utils import engine as midi_engine
        except Exception as e:
            await _err(writer, 500, 'midi engine: {}'.format(e))
            return
        action = query.get('action', 'state')
        try:
            if action == 'state':
                try:
                    midi_engine.start()
                except Exception:
                    pass
                await _json_reply(writer, 200, midi_engine.state())
            elif action == 'setpin' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.set_pin(
                    query.get('pin'), query.get('type'),
                    query.get('cc'), query.get('ch'),
                    query.get('pair')))
            elif action == 'mode' and method == 'POST':
                await _json_reply(writer, 200,
                                  midi_engine.set_mode(query.get('mode')))
            elif action == 'load' and method == 'POST':
                await _json_reply(writer, 200,
                                  midi_engine.load(query.get('name')))
            elif action == 'save' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.save(
                    query.get('name'),
                    overwrite=query.get('overwrite') == '1'))
            elif action == 'delete' and method == 'POST':
                await _json_reply(writer, 200,
                                  midi_engine.delete(query.get('name')))
            elif action == 'rename' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.rename(
                    query.get('old'), query.get('new')))
            elif action == 'addctl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.add_control(
                    query.get('kind', 'fader')))
            elif action == 'delctl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.remove_control(
                    query.get('id')))
            elif action == 'setctl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.set_control(
                    query.get('id'), query.get('cc'), query.get('ch'),
                    query.get('label')))
            elif action == 'sendctl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.send_control(
                    query.get('id'), query.get('value'),
                    query.get('persist', '1') == '1'))
            elif action == 'movectl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.move_control(
                    query.get('id'), query.get('slot')))
            elif action == 'swapctl' and method == 'POST':
                await _json_reply(writer, 200, midi_engine.swap_control(
                    query.get('id'), query.get('slot')))
            else:
                await _err(writer, 400, 'bad midi action')
        except Exception as e:
            await _err(writer, 500, 'midi: {}'.format(e))
        return

    await _err(writer, 404, 'not found')


# ----------------------------------------------------------------------
# Жизненный цикл
# ----------------------------------------------------------------------
async def _reboot():
    await asyncio.sleep_ms(600)
    try:
        import machine
        machine.reset()
    except Exception as e:
        STATUS['error'] = 'reset: {}'.format(e)


async def _sleep_device():
    # Даём браузеру получить ответ, затем штатная анимация и deep sleep.
    await asyncio.sleep_ms(900)
    try:
        import core.shutdown as shutdown_anim
        await shutdown_anim.run()
    except Exception as e:
        STATUS['error'] = 'sleep: {}'.format(e)


async def _launch_async(name):
    """Переключить экран платы на классическую версию приложения.

    HTTP-сервер при этом продолжает работать: WebScreen.on_hide его
    специально не останавливает.
    """
    await asyncio.sleep_ms(250)
    try:
        from gui.core.ugui import Screen
        from apps.system.explorer.app_web import WebScreen

        # Если экран был выключен веб-режимом — возвращаем его,
        # чтобы classic-приложение было видно.
        web_mode.exit()

        cls = app_registry.load_classic(name)
        if cls is None:
            return
        cur = Screen.current_screen
        if cur is not None and isinstance(cur, cls):
            return
        # Запоминаем, куда вернуться после закрытия WebScreen,
        # чтобы закрытие запущенного из портала приложения не выключало UI.
        if cur is not None and not isinstance(cur, WebScreen):
            WebScreen.return_screen = cur
        cls.return_screen = WebScreen
        Screen.change(cls, Screen.REPLACE)
    except Exception as e:
        STATUS['error'] = 'launch: {}'.format(e)


async def _serve():
    global _server
    host = '0.0.0.0'
    port = STATUS['port']
    try:
        _server = await asyncio.start_server(_handle, host, port)
    except Exception as e:
        STATUS['running'] = False
        STATUS['error'] = 'listen: {}'.format(e)
        return
    STATUS['error'] = ''
    while STATUS['running']:
        await asyncio.sleep_ms(1000)
    try:
        _server.close()
    except Exception:
        pass
    _server = None


def start(mode='sta', ssid='', ip=''):
    STATUS['mode'] = mode
    STATUS['ssid'] = ssid
    STATUS['ip'] = ip
    STATUS['error'] = ''
    # Имя espui.esp: мини-DNS поднимаем сразу, чтобы оно работало
    # и в AP, и в STA (если DNS роутера указывает на плату).
    try:
        dns.start(ip)
    except Exception as e:
        STATUS['error'] = 'dns: {}'.format(e)
    if STATUS['running']:
        power.remember_web(mode, ssid, ip, True)
        return True
    STATUS['running'] = True
    try:
        asyncio.create_task(_serve())
    except Exception as e:
        STATUS['running'] = False
        STATUS['error'] = 'task: {}'.format(e)
        dns.stop()
        return False
    power.remember_web(mode, ssid, ip, True)
    return True


def stop():
    web_mode.exit()
    STATUS['running'] = False
    _SESSIONS.clear()
    power.remember_web(STATUS.get('mode'), STATUS.get('ssid'),
                       STATUS.get('ip'), False)
    try:
        dns.stop()
    except Exception:
        pass
    try:
        if _server is not None:
            _server.close()
    except Exception:
        pass


def running():
    return bool(STATUS.get('running'))
