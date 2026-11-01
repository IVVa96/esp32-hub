# ======================================================================
# fsapi.py — операции с файлами для проводника
# ======================================================================
import os


def norm(path):
    """Нормализовать путь: всегда от корня, без '.', '..' и двойных '/'."""
    try:
        path = path or '/'
        path = path.replace('\\', '/')
    except Exception:
        path = '/'
    if not path.startswith('/'):
        path = '/' + path
    parts = []
    for part in path.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return '/' + '/'.join(parts)


def join(dirpath, name):
    if dirpath == '/':
        return '/' + name
    return dirpath + '/' + name


def parent(path):
    path = norm(path)
    if path == '/':
        return None
    idx = path.rfind('/')
    if idx <= 0:
        return '/'
    return path[:idx]


def is_dir(path):
    try:
        return bool(os.stat(path)[0] & 0x4000)
    except OSError:
        return False


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def listdir(path):
    path = norm(path)
    entries = []
    for item in os.ilistdir(path):
        name = item[0]
        try:
            d = bool(item[1] & 0x4000)
        except Exception:
            d = False
        if len(item) >= 4:
            size = item[3]
        else:
            try:
                size = os.stat(join(path, name))[6]
            except OSError:
                size = 0
        entries.append({'name': name, 'dir': d, 'size': size})
    entries.sort(key=lambda e: (0 if e['dir'] else 1, e['name'].lower()))
    return entries


def mkdir(path):
    os.mkdir(norm(path))


def remove(path, recursive=False):
    path = norm(path)
    if is_dir(path):
        if not recursive:
            os.rmdir(path)
            return
        for e in listdir(path):
            remove(join(path, e['name']), True)
        os.rmdir(path)
    else:
        os.remove(path)


def rename(old, new):
    old = norm(old)
    new = norm(new)
    if exists(new):
        remove(new, True)
    os.rename(old, new)


def free(path):
    """(свободно, всего) в байтах."""
    try:
        s = os.statvfs(path)
        return s[0] * s[3], s[0] * s[2]
    except OSError:
        return 0, 0
