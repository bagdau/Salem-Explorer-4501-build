# -*- coding: utf-8 -*-
from __future__ import annotations
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QDialog, QFormLayout, QPushButton
from PyQt5.QtCore import Qt, QTimer, QCoreApplication, QElapsedTimer, QUrl, QThread, pyqtSignal, QSize
import os, sys, socket, shutil, time, json, ctypes, threading, logging, logging.handlers, traceback, subprocess, inspect, hashlib, warnings
from pathlib import Path
from datetime import datetime


def _pyqt_site_packages_candidates():
    cands = []
    try:
        import site
        sp = []
        try:
            sp += list(site.getsitepackages())
        except Exception:
            pass
        try:
            up = site.getusersitepackages()
            if isinstance(up, str):
                sp.append(up)
        except Exception:
            pass
        for spath in sp:
            p = Path(spath) / "PyQt5"
            for name in ("Qt5", "Qt"):
                cand = p / name
                if (cand / "bin").exists():
                    cands.append(cand)
    except Exception:
        pass
    la = os.getenv("LOCALAPPDATA")
    if la:
        base = Path(la) / "Programs" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}"
        p = base / "Lib" / "site-packages" / "PyQt5"
        for name in ("Qt5", "Qt"):
            cand = p / name
            if (cand / "bin").exists():
                cands.append(cand)
    seen = set(); out = []
    for x in cands:
        s = str(x.resolve())
        if s not in seen:
            seen.add(s); out.append(Path(s))
    return out

def _candidate_qt_roots(base: Path):
    for c in _pyqt_site_packages_candidates():
        yield c
    yield base / "_internal" / "PyQt5" / "Qt5"
    yield base / "_internal" / "PyQt5" / "Qt"
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        m = Path(meipass)
        for sub in (("PyQt5","Qt5"),("PyQt5","Qt"),("Qt5",),("Qt",)):
            yield m.joinpath(*sub)
    try:
        from PyQt5.QtCore import QLibraryInfo
        pref = Path(QLibraryInfo.location(QLibraryInfo.PrefixPath))
        if (pref / "bin").exists():
            yield pref
    except Exception:
        pass
    try:
        import PyQt5
        pyqt_dir = Path(inspect.getfile(PyQt5)).resolve().parent
        for name in ("Qt5","Qt"):
            cand = pyqt_dir / name
            if (cand / "bin").exists():
                yield cand
    except Exception:
        pass


def _win_version_strings(fields=('CompanyName','ProductName','ProductVersion','FileDescription','LegalCopyright')):
    out = {k: '' for k in fields}
    try:
        if os.name != 'nt':
            return out
        from ctypes import windll, create_unicode_buffer, sizeof, c_void_p, byref, c_uint, c_wchar_p
        exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
        GetFileVersionInfoSizeW = windll.version.GetFileVersionInfoSizeW
        GetFileVersionInfoW = windll.version.GetFileVersionInfoW
        VerQueryValueW = windll.version.VerQueryValueW

        size = GetFileVersionInfoSizeW(c_wchar_p(exe), None)
        if size <= 0:
            return out
        data = create_unicode_buffer(size)
        if not GetFileVersionInfoW(c_wchar_p(exe), 0, size, data):
            return out

        # Получаем таблицу переводов и бежим по ней
        lp = c_void_p(); lsize = c_uint()
        if VerQueryValueW(data, c_wchar_p(r'\VarFileInfo\Translation'), byref(lp), byref(lsize)) and lsize.value >= 4:
            trans = (ctypes.c_ushort * 2).from_address(lp.value)
            lang, codepage = trans[0], trans[1]
            base = f'\\StringFileInfo\\{lang:04x}{codepage:04x}\\'
        else:
            base = f'\\StringFileInfo\\{lang:04x}{codepage:04x}\\'


        for k in fields:
            lp = c_void_p(); lsize = c_uint()
            if VerQueryValueW(data, c_wchar_p(base + k), byref(lp), byref(lsize)) and lp.value:
                out[k] = ctypes.wstring_at(lp.value, lsize.value - 1)
    except Exception:
        pass
    return out

def app_info():
    # Значения по умолчанию (если вдруг ресурсов нет)
    defaults = {
        'CompanyName':       'Salem Software Corporation',
        'ProductName':       'Salem Explorer',
        'ProductVersion':    '4.5.0',
        'FileDescription':   'Salem Explorer Browser',
        'LegalCopyright':    '© 2025 Salem Software Corporation. All rights reserved.'
    }
    meta = _win_version_strings(tuple(defaults.keys()))
    for k, v in defaults.items():
        if not meta.get(k):
            meta[k] = v
    return meta

class StartupInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("О программе — Salem Explorer")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(False)
        self.setFixedWidth(420)

        info = app_info()
        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 12)

        def _lbl(text): 
            l = QLabel(text); l.setTextInteractionFlags(Qt.TextSelectableByMouse); return l

        form.addRow("Продукт:", _lbl(info['ProductName']))
        form.addRow("Версия:",  _lbl(info['ProductVersion']))
        form.addRow("Компания:",_lbl(info['CompanyName']))
        form.addRow("Описание:",_lbl(info['FileDescription']))
        form.addRow("", _lbl(info['LegalCopyright']))

        btn = QPushButton("OK", self); btn.clicked.connect(self.close)
        form.addRow("", btn)

        # авто-закрытие через 2.5 сек., чтобы не мешало запуску
        QTimer.singleShot(2500, self.close)



# ----------------------------------------------------------------------------
# Base paths (NO chdir). All subsequent paths are absolute via ASSETS_ROOT.
# ----------------------------------------------------------------------------

def _bundle_base() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

BASE = _bundle_base()
INTERNAL = BASE / "_internal"
ASSETS_ROOT = INTERNAL if INTERNAL.exists() else BASE

# ----------------------------------------------------------------------------
# Runtime root (where qt_runtime/** lives). Resilient to _internal and _MEIPASS.
# ----------------------------------------------------------------------------

def _pick_rt_root() -> Path:
    candidates: list[Path] = []
    if INTERNAL.exists():
        candidates.append(INTERNAL)
    candidates.append(BASE)
    meipass = Path(getattr(sys, "_MEIPASS", str(BASE)))
    if meipass not in candidates:
        candidates.append(meipass)
    exe_dir = Path(sys.executable).parent
    if exe_dir not in candidates:
        candidates.append(exe_dir)
    for root in candidates:
        if (root / "qt_runtime" / "bin" / "QtWebEngineProcess.exe").exists():
            return root
    return candidates[0]

RUNTIME_ROOT = _pick_rt_root()

# ----------------------------------------------------------------------------
# Logging (always under BASE/logs). No dependency on cwd.
# ----------------------------------------------------------------------------
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^sip$")
warnings.filterwarnings("ignore", message=r".*sipPyTypeDict.*", category=DeprecationWarning)

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG_DIR = BASE / "logs"; LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "launcher.log"

DEV_MODE = (not getattr(sys, "frozen", False)) or ("--dev" in sys.argv) or (os.environ.get("SALEM_DEV") == "1")

def _setup_logging(dev_console: bool):
    root = logging.getLogger()
    root.handlers[:] = []
    root.setLevel(logging.INFO)

    fmt_console = logging.Formatter("%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s", "%H:%M:%S")
    fmt_file    = logging.Formatter("%(asctime)s [%(levelname)s] %(process)d %(threadName)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.handlers.RotatingFileHandler(str(LOG_PATH), maxBytes=10*1024*1024, backupCount=5, encoding="utf-8", delay=True)
    fh.setFormatter(fmt_file)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)

    if dev_console:
        stream = None
        try:
            if getattr(sys, "stdout", None) and hasattr(sys.stdout, "write"):
                stream = sys.stdout
            elif getattr(sys, "__stdout__", None) and hasattr(sys.__stdout__, "write"):
                stream = sys.__stdout__
        except Exception:
            stream = None
        if stream is not None:
            sh = logging.StreamHandler(stream)
            sh.setFormatter(fmt_console)
            sh.setLevel(logging.INFO)
            root.addHandler(sh)

    logging.raiseExceptions = False

_setup_logging(DEV_MODE)
log = logging.getLogger("launcher")


class _StreamToLogger:
    def __init__(self, logger, level): self.logger = logger; self.level = level
    def write(self, message):
        if message and message != "\n":
            for line in str(message).splitlines(): self.logger.log(self.level, line)
    def flush(self): pass
class _TeeToLogger:
    def __init__(self, stream, logger, level): self._stream = stream; self._logger = logger; self._level = level
    def write(self, message):
        try: self._stream.write(message)
        except Exception: pass
        if message and message != "\n":
            for line in str(message).splitlines(): self._logger.log(self._level, line)
    def flush(self):
        try: self._stream.flush()
        except Exception: pass
# DEV: консоль видна, stderr дублируем в лог.
# GUI (PyInstaller console=False): stdout глушим, stderr пишем в лог.
if DEV_MODE:
    if getattr(sys, "__stderr__", None) and hasattr(sys.__stderr__, "write"):
        sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)
else:
    sys.stdout = None
    sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)


def pline(msg: str):
    print(msg, flush=True); log.info(msg)
pline(f"Launcher start {datetime.now().isoformat(timespec='seconds')}")
pline(f"BASE={BASE}  INTERNAL={INTERNAL}  ASSETS_ROOT={ASSETS_ROOT}  RUNTIME_ROOT={RUNTIME_ROOT}")
_last_crash_txt = BASE / "launcher_crash.log"

def _excepthook(exc_type, exc, tb):
    logging.getLogger("crash").exception("Uncaught: %s", exc)
    try:
        with open(_last_crash_txt, "a", encoding="utf-8") as f:
            traceback.print_exception(exc_type, exc, tb, file=f)
    except Exception: pass
sys.excepthook = _excepthook
for noisy in ("urllib3", "requests", "werkzeug", "PyQt5", "WSGI"): logging.getLogger(noisy).setLevel(logging.INFO)
_lock_sock = None

def _single_instance(port: int = 53345) -> bool:
    global _lock_sock
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port)); s.listen(1)
        _lock_sock = s; return True
    except OSError:
        return False
if not _single_instance():
    pline("[FATAL] Another Salem instance is running."); sys.exit(1)
SAFE = ("--safe" in sys.argv) or (os.environ.get("SALEM_SAFE_MODE") == "1")
DEVTOOLS = ("--inspect" in sys.argv) or (os.environ.get("SALEM_DEVTOOLS") == "1")

# ─────────────────────────── PATCH: donors + полное восстановление Qt/bin ───────────────────────────

def _pyqt_site_packages_candidates() -> list[Path]:
    cands: list[Path] = []
    try:
        import site
        spaths: set[str] = set()
        try:
            for p in site.getsitepackages() or []:
                spaths.add(p)
        except Exception:
            pass
        try:
            up = site.getusersitepackages()
            if isinstance(up, str):
                spaths.add(up)
        except Exception:
            pass
        for sp in spaths:
            base = Path(sp) / "PyQt5"
            for name in ("Qt5", "Qt"):
                cand = base / name
                if (cand / "bin").exists():
                    cands.append(cand)
    except Exception:
        pass
    la = os.getenv("LOCALAPPDATA")
    if la:
        base = Path(la) / "Programs" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}"
        pyqt = base / "Lib" / "site-packages" / "PyQt5"
        for name in ("Qt5", "Qt"):
            cand = pyqt / name
            if (cand / "bin").exists():
                cands.append(cand)
    out: list[Path] = []
    seen: set[str] = set()
    for c in cands:
        s = str(c.resolve())
        if s not in seen:
            seen.add(s)
            out.append(Path(s))
    return out

def _candidate_qt_roots(base: Path):
    # 0) Явный поиск в site-packages (системный и пользовательский)
    for c in _pyqt_site_packages_candidates():
        yield c
    # 1) Внутри бандла (_internal)
    yield base / "_internal" / "PyQt5" / "Qt5"
    yield base / "_internal" / "PyQt5" / "Qt"
    # 2) Onefile-времянка (_MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        m = Path(meipass)
        for sub in (("PyQt5", "Qt5"), ("PyQt5", "Qt"), ("Qt5",), ("Qt",)):
            yield m.joinpath(*sub)
    # 3) QLibraryInfo из установленного PyQt5
    try:
        from PyQt5.QtCore import QLibraryInfo
        pref = Path(QLibraryInfo.location(QLibraryInfo.PrefixPath))
        if (pref / "bin").exists():
            yield pref
    except Exception:
        pass
    # 4) Папка модуля PyQt5
    try:
        import PyQt5, inspect as _insp
        pyqt_dir = Path(_insp.getfile(PyQt5)).resolve().parent
        for name in ("Qt5", "Qt"):
            cand = pyqt_dir / name
            if (cand / "bin").exists():
                yield cand
    except Exception:
        pass

def _repair_from_root(root: Path, paths):
    """
    Полное восстановление: копируем не только QtWebEngineProcess.exe и ресурсы,
    но и ВСЕ dll из donor/bin (Qt5*.dll, libEGL.dll, libGLESv2.dll, opengl32sw.dll,
    d3dcompiler_47.dll и прочее), а также plugins/ и qml/.
    """
    binp = root / "bin"
    resp = root / "resources"
    locp = root / "translations" / "qtwebengine_locales"

    # гарантируем структуру целевых каталогов
    paths["bin"].mkdir(parents=True, exist_ok=True)
    paths["res"].mkdir(parents=True, exist_ok=True)
    paths["loc"].mkdir(parents=True, exist_ok=True)
    (paths["base"] / "qt_runtime" / "plugins").mkdir(parents=True, exist_ok=True)
    (paths["base"] / "qt_runtime" / "qml").mkdir(parents=True, exist_ok=True)

    # EXE процесса
    if (binp / "QtWebEngineProcess.exe").exists():
        _copy(binp / "QtWebEngineProcess.exe", paths["exe"])

    # Полный набор DLL из donor/bin
    try:
        for dll in binp.glob("*.dll"):
            try:
                _copy(dll, paths["bin"] / dll.name)
            except Exception:
                pass
        # Иногда встречаются дополнительные файлы (напр. *.pak рядом с bin)
        for extra in ("d3dcompiler_47.dll", "opengl32sw.dll", "libEGL.dll", "libGLESv2.dll"):
            q = binp / extra
            if q.exists():
                try:
                    _copy(q, paths["bin"] / q.name)
                except Exception:
                    pass
    except Exception:
        pass

    # Ресурсы WebEngine
    for name in (
        "icudtl.dat",
        "qtwebengine_resources.pak",
        "qtwebengine_resources_100p.pak",
        "qtwebengine_resources_200p.pak",
        "qtwebengine_devtools_resources.pak",
    ):
        src = resp / name
        if src.exists():
            _copy(src, paths["res"] / name)

    # Локали
    if locp.exists():
        for f in locp.glob("*.pak"):
            _copy(f, paths["loc"] / f.name)

    # Плагины и QML — мерджим деревом
    for sub in ("plugins", "qml"):
        s = root / sub
        d = paths["base"] / "qt_runtime" / sub
        if s.exists():
            try:
                shutil.copytree(str(s), str(d), dirs_exist_ok=True)
            except TypeError:
                # Python <3.8: emulate dirs_exist_ok
                for p in s.rglob("*"):
                    if p.is_file():
                        dst = d / p.relative_to(s)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(str(p), str(dst))
                        except Exception:
                            pass

    # Базовые VC-рантаймы — в bin и рядом с exe на всякий случай
    for dll in VC_DLLS:
        src = binp / dll
        if src.exists():
            for dst in (
                paths["bin"] / dll,
                Path(sys.executable).parent / dll,
                Path(getattr(sys, "_MEIPASS", paths["base"])) / dll,
            ):
                try:
                    if not dst.exists():
                        _copy(src, dst)
                except Exception:
                    pass


# ----------------------------------------------------------------------------
# Env (absolute paths from ASSETS_ROOT). No reliance on cwd.
# ----------------------------------------------------------------------------
_env = {
    "SALEM_ASSETS_ROOT":         str(ASSETS_ROOT),
    "SALEM_IMG_DIR":             str(ASSETS_ROOT / "img" / "icons"),
    "SALEM_MODULES_ICONS":       str(ASSETS_ROOT / "modules" / "icons"),
    "SALEM_EXT":                 "" if SAFE else str(ASSETS_ROOT / "extensions"),
    "SALEM_MODS":                "" if SAFE else str(ASSETS_ROOT / "mods"),
    "SALEM_NEWS_ROOT":           str(ASSETS_ROOT / "news_proxy"),
    "SALEM_NEWS_ICONSPAGE":      str(ASSETS_ROOT / "news_proxy" / "IconsStartPage"),
    "SALEM_NEWS_IMG":            str(ASSETS_ROOT / "news_proxy" / "img"),
    "SALEM_NEWS_STATIC":         str(ASSETS_ROOT / "news_proxy" / "static"),
    "SALEM_NEWS_API":            str(ASSETS_ROOT / "news_proxy" / "static" / "api"),
    "SALEM_NEWS_AVATARS":        str(ASSETS_ROOT / "news_proxy" / "static" / "avatars"),
    "SALEM_NEWS_STATIC_IMG":     str(ASSETS_ROOT / "news_proxy" / "static" / "img"),
    "SALEM_NEWS_UPLOADS":        str(ASSETS_ROOT / "news_proxy" / "static" / "uploads"),
    "SALEM_NEWS_WALLPAPERS":     str(ASSETS_ROOT / "news_proxy" / "static" / "wallpapers"),
}
for k, v in _env.items(): os.environ[k] = v
if DEVTOOLS:
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"
else:
    os.environ.pop("QTWEBENGINE_REMOTE_DEBUGGING", None)

os.environ.setdefault("QT_LOGGING_RULES", "qt.webenginecontext.debug=false;qt.qpa.*=false")

_MIN_SIZES = {
    "QtWebEngineProcess.exe": 256_000,
    "icudtl.dat": 100_000,
    "qtwebengine_resources.pak": 100_000,
    "qtwebengine_resources_100p.pak": 100_000,
    "qtwebengine_resources_200p.pak": 100_000,
    "qtwebengine_devtools_resources.pak": 100_000,
}
VC_DLLS = ("vcruntime140.dll","vcruntime140_1.dll","msvcp140.dll","msvcp140_1.dll","msvcp140_2.dll","concrt140.dll")

# ----------------------------------------------------------------------------
# QtWebEngine runtime: verify, repair, and export env (using RUNTIME_ROOT)
# ----------------------------------------------------------------------------

def _exists_nonempty(p: Path, min_bytes=1):
    try: return p.exists() and p.is_file() and p.stat().st_size >= min_bytes
    except Exception: return False

def _rt_paths(base: Path):
    rt = base / "qt_runtime"
    return {
        "base": base,
        "rt": rt,
        "bin": rt / "bin",
        "res": rt / "resources",
        "loc": rt / "translations" / "qtwebengine_locales",
        "exe": rt / "bin" / "QtWebEngineProcess.exe",
        "conf_root": base / "qt.conf",
        "conf_bin": rt / "bin" / "qt.conf",
        "hashes_json": rt / "resources" / "qt_hashes.json",
    }

def _write_qt_confs(paths):
    try:
        paths["conf_root"].write_text("[Paths]\nPrefix = qt_runtime\n", encoding="utf-8")
        paths["conf_bin"].parent.mkdir(parents=True, exist_ok=True)
        paths["conf_bin"].write_text("[Paths]\nPrefix = ..\n", encoding="utf-8")
    except Exception: pass

def _set_env(paths):
    os.environ["QTWEBENGINEPROCESS_PATH"] = str(paths["exe"])
    os.environ["QT_PLUGIN_PATH"] = str(paths["base"] / "qt_runtime" / "plugins")
    os.environ["QML_IMPORT_PATH"] = str(paths["base"] / "qt_runtime" / "qml")
    os.environ["QML2_IMPORT_PATH"] = os.environ["QML_IMPORT_PATH"]
    os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(paths["base"] / "qt_runtime" / "resources")
    os.environ["QTWEBENGINE_LOCALES"] = str(paths["base"] / "qt_runtime" / "translations" / "qtwebengine_locales")
    prepend = os.pathsep.join(str(p) for p in [paths["bin"], paths["base"]/"qt_runtime"/"plugins", paths["base"]/"qt_runtime"/"qml"] if p.exists())
    os.environ["PATH"] = prepend + os.pathsep + os.environ.get("PATH", "")

def _sha256(p: Path) -> str:
    h = hashlib.sha256();
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def _load_hashes(paths) -> dict[str, str]:
    try:
        j = json.loads(paths["hashes_json"].read_text("utf-8"))
        if isinstance(j, dict):
            return {str(paths["res"]/k if not str(k).endswith(".exe") else paths["bin"]/k): str(v) for k, v in j.items()}
    except Exception: pass
    return {}

def _verify_runtime(paths) -> list[str]:
    missing: list[str] = []
    if not _exists_nonempty(paths["exe"], min_bytes=_MIN_SIZES["QtWebEngineProcess.exe"]): missing.append("QtWebEngineProcess.exe")
    res = paths["res"]; must = [res/"icudtl.dat", res/"qtwebengine_resources.pak", res/"qtwebengine_resources_100p.pak", res/"qtwebengine_resources_200p.pak", res/"qtwebengine_devtools_resources.pak"]
    for f in must:
        if not _exists_nonempty(f, _MIN_SIZES.get(f.name, 100_000)): missing.append(f.name)
    if not (paths["loc"].exists() and any(paths["loc"].glob("*.pak"))): missing.append("qtwebengine_locales/*.pak")
    hashes = _load_hashes(paths); bad_hash = []
    for abs_rel, h in hashes.items():
        p = Path(abs_rel)
        try:
            if not p.exists(): bad_hash.append(Path(abs_rel).name + "(missing)")
            else:
                if _sha256(p).lower() != h.lower(): bad_hash.append(p.name)
        except Exception: bad_hash.append(Path(abs_rel).name)
    if bad_hash: missing += ["bad_hash:" + n for n in bad_hash]
    return missing

def _copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(str(src), str(dst))

def _repair_from_root(root: Path, paths):
    binp = root / "bin"; resp = root / "resources"; locp = root / "translations" / "qtwebengine_locales"
    if (binp / "QtWebEngineProcess.exe").exists(): _copy(binp / "QtWebEngineProcess.exe", paths["exe"])
    for name in ("icudtl.dat","qtwebengine_resources.pak","qtwebengine_resources_100p.pak","qtwebengine_resources_200p.pak","qtwebengine_devtools_resources.pak"):
        if (resp / name).exists(): _copy(resp / name, paths["res"] / name)
    if locp.exists():
        paths["loc"].mkdir(parents=True, exist_ok=True)
        for f in locp.glob("*.pak"): _copy(f, paths["loc"] / f.name)
    for sub in ("plugins","qml"):
        s = root / sub; d = paths["base"]/"qt_runtime"/sub
        if s.exists() and not d.exists(): shutil.copytree(str(s), str(d))
    for dll in VC_DLLS:
        if (binp/dll).exists():
            try:
                _copy(binp/dll, paths["bin"]/dll)
            except Exception: pass

def _candidate_qt_roots(base: Path):
    yield base / "_internal" / "PyQt5" / "Qt5"
    yield base / "_internal" / "PyQt5" / "Qt"
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        m = Path(meipass)
        for sub in (("PyQt5","Qt5"),("PyQt5","Qt"),("Qt5",),("Qt",)): yield m.joinpath(*sub)
    try:
        from PyQt5.QtCore import QLibraryInfo
        pref = Path(QLibraryInfo.location(QLibraryInfo.PrefixPath))
        if (pref / "bin").exists(): yield pref
    except Exception: pass
    try:
        import PyQt5
        pyqt_dir = Path(inspect.getfile(PyQt5)).resolve().parent
        for name in ("Qt5","Qt"):
            cand = pyqt_dir / name
            if (cand / "bin").exists(): yield cand
    except Exception: pass

def _find_loose_exe_candidates(base: Path):
    yield base / "QtWebEngineProcess.exe"
    yield base / "bin" / "QtWebEngineProcess.exe"
    yield base / "qt_runtime" / "QtWebEngineProcess.exe"

def _pickup_loose_exe(paths) -> bool:
    base = paths["base"]
    for f in _find_loose_exe_candidates(base):
        if _exists_nonempty(f, min_bytes=256_000): _copy(f, paths["exe"]); pline(f"[QTWE] picked loose exe: {f} -> {paths['exe']}"); return True
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(p) / "QtWebEngineProcess.exe"
        if _exists_nonempty(cand, min_bytes=256_000): _copy(cand, paths["exe"]); pline(f"[QTWE] picked from PATH: {cand} -> {paths['exe']}"); return True
    return False

def _install_side_by_side(paths):
    exe_src = paths["exe"]
    targets = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass: targets.append(Path(meipass) / "QtWebEngineProcess.exe")
    targets.append(Path(sys.executable).parent / "QtWebEngineProcess.exe")
    for t in targets:
        try:
            if not _exists_nonempty(t, 256_000): _copy(exe_src, t)
        except Exception: pass
    donor_bin = paths["bin"].parent / "bin"
    for dll in VC_DLLS:
        srcs = [paths["bin"]/dll, donor_bin/dll]
        for src in srcs:
            if src.exists():
                for dst in (paths["bin"]/dll, Path(sys.executable).parent/dll, Path(getattr(sys,"_MEIPASS", paths["base"]))/dll):
                    try:
                        if not (dst.exists()): _copy(src, dst)
                    except Exception: pass

def ensure_qt_engine(sleep_between_attempts=1.0):
    root = RUNTIME_ROOT
    paths = _rt_paths(root)
    attempt = 0
    while True:
        attempt += 1
        missing = _verify_runtime(paths)
        if not missing:
            _write_qt_confs(paths)
            _set_env(paths)
            _install_side_by_side(paths)
            pline(f"[QTWE] FOUND at {paths['exe']}  (attempt {attempt})")
            return paths["exe"]
        pline(f"[QTWE] attempt {attempt}: missing {', '.join(missing)}")
        repaired_any = _pickup_loose_exe(paths)
        for rootp in _candidate_qt_roots(root):
            if not (rootp / "bin").exists():
                continue
            pline(f"[QTWE] try donor: {rootp}")
            try:
                _repair_from_root(rootp, paths); repaired_any = True
                if not _verify_runtime(paths): break
            except Exception as e:
                log.error(f"[QTWE] donor repair failed from {rootp}: {e!r}")
        if not _verify_runtime(paths):
            _write_qt_confs(paths); _set_env(paths); _install_side_by_side(paths)
            pline(f"[QTWE] FOUND at {paths['exe']}  (attempt {attempt})")
            return paths["exe"]
        if not repaired_any: pline("[QTWE] no donors; retry…")
        time.sleep(sleep_between_attempts)

# ----------------------------------------------------------------------------
# System dump (after Qt env is ready)
# ----------------------------------------------------------------------------

def _dump_sysinfo():
    pline(f"[SYS] python={sys.version.split()[0]} exe={sys.executable}")
    pline(f"[SYS] base={BASE} internal={INTERNAL} assets={ASSETS_ROOT} runtime={RUNTIME_ROOT}")
    try:
        first = ":".join(str(Path(p)) for p in list(dict.fromkeys(sys.path))[:8])
        pline(f"[SYS] sys.path[:8]={first}")
    except Exception: pass
    env_keys = [k for k in os.environ.keys() if k.startswith("SALEM_") or k.startswith("QT")] + ["PATH"]
    for k in sorted(set(env_keys)):
        v = os.environ.get(k, "");
        if k == "PATH":
            parts = v.split(os.pathsep)
            v = os.pathsep.join(parts[:6]) + ("…" if len(parts) > 6 else "")
        pline(f"[ENV] {k}={v}")

# ----------------------------------------------------------------------------
# Make sure Python can import our modules regardless of cwd
# ----------------------------------------------------------------------------
import importlib, importlib.util, py_compile

def _ensure_modules_on_path():
    for p in (BASE, INTERNAL, ASSETS_ROOT, ASSETS_ROOT/"modules"):
        try:
            if p and p.exists():
                s = str(p)
                if s not in sys.path: sys.path.insert(0, s)
        except Exception: pass

_ensure_modules_on_path()

# ----------------------------------------------------------------------------
# Verify extension modules using absolute paths from ASSETS_ROOT
# ----------------------------------------------------------------------------

def _verify_module_file(mod_name: str, rel_path: str) -> bool:
    p = (ASSETS_ROOT / rel_path)
    tag = f"[EXTCHECK] {mod_name}"
    if not p.exists(): pline(f"{tag} ❌ file not found: {p}"); return False
    try:
        py_compile.compile(str(p), doraise=True); pline(f"{tag} ✅ syntax OK: {p}")
    except Exception as e:
        pline(f"{tag} ❌ syntax error in {p}: {e}"); return False
    try:
        importlib.invalidate_caches(); importlib.import_module(mod_name); pline(f"{tag} ✅ import OK"); return True
    except Exception as e:
        logging.getLogger("extensions").exception(f"{tag} ❌ import failed: {e}"); return False

def verify_browser_modules():
    ok1 = _verify_module_file("modules.extensions_ui",   "modules/extensions_ui.py")
    ok2 = _verify_module_file("modules.extensions_popup", "modules/extensions_popup.py")
    extra = os.environ.get("SALEM_CHECK_MODS", "").strip()
    if extra:
        for name in [x.strip() for x in extra.split(",") if x.strip()]:
            mod_path = name.replace(".", "/") + ".py"; _verify_module_file(name, mod_path)
    if ok1 and ok2: pline("[EXTCHECK] ✅ all extension modules look healthy")
    else: pline("[EXTCHECK] ⚠️ some extension modules failed; see stack above")

# Prepare Qt runtime BEFORE any Qt imports
ensure_qt_engine(); _dump_sysinfo()
verify_browser_modules()

# ----------------------------------------------------------------------------
# Mode detection and Chromium flags
# ----------------------------------------------------------------------------

def _total_ram_gb() -> int:
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        stat = MEMORYSTATUSEX(); stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys // (1024**3))
    except Exception: return 8

def detect_mode() -> str:
    manual = os.environ.get("SALEM_BOOT_MODE", " ").upper()
    if manual in ("FAST-HDD","NORMAL"): return manual
    ram = _total_ram_gb(); cores = os.cpu_count() or 4
    return "FAST-HDD" if (ram <= 8 or cores <= 4) else "NORMAL"

BOOT_MODE = detect_mode(); pline(f"[BOOT] Mode={BOOT_MODE}  RAM≈{_total_ram_gb()}GB  CPU={os.cpu_count()}")

def apply_mode_flags(mode: str):
    flags = ["--no-sandbox","--disable-gpu-sandbox","--no-default-browser-check","--disable-component-update","--disable-domain-reliability","--disable-breakpad","--no-pings"]
    if mode == "FAST-HDD": flags += ["--disable-features=OptimizationHints,InterestFeedContentSuggestions,HeavyAdIntervention","--disable-print-preview","--renderer-process-limit=2","--process-per-site"]
    else: flags += ["--enable-features=NetworkServiceInProcess"]
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)

apply_mode_flags(BOOT_MODE)

# ----------------------------------------------------------------------------
# UI / Qt imports (after runtime ready)
# ----------------------------------------------------------------------------
from PyQt5.QtCore import Qt, QTimer, QCoreApplication, QElapsedTimer, QUrl, QThread, pyqtSignal, QSize
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt5.QtGui import QPixmap, QFont, QMovie, QIcon

GPU_MARKER = ASSETS_ROOT / "gpu_fallback.marker"
USE_SOFT_GL = GPU_MARKER.exists() or ("--softgl" in sys.argv) or (os.environ.get("SALEM_SOFT_GL") == "1")
if USE_SOFT_GL:
    QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True); pline("[GPU] Software OpenGL enabled (marker/flag)")

class Splash(QWidget):
    def __init__(self):
        super().__init__(flags=Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("SalemSplash")
        root = QVBoxLayout(self); root.setContentsMargins(18,18,18,18); root.setSpacing(10)
        self.logo = QLabel(self); self.logo.setAlignment(Qt.AlignCenter); self._logo_width = None
        pix = None
        for c in [ASSETS_ROOT/"img"/"icons"/"icon2.jpg", ASSETS_ROOT/"img"/"icons"/"logo.png", ASSETS_ROOT/"img"/"icons"/"icon1.ico"]:
            if c.exists(): pix = QPixmap(str(c)); break
        if pix:
            w = min(420, pix.width()); self._logo_width = w; self.logo.setPixmap(pix.scaledToWidth(w, Qt.SmoothTransformation))
        else:
            self.logo.setText("Salem Explorer"); self.logo.setFont(QFont("Segoe UI", 18, QFont.Bold))
        root.addWidget(self.logo)
        self.msg = QLabel("Инициализация…", self); self.msg.setAlignment(Qt.AlignCenter); self.msg.setFont(QFont("Segoe UI", 10)); root.addWidget(self.msg)
        self._mv = None; self.resize(520, 300); self._center()
        self.setStyleSheet("""QWidget#SalemSplash { background: rgba(22,22,28,0.92); border-radius: 18px; } QLabel { color: #EDEEF0; } QProgressBar { height: 6px; border: none; background: #2d2f36; border-radius: 3px; } QProgressBar::chunk { background: #5aa7ff; }""")
        QTimer.singleShot(1200, self._start_loader)
    def _start_loader(self):
        gif_paths = [ASSETS_ROOT/"news_proxy"/"static"/"img"/"loader.gif", ASSETS_ROOT/"img"/"icons"/"preloader.gif"]
        for g in gif_paths:
            if g.exists(): self._mv = QMovie(str(g));
            if self._mv:
                if self._logo_width: self._mv.setScaledSize(QSize(self._logo_width, self._logo_width))
                self.logo.clear(); self.logo.setMovie(self._mv); self._mv.start(); return
        self.logo.hide(); pb = QProgressBar(self); pb.setRange(0,0); pb.setTextVisible(False); self.layout().insertWidget(0, pb)
    def _center(self):
        geo = self.frameGeometry(); screen = QApplication.primaryScreen().availableGeometry().center(); geo.moveCenter(screen); self.move(geo.topLeft())
    def set_message(self, text: str): self.msg.setText(text)

RAM_CACHE: dict[str, bytes] = {}
HOT_PATHS = [ASSETS_ROOT/"img"/"icons", ASSETS_ROOT/"modules"/"icons", ASSETS_ROOT/"news_proxy"/"IconsStartPage", ASSETS_ROOT/"news_proxy"/"img", ASSETS_ROOT/"news_proxy"/"static"/"css", ASSETS_ROOT/"news_proxy"/"static"/"js", ASSETS_ROOT/"news_proxy"/"static"/"img"]
_PREFETCH_LIMIT_KB = int(os.environ.get("SALEM_PREFETCH_LIMIT_KB", "12288" if (lambda: "FAST-HDD" if (_total_ram_gb() <= 8 or (os.cpu_count() or 4) <= 4) else "NORMAL")()=="FAST-HDD" else "24576"))

def _iter_files(rootp: Path, allow_types: tuple[str, ...]):
    if not rootp.exists(): return
    for p in rootp.rglob("*"):
        if p.is_file() and p.suffix.lower() in allow_types: yield p

def _prefetch_bg():
    allow = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico") if BOOT_MODE=="FAST-HDD" else (".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".css", ".js", ".html")
    count, total = 0, 0; limit_bytes = _PREFETCH_LIMIT_KB * 1024
    for base in HOT_PATHS:
        for f in _iter_files(base, allow):
            try:
                b = f.read_bytes();
                if total + len(b) > limit_bytes: pline(f"[PREFETCH] limit reached ~{total/1024:.0f} KB; stop"); pline(f"[PREFETCH] warmed {count} files"); return
                total += len(b)
                if len(b) <= 256*1024: RAM_CACHE[str(f)] = b
                count += 1
            except Exception: pass
    pline(f"[PREFETCH] warmed {count} files, ~{total/1024:.0f} KB")

def _load_manifest(path: Path) -> dict | None:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return None

def _prefetch_from_manifest(manifest_path: Path, size_threshold=256*1024):
    mf = _load_manifest(manifest_path)
    if not mf or "entries" not in mf: return _prefetch_bg()
    count = 0; total = 0; limit_bytes = _PREFETCH_LIMIT_KB * 1024
    for e in mf["entries"]:
        rel = e.get("rel"); size = int(e.get("size", 0))
        if not rel: continue
        p = (ASSETS_ROOT / rel)
        if not p.exists(): continue
        try:
            b = p.read_bytes()
            if total + len(b) > limit_bytes: pline(f"[PREFETCH-MF] limit reached ~{total/1024:.0f} KB; stop"); break
            total += len(b)
            if size <= size_threshold: RAM_CACHE[str(p)] = b
            count += 1
        except Exception: pass
    pline(f"[PREFETCH-MF] warmed {count} files, ~{total/1024:.0f} KB (from manifest)")

def start_prefetch():
    def _runner():
        mf_path = ASSETS_ROOT / "assets.manifest.json"
        if mf_path.exists(): _prefetch_from_manifest(mf_path)
        else: _prefetch_bg()
    threading.Thread(target=_runner, name="hot-prefetch", daemon=True).start()

# ----------------------------------------------------------------------------
# Self-check (absolute paths)
# ----------------------------------------------------------------------------

def _selfcheck_bg():
    for must in (ASSETS_ROOT/"news_proxy"/"static"/"avatars", ASSETS_ROOT/"news_proxy"/"static"/"uploads", ASSETS_ROOT/"news_proxy"/"static"/"wallpapers"):
        try: must.mkdir(parents=True, exist_ok=True)
        except Exception: pass
    checks = [
        ("IMG icons", ASSETS_ROOT/"img"/"icons"),
        ("MODULES icons", ASSETS_ROOT/"modules"/"icons"),
        ("NP IconsStartPage", ASSETS_ROOT/"news_proxy"/"IconsStartPage"),
        ("NP img", ASSETS_ROOT/"news_proxy"/"img"),
        ("NP static/api", ASSETS_ROOT/"news_proxy"/"static"/"api"),
        ("NP static/avatars", ASSETS_ROOT/"news_proxy"/"static"/"avatars"),
        ("NP static/img", ASSETS_ROOT/"news_proxy"/"static"/"img"),
        ("NP static/uploads", ASSETS_ROOT/"news_proxy"/"static"/"uploads"),
        ("NP static/wallpapers", ASSETS_ROOT/"news_proxy"/"static"/"wallpapers"),
        ("QtWebEngineProcess", Path(os.environ.get("QTWEBENGINEPROCESS_PATH",""))),
        ("Qt plugins", Path(os.environ.get("QT_PLUGIN_PATH",""))),
        ("Qt resources", Path(os.environ.get("QTWEBENGINE_RESOURCES_PATH",""))),
    ]
    missing = [name for name, p in checks if not p or not Path(p).exists()]
    if missing: log.warning("[SELFTEST] ❌ missing: " + ", ".join(missing))
    else:       log.info("[SELFTEST] ✅ assets ok")

# ----------------------------------------------------------------------------
# Ports & servers
# ----------------------------------------------------------------------------

def _free_port(start):
    p = start
    while p < start + 50:
        with socket.socket() as s:
            try: s.bind(("127.0.0.1", p)); return p
            except OSError: p += 1
    return start

PORT, MEDIA_PORT = _free_port(5000), _free_port(7000)
HOST = MEDIA_HOST = "127.0.0.1"
HEALTH_URL, MEDIA_HEALTH_URL = f"http://{HOST}:{PORT}/health", f"http://{MEDIA_HOST}:{MEDIA_PORT}/health"
HOME_URL = f"http://{HOST}:{PORT}/"; os.environ["SALEM_HOME_URL"] = HOME_URL
pline(f"[NET] main={HOST}:{PORT}  media={MEDIA_HOST}:{MEDIA_PORT}  HOME_URL={HOME_URL}")
from werkzeug.serving import make_server, WSGIRequestHandler
class _QuietWSGI(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        try: logging.getLogger("WSGI").info('WSGI %s "%s" %s %s', self.command, self.path, str(code), str(size))
        except Exception: pass
class FlaskThread(threading.Thread):
    def __init__(self, wsgi_app, host, port):
        super().__init__(daemon=True); self.httpd = make_server(host, port, wsgi_app, request_handler=_QuietWSGI)
    def run(self): addr = self.httpd.server_address; pline(f"[WSGI] up at http://{addr[0]}:{addr[1]}"); self.httpd.serve_forever()
    def shutdown(self):
        try: self.httpd.shutdown()
        except Exception: pass

# Make sure our project modules are importable regardless of cwd
try:
    from news_proxy.server import SalemServer
except Exception as e:
    SalemServer = None; logging.getLogger("launcher").warning("news_proxy.server not available: %s", e)
try:
    from MediaHub.mediahub_server import SalemMediaServer
except Exception as e:
    SalemMediaServer = None; logging.getLogger("launcher").warning("MediaHub.mediahub_server not available: %s", e)

class BootWorker(QThread):
    progress = pyqtSignal(str); done = pyqtSignal(bool, bool)
    def __init__(self, host, port, media_host, media_port, health_url, media_health_url, home_url):
        super().__init__(); self.HOST, self.PORT = host, port; self.MEDIA_HOST, self.MEDIA_PORT = media_host, media_port
        self.HEALTH_URL, self.MEDIA_HEALTH_URL = health_url, media_health_url; self.HOME_URL = home_url
        self.main_srv: FlaskThread | None = None; self.media_srv: FlaskThread | None = None
        self._stop = threading.Event(); self._watchdog_interval = 3.0
    def run(self):
        import requests
        try:
            if SalemServer and not self._in_use(self.HOST, self.PORT):
                self.progress.emit("Запуск основного сервиса…"); app = SalemServer(); self.main_srv = FlaskThread(getattr(app, "wsgi", app), self.HOST, self.PORT); self.main_srv.start()
            if SalemMediaServer and not self._in_use(self.MEDIA_HOST, self.MEDIA_PORT):
                self.progress.emit("Запуск медиа‑сервиса…"); app = SalemMediaServer(); self.media_srv = FlaskThread(getattr(app, "wsgi", app), self.MEDIA_HOST, self.MEDIA_PORT); self.media_srv.start()
            self.progress.emit("Ожидание готовности API…"); main_ok  = self._wait(self.HEALTH_URL, 25); media_ok = self._wait(self.MEDIA_HEALTH_URL, 15)
            try: requests.get(self.HOME_URL, timeout=2)
            except Exception: pass
            self.done.emit(main_ok, media_ok)
            while not self._stop.is_set():
                time.sleep(self._watchdog_interval)
                if SalemServer and not self._alive(self.HEALTH_URL):
                    logging.getLogger("watchdog").warning("[WD] main API down; restarting…")
                    try:
                        if self.main_srv: self.main_srv.shutdown()
                    except Exception: pass
                    try:
                        app = SalemServer(); self.main_srv = FlaskThread(getattr(app, "wsgi", app), self.HOST, self.PORT); self.main_srv.start()
                    except Exception as e:
                        logging.getLogger("watchdog").exception("[WD] main restart failed: %s", e)
                if SalemMediaServer and not self._alive(self.MEDIA_HEALTH_URL):
                    logging.getLogger("watchdog").warning("[WD] media API down; restarting…")
                    try:
                        if self.media_srv: self.media_srv.shutdown()
                    except Exception: pass
                    try:
                        app = SalemMediaServer(); self.media_srv = FlaskThread(getattr(app, "wsgi", app), self.MEDIA_HOST, self.MEDIA_PORT); self.media_srv.start()
                    except Exception as e:
                        logging.getLogger("watchdog").exception("[WD] media restart failed: %s", e)
        except Exception as e:
            logging.getLogger("launcher").exception("BootWorker error: %s", e); self.done.emit(False, False)
    def stop(self):
        self._stop.set()
        for srv in (self.main_srv, self.media_srv):
            try: srv.shutdown()
            except Exception: pass
    @staticmethod
    def _in_use(host, port, timeout=0.5):
        with socket.socket() as s:
            s.settimeout(timeout)
            try: s.connect((host, port)); return True
            except Exception: return False
    @staticmethod
    def _wait(url: str, timeout_s: int) -> bool:
        import requests, time as _t
        t0 = _t.time()
        while _t.time() - t0 < timeout_s:
            try:
                r = requests.get(url, timeout=1.5)
                if r.status_code == 200: return True
            except Exception: pass
            _t.sleep(0.2)
        return False
    @staticmethod
    def _alive(url: str) -> bool:
        import requests
        try:
            r = requests.get(url, timeout=1.0); return r.status_code == 200
        except Exception: return False

# ----------------------------------------------------------------------------
# Import UI class with fallback
# ----------------------------------------------------------------------------

def _import_webengine_widgets():
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineSettings, QWebEngineView
        return QWebEngineProfile, QWebEngineSettings, QWebEngineView
    except Exception:
        from PyQt5.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        return QWebEngineProfile, QWebEngineSettings, QWebEngineView
try:
    from Salem import SalemBrowser
    pline("[IMPORT] SalemBrowser imported OK")
except Exception as e:
    logging.getLogger("launcher").exception("[IMPORT] Failed to import SalemBrowser: %s", e)
    SalemBrowser = None
    from PyQt5.QtWidgets import QMainWindow
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    class _FallbackWindow(QMainWindow):
        def __init__(self):
            super().__init__(); self.setWindowTitle("Salem Explorer — Fallback"); self.resize(1100, 720)
            w = QWebEngineView(self); self.setCentralWidget(w); w.load(QUrl(os.environ.get("SALEM_HOME_URL", "about:blank")))

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    try:
        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: signal.signal(sig, lambda *_: QCoreApplication.quit())
            except Exception: pass
    except Exception: pass
    app = QApplication(sys.argv)

    QCoreApplication.setOrganizationName("Salem Software Corporation")
    QCoreApplication.setOrganizationDomain("https://officialcorporationsalem.kz")
    QCoreApplication.setApplicationName("Salem Explorer")
    QCoreApplication.setApplicationVersion("4.5.0.1")

    # Наш info-диалог на старте
    _about = StartupInfoDialog()
    _about.show()

    splash = Splash(); splash.show(); app.processEvents()
    threading.Thread(target=_selfcheck_bg, name="selfcheck", daemon=True).start()
    if BOOT_MODE == "FAST-HDD": start_prefetch()
    try:
        QWebEngineProfile, QWebEngineSettings, QWebEngineView = _import_webengine_widgets(); splash.set_message("WebEngine загружен…")
    except Exception as e:
        log.error(f"Fatal WebEngine import: {e}"); splash.set_message("Ошибка WebEngine"); time.sleep(1.2); return 1
    s = QWebEngineSettings.globalSettings(); s.setAttribute(QWebEngineSettings.PluginsEnabled, False); s.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True); s.setAttribute(QWebEngineSettings.JavascriptEnabled, True); s.setAttribute(QWebEngineSettings.WebGLEnabled, True)
    prof = QWebEngineProfile.defaultProfile(); u = _user_data_root()
    prof.setHttpCacheType(QWebEngineProfile.DiskHttpCache); prof.setCachePath(str(u / "cache")); prof.setPersistentStoragePath(str(u / "storage"))
    try: prof.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    except Exception: pass
    t = QElapsedTimer(); t.start()
    if SalemBrowser: win = SalemBrowser()
    else:
        win = _FallbackWindow()
    icon_path = ASSETS_ROOT/"img"/"icons"/"icon1.ico"
    if icon_path.exists():
        try: win.setWindowIcon(QIcon(str(icon_path)))
        except Exception: pass
    win.show(); pline(f"[BOOT] UI shown at {t.elapsed()} ms")
    try:
        tmp = QWebEngineView(); tmp.setAttribute(Qt.WA_DontShowOnScreen, True); tmp.load(QUrl("about:blank")); tmp.show(); QTimer.singleShot(600, tmp.deleteLater)
    except Exception: pass
    worker = BootWorker(HOST, PORT, MEDIA_HOST, MEDIA_PORT, HEALTH_URL, MEDIA_HEALTH_URL, HOME_URL)
    worker.progress.connect(splash.set_message)
    def go_home():
        try:
            if hasattr(win, "add_new_tab"): win.add_new_tab(QUrl(HOME_URL), "Home")
            elif hasattr(win, "navigate_to"): win.navigate_to(HOME_URL)
            elif hasattr(win, "load"): win.load(QUrl(HOME_URL))
        except Exception: traceback.print_exc()
    def on_ready(main_ok: bool, media_ok: bool):
        pline(f"[SERVERS] main={main_ok} media={media_ok}"); QTimer.singleShot(200, splash.close); 
        if main_ok: QTimer.singleShot(0, go_home)
    worker.done.connect(on_ready); worker.start(); QTimer.singleShot(5000, splash.close)
    def shutdown():
        try: worker.stop()
        except Exception: pass
    app.aboutToQuit.connect(shutdown)
    rc = app.exec_(); pline(f"Exit code {rc}"); return rc

def _user_data_root(profile: str = "DefaultProfile") -> Path:
    local = Path(os.getenv("LOCALAPPDATA", str(Path.home()))); rootp = local / "SalemExplorer" / profile
    for sub in ("cache","storage","downloads"): (rootp / sub).mkdir(parents=True, exist_ok=True)
    return rootp

def _looks_like_gl_crash(text: str) -> bool:
    text_l = text.lower(); tokens = ("qopengl","opengl","angle","opengl32","gpu","graphics driver")
    return any(t in text_l for t in tokens)

if __name__ == "__main__":
    try:
        rc = main(); sys.exit(rc)
    except Exception as e:
        try:
            with open(_last_crash_txt, "a", encoding="utf-8") as f:
                f.write("\n=== CRASH at " + datetime.now().isoformat(timespec='seconds') + " ===\n"); traceback.print_exc(file=f)
        except Exception: pass
        text = traceback.format_exc(); logging.getLogger("launcher").exception("Fatal: %s", e)
        if not GPU_MARKER.exists() and _looks_like_gl_crash(text):
            try: GPU_MARKER.write_text("use_soft_gl=1", encoding="utf-8")
            except Exception: pass
            try:
                args = [sys.executable] + [sys.argv[0], "--softgl"] + [a for a in sys.argv[1:] if a != "--softgl"]
                subprocess.Popen(args, cwd=str(INTERNAL if INTERNAL.exists() else BASE))
            except Exception: pass
        sys.exit(1)
