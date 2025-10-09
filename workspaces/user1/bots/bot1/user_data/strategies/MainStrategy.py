import sys, pathlib
# Ascend to locate project root containing backend/app
_p = pathlib.Path(__file__).resolve().parent
_root = None
for _ in range(12):
    if (_p / 'backend' / 'app').is_dir():
        _root = _p
        break
    if _p.parent == _p: break
    _p = _p.parent
if not _root: raise RuntimeError('Cannot locate project root (backend/app) for MainStrategy shim')
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
from backend.app.trading_core.main_strategy import MainStrategy as _CoreMainStrategy
class MainStrategy(_CoreMainStrategy):
    pass
__all__ = ['MainStrategy']
