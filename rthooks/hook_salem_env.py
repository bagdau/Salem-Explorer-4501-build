import os, sys
from pathlib import Path

def pre_safe_import_module(api):
    base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    INTERNAL = base / "_internal"

    # Пути к ассетам Salem
    os.environ["SALEM_IMG"] = str(INTERNAL / "img")
    os.environ["SALEM_MODULES"] = str(INTERNAL / "modules")
    os.environ["SALEM_NEWS_PROXY"] = str(INTERNAL / "news_proxy")
    os.environ["SALEM_MEDIAHUB"] = str(INTERNAL / "MediaHub")

    # Qt plugin path
    qt_plugins = INTERNAL / "PyQt5" / "Qt5" / "plugins"
    if qt_plugins.exists():
        os.environ["QT_PLUGIN_PATH"] = str(qt_plugins)

    # QtWebEngineProcess и бинари
    qt_bin = None
    cands = [
        INTERNAL / "PyQt5" / "Qt5" / "bin",
        INTERNAL / "PyQt5" / "Qt"  / "bin",
        INTERNAL
    ]
    for cand in cands:
        exe = cand / "QtWebEngineProcess.exe"
        if exe.exists():
            qt_bin = cand
            os.environ["QTWEBENGINEPROCESS_PATH"] = str(exe)
            break

    if qt_bin:
        # PATH нужен для DLL
        os.environ["PATH"] = str(qt_bin) + os.pathsep + os.environ.get("PATH", "")

        # Ресурсы
        qt_res = INTERNAL / "PyQt5" / "Qt5" / "resources"
        if qt_res.exists():
            os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(qt_res)

        qt_loc = INTERNAL / "PyQt5" / "Qt5" / "translations" / "qtwebengine_locales"
        if qt_loc.exists():
            os.environ["QTWEBENGINE_LOCALES_PATH"] = str(qt_loc)

        # Для отладки можно включить:
        # print("[HOOK] QtWebEngineProcess =", exe)
        # print("[HOOK] PATH =", os.environ["PATH"])
        # print("[HOOK] RES =", os.environ.get("QTWEBENGINE_RESOURCES_PATH"))
        # print("[HOOK] LOCALES =", os.environ.get("QTWEBENGINE_LOCALES_PATH"))
