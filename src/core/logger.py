# ======================================================================
# logger.py — вывод с уровнями отладки
# ======================================================================
from config import DEBUG_LEVEL, LOG_ERROR, LOG_WARN, LOG_INFO, LOG_VERBOSE


def _log(level, prefix, *args):
    if DEBUG_LEVEL < level:
        return
    try:
        print(prefix, *args)
    except Exception:
        pass


def error(*a):   _log(LOG_ERROR,   "[ERR]",  *a)
def warn(*a):    _log(LOG_WARN,    "[WARN]", *a)
def info(*a):    _log(LOG_INFO,    "[INFO]", *a)
def verbose(*a): _log(LOG_VERBOSE, "[VRB]",  *a)