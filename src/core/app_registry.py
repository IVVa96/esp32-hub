# ======================================================================
# app_registry.py — реестр приложений: classic (app.py) и web (app_web.py)
#
# У приложения может быть одна или две версии:
#   apps/<group>/<name>/app.py      — классическая версия для экрана платы
#   apps/<group>/<name>/app_web.py  — веб-версия для браузера
# Обе версии живут рядом и делят общую папку utils.
# ======================================================================
import os
import sys

SOURCES = ('apps/system', 'apps/user')
CLASSIC_FILE = 'app.py'
WEB_FILE = 'app_web.py'
CLASS_ATTR = 'AppScreen'


def _valid_name(name):
    if not name:
        return False
    c = name[0]
    if not (c.isalpha() or c == '_'):
        return False
    for ch in name[1:]:
        if not (ch.isalpha() or ch.isdigit() or ch == '_'):
            return False
    return True


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _app_dirs():
    """Все папки приложений: (name, dir, group)."""
    out = []
    for base in SOURCES:
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        entries.sort()
        for name in entries:
            if not _valid_name(name):
                continue
            if name.startswith('_') or name.startswith('.'):
                continue
            out.append((name, '{}/{}'.format(base, name), base))
    return out


def _web_title(name, app_dir):
    """TITLE из app_web.py, иначе имя папки."""
    module_path = app_dir.replace('/', '.') + '.app_web'
    try:
        __import__(module_path)
        mod = sys.modules.get(module_path)
        title = getattr(mod, 'TITLE', None)
        if title:
            return str(title)
    except Exception:
        pass
    return name.replace('_', ' ').upper()


def _web_page(name, app_dir):
    """PAGE из app_web.py (относительно папки), иначе utils/index.html."""
    module_path = app_dir.replace('/', '.') + '.app_web'
    rel = 'utils/index.html'
    try:
        __import__(module_path)
        mod = sys.modules.get(module_path)
        page = getattr(mod, 'PAGE', None)
        if page:
            rel = str(page)
    except Exception:
        pass
    return '{}/{}'.format(app_dir, rel)


def _web_dual(name, app_dir):
    """DUAL_MODE из app_web.py: можно ли работать вместе с classic."""
    module_path = app_dir.replace('/', '.') + '.app_web'
    try:
        __import__(module_path)
        mod = sys.modules.get(module_path)
        return bool(getattr(mod, 'DUAL_MODE', False))
    except Exception:
        return False


def scan():
    """Список приложений: name, title, classic, web, dir, url."""
    out = []
    for name, app_dir, _base in _app_dirs():
        classic = _exists('{}/{}'.format(app_dir, CLASSIC_FILE))
        web = _exists('{}/{}'.format(app_dir, WEB_FILE))
        if not (classic or web):
            continue
        out.append({
            'name': name,
            'title': _web_title(name, app_dir) if web else name.replace('_', ' ').upper(),
            'classic': classic,
            'web': web,
            'dual': _web_dual(name, app_dir) if web else False,
            'dir': app_dir,
            'url': '/apps/{}/'.format(name) if web else '',
        })
    return out


def classic_apps():
    """Только приложения с классической версией (для меню на плате)."""
    out = []
    for name, app_dir, _base in _app_dirs():
        if _exists('{}/{}'.format(app_dir, CLASSIC_FILE)):
            out.append((name, app_dir.replace('/', '.') + '.app'))
    return out


def find(name):
    for a in scan():
        if a['name'] == name:
            return a
    return None


def classic_module(name):
    a = find(name)
    if not a or not a['classic']:
        return None
    return a['dir'].replace('/', '.') + '.app'


def web_page(name):
    a = find(name)
    if not a or not a['web']:
        return None
    return _web_page(name, a['dir'])


def web_dual(name):
    """True, если web-версия может работать одновременно с classic."""
    a = find(name)
    if not a or not a['web']:
        return False
    return bool(a.get('dual'))


def load_classic(name):
    """Загрузить класс AppScreen классической версии приложения."""
    module_path = classic_module(name)
    if not module_path:
        return None
    __import__(module_path)
    mod = sys.modules.get(module_path)
    if mod is None:
        return None
    return getattr(mod, CLASS_ATTR, None)
